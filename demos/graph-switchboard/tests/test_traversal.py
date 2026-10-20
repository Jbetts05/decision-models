import copy
import json
import math
import os
import unittest
from collections import Counter
from unittest.mock import Mock, patch

import psycopg

from traversal.age import AgeGraph, bound_cypher, dollar_quote, graph_projection, literal, stored_properties, validate_read_query
from traversal.evaluate import sample_queries, score, summarize
from traversal.foundry import DECISION_INSTRUCTIONS, Foundry, InferenceError, parse_choice
from traversal.runtime import (
    BASELINE_PROMPT, ENTRY_PROMPT, decision_walk, llm_cypher, raw_input, resolve_entry,
    validate_answer, validate_returned_answer,
)
from traversal.server import valid_run, visible_vehicle
from traversal.synthetic import ENTITY_TYPES, KINDS, RELATION_TYPES, canonical_hash, generate, validate


class MemoryGraph:
    """Test double only: never used by the application or live evaluator."""

    def __init__(self, data):
        self.nodes = {n["id"]: n for n in data["nodes"]}
        self.edges = data["edges"]

    def node(self, identifier):
        return self.nodes[identifier]

    def neighbors(self, identifier):
        return [{"edge": e, "node": self.nodes[e["target"]]}
                for e in self.edges if e["source"] == identifier]

    def eligible(self, node, vehicle):
        procedure = self.nodes[node["procedure_id"]]
        return procedure["status"] == "published" and any(
            e["source"] == procedure["id"] and e["target"] == vehicle
            and e["type"] == "APPLIES_TO" for e in self.edges
        )


class ScriptedChoice:
    def __init__(self, choices, probability=1.0):
        self.choices = iter(choices)
        self.probability = probability
        self.states = []

    def choose(self, state, options):
        self.states.append(state)
        selected = next(self.choices)
        if selected not in options:
            raise ValueError("Scripted test choice is not available.")
        remaining = (1 - self.probability) / (len(options) - 1)
        return selected, {key: self.probability if key == selected else remaining for key in options}


class CorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph, cls.queries, cls.answers, cls.manifest = generate()
        cls.store = MemoryGraph(cls.graph)
        cls.oracle = {a["id"]: a for a in cls.answers}

    def test_reproducible_and_covers_published_schema(self):
        self.assertEqual(canonical_hash(generate()), canonical_hash(generate()))
        self.assertGreaterEqual(len(self.graph["nodes"]), 30)
        self.assertGreaterEqual(len(self.queries), 20)
        self.assertEqual(set(self.manifest["nodes"]), ENTITY_TYPES)
        self.assertEqual(set(self.manifest["relationships"]), set(RELATION_TYPES))
        self.assertEqual({n["result_type"] for n in self.graph["nodes"] if n["type"] == "Action"}, set(KINDS))

    def test_all_expected_paths_are_executable_by_controller(self):
        edges = {e["id"]: e for e in self.graph["edges"]}
        for query in self.queries:
            expected = self.oracle[query["id"]]
            choices = [eid for eid in expected["path"] if edges[eid]["type"] == "RESULT"]
            if expected["status"] == "clarify":
                choices.append("__clarify__")
            if expected["status"] == "next_action":
                choices.append("__next_action__")
            model = ScriptedChoice(choices)
            result = decision_walk(self.store, model, query)
            self.assertTrue(score(result, expected)["exact"], query["id"])
            if expected["status"] != "unsupported":
                validate_answer(self.store, query, result)
            for state in model.states:
                self.assertNotIn("expected", state)
                self.assertNotIn("category", state)
                self.assertNotIn("split", state)

    def test_wrong_path_does_not_pass_oracle_scoring(self):
        expected = self.answers[0]
        result = {**expected, "path": ["invented"]}
        self.assertFalse(score(result, expected)["exact"])
        self.assertTrue(score(result, expected)["wrong_transition"])

    def test_path_controller_rejects_jump_to_known_root(self):
        with self.assertRaises(ValueError):
            validate_answer(self.store, self.queries[0],
                            {"status": "root_cause", "target": self.answers[0]["target"], "path": []})

    def test_threshold_and_event_stream(self):
        query = next(q for q in self.queries if len(self.oracle[q["id"]]["path"]) >= 2
                     and self.oracle[q["id"]]["status"] == "root_cause")
        expected = self.oracle[query["id"]]
        selected = expected["path"][1]
        events = []
        result = decision_walk(self.store, ScriptedChoice([selected], .7), query, .8, events.append)
        self.assertEqual(result["status"], "clarify")
        self.assertEqual(len(result["path"]), 1)
        self.assertIn("decision_pending", {event["event"] for event in events})
        self.assertIn("decision", {event["event"] for event in events})

    def test_decision_trace_preserves_actual_inputs_at_each_step(self):
        query = next(q for q in self.queries
                     if self.oracle[q["id"]]["status"] == "root_cause"
                     and len(self.oracle[q["id"]]["path"]) >= 3)
        expected = self.oracle[query["id"]]
        edges = {edge["id"]: edge for edge in self.graph["edges"]}
        model = ScriptedChoice([identifier for identifier in expected["path"]
                                if edges[identifier]["type"] == "RESULT"])
        events = []
        result = decision_walk(self.store, model, query, emit=events.append)
        pending = [event for event in events if event["event"] == "decision_pending"]
        decisions = [event for event in events if event["event"] == "decision"]
        self.assertTrue(score(result, expected)["exact"])
        self.assertEqual(events[0]["event"], "start")
        self.assertEqual(events[0]["question"], query["question"])
        self.assertEqual(events[1]["event"], "scope_checked")
        self.assertTrue(events[1]["eligible"])
        self.assertEqual([len(event["request"]["state"]["traversed_edge_ids"]) for event in pending],
                         [index for index, identifier in enumerate(expected["path"])
                          if edges[identifier]["type"] == "RESULT"])
        for request, decision, state in zip(pending, decisions, model.states, strict=True):
            self.assertEqual(request["request"], decision["request"])
            self.assertEqual(request["request"]["state"], state)
            self.assertEqual(request["request"]["instructions"], DECISION_INSTRUCTIONS)
            self.assertEqual(set(request["request"]["criteria"]), set(decision["probabilities"]))
            self.assertNotIn("expected", state)
        transitions = [event for event in events if event["event"] == "traversed"]
        self.assertEqual(sum(event["policy"] == "model_selected_result" for event in transitions),
                         sum(edges[identifier]["type"] == "RESULT" for identifier in expected["path"]))
        self.assertEqual(len(transitions), len(expected["path"]))

    def test_trace_explains_policy_rejection_without_inference(self):
        query = next(q for q in self.queries if self.oracle[q["id"]]["status"] == "unsupported")
        model, events = ScriptedChoice([]), []
        result = decision_walk(self.store, model, query, emit=events.append)
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual([event["event"] for event in events], ["start", "scope_checked"])
        self.assertFalse(events[-1]["eligible"])
        self.assertEqual(model.states, [])

    def test_llm_trace_preserves_messages_before_each_request(self):
        query, expected = self.queries[0], self.oracle[self.queries[0]["id"]]

        class ReadGraph(MemoryGraph):
            def read(self, cypher, *, model_authored):
                self.last_query = cypher
                return [json.dumps({"nodes": list(self.nodes.values()), "edges": self.edges})]

        class Responses:
            def __init__(self):
                self.responses = iter([
                    {"kind": "query", "cypher": "MATCH (n) RETURN properties(n) LIMIT 1"},
                    {"kind": "answer", "cypher": "", **expected},
                ])
                self.inputs = []

            def chat(self, messages):
                self.inputs.append([dict(message) for message in messages])
                return next(self.responses)

        model, events = Responses(), []
        result = llm_cypher(ReadGraph(self.graph), model, query, emit=events.append)
        pending = [event for event in events if event["event"] == "cypher_pending"]
        self.assertTrue(score(result, expected)["exact"])
        self.assertEqual([event["turn"] for event in pending], [1, 2])
        self.assertEqual([event["successful_reads"] for event in pending], [0, 1])
        self.assertEqual([len(event["messages"]) for event in pending], [2, 4])
        self.assertEqual([event["messages"] for event in pending], model.inputs)
        user_input = json.loads(pending[0]["messages"][1]["content"])
        self.assertEqual(user_input["question"], query["question"])
        self.assertEqual(user_input["evidence"], raw_input(query)["evidence"])
        self.assertNotIn("start_node", user_input)
        self.assertNotIn("procedure_id", user_input)
        self.assertNotIn("current_node", user_input)
        self.assertNotIn("expected", user_input)
        query_event = next(event for event in events if event["event"] == "cypher")
        response = next(event for event in events if event["event"] == "graph_result")
        self.assertEqual(query_event["cypher"], response["cypher"])
        self.assertEqual(response["rows"], [json.dumps({"nodes": self.graph["nodes"], "edges": self.graph["edges"]})])

    def test_sol_rejects_invalid_answers_and_uses_its_own_correction(self):
        query = next(q for q in self.queries if self.oracle[q["id"]]["status"] == "root_cause")
        expected = self.oracle[query["id"]]
        good = {"kind": "answer", "cypher": "", **{
            key: expected[key] for key in ("status", "target", "path")}}
        entry = next(e for e in self.graph["edges"]
                     if e["type"] == "ENTRY_POINT" and e["target"] == query["start_node"])
        invalid = [
            {**good, "path": [entry["id"], *good["path"]]},
            {**good, "path": ["invented-edge"]},
            {**good, "target": query["start_node"]},
        ]
        for bad in invalid:
            with self.subTest(answer=bad):
                store = MemoryGraph(self.graph)
                store.read = Mock(return_value=[json.dumps(self.graph)])
                model = Mock(chat=Mock(side_effect=[
                    {"kind": "query", "cypher": "MATCH (n) RETURN properties(n)"},
                    bad, good,
                ]))
                events = []
                result = llm_cypher(store, model, query, max_turns=3, emit=events.append)
                self.assertTrue(score(result, expected)["exact"])
                self.assertEqual(model.chat.call_count, 3)
                store.read.assert_called_once()
                rejected = [e for e in events if e["event"] == "answer_rejected"]
                self.assertEqual(len(rejected), 1)
                self.assertEqual(rejected[0]["answer"], bad)
                self.assertEqual(len([e for e in events if e["event"] == "answer_path"]), 1)
                requests = [e for e in events if e["event"] == "cypher_pending"]
                self.assertEqual([len(e["messages"]) for e in requests], [2, 4, 6])
                feedback = json.loads(requests[-1]["messages"][-1]["content"])
                self.assertEqual(feedback["answer_validation_result"]["answer"], bad)
                self.assertNotIn("expected", feedback)
                self.assertNotIn("start_node", feedback)

    def test_sol_invalid_answer_feedback_cannot_extend_the_turn_budget(self):
        query = next(q for q in self.queries if self.oracle[q["id"]]["status"] == "root_cause")
        bad = {"kind": "answer", "status": "root_cause", "target": "invented", "path": ["invented-edge"]}
        store = MemoryGraph(self.graph)
        store.read = Mock(return_value=[json.dumps(self.graph)])
        model = Mock(chat=Mock(side_effect=[
            {"kind": "query", "cypher": "MATCH (n) RETURN properties(n)"}, bad, bad,
        ]))
        events = []
        with self.assertRaisesRegex(ValueError, "not returned by AGE"):
            llm_cypher(store, model, query, max_turns=3, emit=events.append)
        self.assertEqual(model.chat.call_count, 3)
        self.assertEqual(len([e for e in events if e["event"] == "answer_rejected"]), 2)
        self.assertNotIn("answer_path", {e["event"] for e in events})

    def test_sol_validation_feedback_does_not_retry_provider_failures(self):
        query = next(q for q in self.queries if self.oracle[q["id"]]["status"] == "root_cause")
        store = MemoryGraph(self.graph)
        store.read = Mock(return_value=[json.dumps(self.graph)])
        model = Mock(chat=Mock(side_effect=[
            {"kind": "query", "cypher": "MATCH (n) RETURN properties(n)"},
            {"kind": "answer", "status": "root_cause", "target": "invented", "path": ["invented-edge"]},
            InferenceError("Provider unavailable"),
        ]))
        with self.assertRaisesRegex(InferenceError, "Provider unavailable"):
            llm_cypher(store, model, query)
        self.assertEqual(model.chat.call_count, 3)

    def test_split_disjointness_and_category_sampling(self):
        limit = min(52, sum(query["split"] == "test" for query in self.queries))
        selected = sample_queries(self.queries, "test", limit, 7)
        self.assertEqual(selected, sample_queries(self.queries, "test", limit, 7))
        self.assertEqual({q["category"] for q in selected},
                         {q["category"] for q in self.queries if q["split"] == "test"})
        self.assertTrue(all(q["split"] == "test" for q in selected))
        procedures = {}
        for q in self.queries:
            procedures.setdefault(self.oracle[q["id"]]["procedure_id"], set()).add(q["split"])
        self.assertTrue(all(len(splits) == 1 for splits in procedures.values()))

    def test_validation_rejects_bad_endpoints_and_oracle(self):
        bad = copy.deepcopy(self.graph)
        bad["edges"][0]["target"] = bad["edges"][0]["source"]
        with self.assertRaises(ValueError):
            validate(bad, self.queries, self.answers)
        bad_answers = copy.deepcopy(self.answers)
        index = next(index for index, answer in enumerate(bad_answers) if len(answer["path"]) >= 2)
        bad_answers[index]["path"] = list(reversed(bad_answers[index]["path"]))
        with self.assertRaises(ValueError):
            validate(self.graph, self.queries, bad_answers)

    def test_edited_input_disables_expected_scoring(self):
        q = {**self.queries[0], "vehicle": visible_vehicle(self.queries[0].get("vehicle", {})),
             "evidence": [{"check": "Bench check", "observation": "Reported result"}]}
        _, scorable = valid_run({"case_id": q["id"]}, {q["id"]: q})
        self.assertTrue(scorable)
        _, scorable = valid_run({"case_id": q["id"], "question": "Different question"}, {q["id"]: q})
        self.assertFalse(scorable)
        with self.assertRaises(ValueError):
            valid_run({"case_id": q["id"], "evidence": [{"action_id": "a", "observation": ""}]}, {q["id"]: q})

    def test_symptom_only_stops_at_actual_first_action_without_inventing_results(self):
        query = next(q for q in self.queries if not q["evidence"]
                     and self.oracle[q["id"]]["status"] == "next_action")
        model = Mock()
        result = decision_walk(self.store, model, query)
        self.assertEqual(result["status"], "next_action")
        self.assertEqual(self.store.node(result["target"])["type"], "Action")
        self.assertTrue(all(self.store.nodes[
            next(edge for edge in self.graph["edges"] if edge["id"] == identifier)["source"]
        ]["type"] == "Condition" for identifier in result["path"]))
        model.choose.assert_not_called()

    def test_authored_handoff_without_result_edges_never_invents_a_cause(self):
        handoff = next(node for node in self.graph["nodes"] if node.get("handoff")
                       and self.store.nodes[node["procedure_id"]]["status"] == "published")
        vehicle = next(edge["target"] for edge in self.graph["edges"]
                       if edge["source"] == handoff["procedure_id"] and edge["type"] == "APPLIES_TO")
        query = {"id": "handoff", "start_node": handoff["id"], "vehicle_id": vehicle,
                 "question": "The earlier checks did not establish a cause.", "evidence": []}
        self.assertEqual(self.store.neighbors(handoff["id"]), [])
        self.assertEqual(decision_walk(self.store, Mock(), query)["status"], "next_action")
        query["evidence"] = [{"check": handoff["description"], "observation": "No conclusive result."}]
        model = Mock()
        self.assertEqual(decision_walk(self.store, model, query)["status"], "next_action")
        model.choose.assert_not_called()

    def test_real_returned_path_validator_rejects_unretrieved_edges_and_no_evidence_result(self):
        query = next(q for q in self.queries if self.oracle[q["id"]]["status"] == "root_cause")
        answer = self.oracle[query["id"]]
        nodes = self.store.nodes
        edges = {edge["id"]: edge for edge in self.graph["edges"]}
        validate_returned_answer(self.store, query, answer, nodes, edges)
        missing = dict(edges)
        del missing[answer["path"][-1]]
        with self.assertRaisesRegex(ValueError, "not returned"):
            validate_returned_answer(self.store, query, answer, nodes, missing)
        with self.assertRaisesRegex(ValueError, "actual supplied observation"):
            validate_returned_answer(self.store, {**query, "evidence": []}, answer, nodes, edges)

    def test_visible_vehicle_edits_and_missing_context_are_not_scorable(self):
        query = {**self.queries[0], "vehicle": {"make": "Brand X", "model": "Model A",
                                               "year": 2021, "configuration": "petrol"}}
        edited, scorable = valid_run({"case_id": query["id"], "vehicle": {}, "vehicle_id": ""},
                                     {query["id"]: query})
        self.assertFalse(scorable)
        self.assertEqual(raw_input(edited)["vehicle"], {})
        self.assertEqual(raw_input(edited)["vehicle_id"], "")
        cleared, scorable = valid_run({"case_id": query["id"], "vehicle": None, "vehicle_id": ""},
                                      {query["id"]: query})
        self.assertFalse(scorable)
        self.assertNotIn("vehicle", raw_input(cleared))


class ApiAndDatabaseBoundaryTests(unittest.TestCase):
    def test_both_model_schemas_name_actual_age_vehicle_year_property(self):
        graph, _, _, _ = generate()
        vehicle = next(node for node in graph["nodes"] if node["type"] == "VehicleModel")
        self.assertIn("model_year", vehicle)
        self.assertNotIn("year", vehicle)
        for prompt in (ENTRY_PROMPT, BASELINE_PROMPT):
            self.assertIn("model_year (integer)", prompt)
            self.assertIn("filter v.model_year, NOT v.year", prompt)

    def test_display_query_binds_values_without_replacing_quoted_tokens(self):
        query = """MATCH (n) WHERE n.id = $id AND n.note = '$id' AND n.other = $id2 RETURN n"""
        self.assertEqual(bound_cypher(query, {"id": 'quoted"node', "id2": "other"}),
                         """MATCH (n) WHERE n.id = "quoted\\"node" AND n.note = '$id' AND n.other = "other" RETURN n""")
        self.assertEqual(bound_cypher(query, None), query)
    def test_graph_projection_preserves_typed_content_and_does_not_invent_topology(self):
        node = {"id": "state", "type": "Condition", "description": "quoted ::vertex suffix"}
        edge = {"id": "route", "type": "NEXT_ACTION", "source": "state", "target": "action"}
        typed = ('[{"id":123,"label":"Condition","properties":' + json.dumps(node)
                 + '}::vertex, {"id":456,"properties":' + json.dumps(edge) + '}::edge]::path')
        self.assertEqual(graph_projection([typed], encoded=True), {"nodes": [node], "edges": [edge]})
        self.assertEqual(graph_projection([{"id": "partial"}, "state", 42]), {"nodes": [], "edges": []})
        self.assertEqual(graph_projection(['"state"', "42"], encoded=True), {"nodes": [], "edges": []})

    def test_entry_input_contains_no_supplied_graph_ids_or_oracle(self):
        node = {"id": "retrieved-state", "type": "Condition", "procedure_id": "retrieved-procedure"}
        graph = Mock()
        graph.read.return_value = [json.dumps(node)]
        graph.node.return_value = node
        graph.eligible.return_value = True
        model = Mock()
        model.chat.side_effect = [
            {"kind": "query", "cypher": "MATCH (n:Condition) RETURN properties(n) LIMIT 1"},
            {"kind": "answer", "status": "next_action", "target": node["id"], "path": []},
        ]
        events = []
        raw = {"id": "case", "vehicle_id": "vehicle", "question": "Reported bench state", "evidence": [],
               "start_node": "hidden-start", "procedure_id": "hidden-procedure", "expected": "hidden-oracle"}
        result = resolve_entry(graph, model, raw, emit=events.append)
        returned = next(event for event in events if event["event"] == "entry_candidates")
        self.assertEqual(returned["candidates"], [node])
        self.assertEqual(returned["rows"], graph.read.return_value)
        first = next(event for event in events if event["event"] == "cypher_pending")
        self.assertEqual(json.loads(first["messages"][1]["content"]),
                         {key: raw[key] for key in ("vehicle_id", "question", "evidence")})
        self.assertNotIn("hidden-", json.dumps(first["messages"]))
        self.assertEqual(len(first["messages"]), 2)
        self.assertEqual(result["query"]["start_node"], node["id"])
        self.assertEqual(result["status"], "resolved")
        graph.eligible.assert_called_once_with(node, "vehicle")

    def test_entry_requires_real_read_and_returned_candidate(self):
        raw = {"id": "case", "vehicle_id": "vehicle", "question": "Unknown state", "evidence": []}
        answer = {"kind": "answer", "status": "next_action", "target": "invented", "path": []}
        with self.assertRaisesRegex(ValueError, "without querying"):
            resolve_entry(Mock(), Mock(chat=Mock(return_value=answer)), raw)
        graph = Mock(read=Mock(return_value=[]))
        model = Mock(chat=Mock(side_effect=[{"kind": "query", "cypher": "MATCH (n) RETURN n"}, answer]))
        with self.assertRaisesRegex(ValueError, "not a starting state returned"):
            resolve_entry(graph, model, raw)
        graph.node.assert_not_called()

    def test_entry_no_match_and_ambiguity_stop_without_fallback(self):
        raw = {"id": "case", "vehicle_id": "vehicle", "question": "Unknown state", "evidence": []}
        for status in ("unsupported", "clarify"):
            graph = Mock(read=Mock(return_value=[]))
            model = Mock(chat=Mock(side_effect=[
                {"kind": "query", "cypher": "MATCH (n) RETURN n"},
                {"kind": "answer", "status": status, "target": "", "path": []},
            ]))
            self.assertEqual(resolve_entry(graph, model, raw)["status"], status)
            graph.node.assert_not_called()

    def test_empty_clarification_needs_no_artificial_graph_read_in_either_lane(self):
        raw = {"id": "missing-context", "vehicle_id": "", "vehicle": {},
               "question": "Something is wrong. Where should I start?", "evidence": []}
        for run in (resolve_entry, llm_cypher):
            with self.subTest(lane=run.__name__):
                graph = Mock()
                model = Mock(chat=Mock(return_value={
                    "kind": "answer", "status": "clarify", "target": "", "path": [],
                }))
                result = run(graph, model, raw)
                self.assertEqual(result["status"], "clarify")
                self.assertIsNone(result["target"])
                self.assertEqual(result["path"], [])
                self.assertEqual(graph.mock_calls, [])
                self.assertEqual(model.chat.call_count, 1)

    def test_vehicle_conflict_transport_and_abstention_contract_not_semantic_recognition(self):
        raw = {
            "id": "blower-customer", "title": "Hidden fixture blower title",
            "start_node": "hidden-blower-start",
            "vehicle_id": "vehicle-brandx-modela-2021",
            "vehicle": {"make": "Brand X", "model": "Model A", "year": 2021,
                        "configuration": "petrol"},
            "question": "This is a Brand Y Model B 2024 diesel, not the selected vehicle. "
                        "The engine idles roughly.",
            "evidence": [],
        }
        for run in (resolve_entry, llm_cypher):
            for status in ("clarify", "unsupported"):
                with self.subTest(lane=run.__name__, explicit_abstention=status):
                    answers = []
                    if status == "unsupported":
                        answers.append({"kind": "query", "cypher":
                                        "MATCH (p:Procedure) RETURN properties(p) LIMIT 1",
                                        "status": "clarify", "target": "", "path": []})
                    answers.append({"kind": "answer", "cypher": "", "status": status,
                                    "target": "", "path": []})
                    responses = []
                    for answer in answers:
                        response = Mock()
                        response.read.return_value = json.dumps({
                            "usage": {"input_tokens": 10, "output_tokens": 5},
                            "choices": [{"finish_reason": "stop", "message": {
                                "role": "assistant", "content": json.dumps(answer),
                            }}],
                        }).encode()
                        response.__enter__ = Mock(return_value=response)
                        response.__exit__ = Mock(return_value=False)
                        responses.append(response)
                    model = Foundry({"endpoint": "https://example.cognitiveservices.azure.com",
                                     "baseline_deployment": "Sol"})
                    events = []
                    model.emit = events.append
                    graph = Mock(read=Mock(return_value=[]))
                    with patch.object(model, "headers", return_value={}), \
                            patch("traversal.foundry.urllib.request.urlopen",
                                  side_effect=responses) as http:
                        result = run(graph, model, raw)
                    requests = [event["request"] for event in events
                                if event["event"] == "model_request"]
                    self.assertEqual(len(requests), len(answers))
                    sent = json.loads(http.call_args_list[0].args[0].data)
                    self.assertEqual(requests[0], sent)
                    self.assertEqual(json.loads(sent["messages"][1]["content"]), raw_input(raw))
                    self.assertEqual(json.loads(sent["messages"][1]["content"])["question"],
                                     raw["question"])
                    self.assertNotIn("hidden-blower-start", json.dumps(sent))
                    self.assertNotIn("Hidden fixture blower title", json.dumps(sent))
                    self.assertEqual(result["status"], status)
                    self.assertIsNone(result["target"])
                    self.assertEqual(result["path"], [])
                    graph.node.assert_not_called()
                    graph.eligible.assert_not_called()

    def test_pre_read_clarification_cannot_smuggle_a_target_or_path(self):
        raw = {"id": "ambiguous", "vehicle_id": "", "question": "Which car?", "evidence": []}
        for run in (resolve_entry, llm_cypher):
            for target, path in (("invented-action", []), ("", ["invented-edge"])):
                with self.subTest(lane=run.__name__, target=target, path=path):
                    model = Mock(chat=Mock(return_value={
                        "kind": "answer", "status": "clarify", "target": target, "path": path,
                    }))
                    with self.assertRaises(ValueError):
                        run(Mock(), model, raw)

    def test_ambiguous_actual_entry_candidates_can_clarify_without_choosing_first(self):
        nodes = [{"id": identifier, "type": "Condition", "entry": True,
                  "procedure_id": "procedure-" + identifier}
                 for identifier in ("rough-idle", "lean-idle")]
        raw = {"id": "ambiguous", "vehicle_id": "vehicle", "question": "The engine feels wrong.",
               "evidence": []}
        graph = Mock(read=Mock(return_value=[json.dumps(nodes)]))
        model = Mock(chat=Mock(side_effect=[
            {"kind": "query", "cypher": "MATCH (p:Procedure)-[:ENTRY_POINT]->(c) RETURN properties(c)"},
            {"kind": "answer", "status": "clarify", "target": "", "path": []},
        ]))
        events = []
        result = resolve_entry(graph, model, raw, emit=events.append)
        self.assertEqual(result["status"], "clarify")
        candidates = next(event for event in events if event["event"] == "entry_candidates")
        self.assertEqual(candidates["candidates"], nodes)
        graph.node.assert_not_called()

    def test_broad_candidates_can_be_narrowed_then_resolved_without_overclarifying(self):
        data, _, _, _ = generate()
        nodes = {node["id"]: node for node in data["nodes"]}
        entries = {
            edge["source"]: nodes[edge["target"]]
            for edge in data["edges"] if edge["type"] == "ENTRY_POINT"
        }
        rough = entries["procedure-rough-idle"]
        lean = entries["procedure-lean-idle"]
        graph = Mock(
            read=Mock(side_effect=[
                [json.dumps({"candidates": [rough, lean]})],
                [json.dumps({"candidate": rough})],
            ]),
            node=Mock(return_value=rough), eligible=Mock(return_value=True),
            is_entry=Mock(return_value=True),
        )
        broad = ("MATCH (p:Procedure)-[:ENTRY_POINT]->(c:Condition) "
                 "WHERE p.status = 'published' AND toLower(p.title) CONTAINS 'idle' "
                 "RETURN {procedure:properties(p),node:properties(c)} LIMIT 20")
        narrow = ("MATCH (p:Procedure)-[:ENTRY_POINT]->(c:Condition) "
                  "WHERE p.id = 'procedure-rough-idle' "
                  "RETURN {procedure:properties(p),node:properties(c)} LIMIT 1")
        model = Mock(chat=Mock(side_effect=[
            {"kind": "query", "cypher": broad},
            {"kind": "query", "cypher": narrow},
            {"kind": "answer", "status": "next_action", "target": rough["id"], "path": []},
        ]))
        raw = {
            "id": "narrowing", "vehicle_id": "vehicle-brandx-modela-2021",
            "question": "The engine shakes at idle with its warning light on. The scan shows "
                        "P0301; nobody has reported a lean-mixture finding.",
            "evidence": [{"check": "Completed engine diagnostic scan",
                          "observation": "The saved scan lists P0301."}],
        }
        events = []
        result = resolve_entry(graph, model, raw, emit=events.append)
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["target"], rough["id"])
        self.assertEqual([len(event["candidates"]) for event in events
                          if event["event"] == "entry_candidates"], [2, 1])
        self.assertEqual([call.args[0] for call in graph.read.call_args_list], [broad, narrow])
        self.assertEqual(model.chat.call_count, 3)
        self.assertEqual(model.chat.call_args.kwargs, {"answer_only": True})
        graph.eligible.assert_called_once_with(rough, raw["vehicle_id"])
        graph.is_entry.assert_called_once_with(rough)

    def test_entry_rejects_unpublished_or_inapplicable_node_and_future_path(self):
        raw = {"id": "case", "vehicle_id": "vehicle", "question": "Unknown state", "evidence": []}
        node = {"id": "state", "type": "Condition", "procedure_id": "procedure"}
        for path, error in (([], "publication"), (["future"], "future path")):
            graph = Mock(read=Mock(return_value=[json.dumps(node)]),
                         node=Mock(return_value=node), eligible=Mock(return_value=False))
            model = Mock(chat=Mock(side_effect=[
                {"kind": "query", "cypher": "MATCH (n) RETURN n"},
                {"kind": "answer", "status": "next_action", "target": "state", "path": path},
            ]))
            with self.assertRaisesRegex(ValueError, error):
                resolve_entry(graph, model, raw)

    def test_entry_query_errors_remain_visible_and_budget_is_bounded(self):
        raw = {"id": "case", "vehicle_id": "vehicle", "question": "Unknown state", "evidence": []}
        graph = Mock(read=Mock(side_effect=ValueError("Query rejected")))
        model = Mock(chat=Mock(return_value={"kind": "query", "cypher": "invalid"}))
        events = []
        with self.assertRaisesRegex(InferenceError, "budget"):
            resolve_entry(graph, model, raw, emit=events.append)
        self.assertEqual(model.chat.call_count, 3)
        self.assertEqual([e["error"] for e in events if e["event"] == "graph_result"], ["Query rejected"] * 2)
        self.assertTrue(model.chat.call_args.kwargs["answer_only"])
        self.assertFalse(any(e["event"] == "entry_selected" for e in events))

    def test_entry_reserves_last_turn_for_a_structured_final_answer(self):
        raw = {"id": "case", "vehicle_id": "vehicle", "question": "Missing operating profile", "evidence": []}
        model = Mock(chat=Mock(side_effect=[
            {"kind": "query", "cypher": "MATCH (n) RETURN n"},
            {"kind": "query", "cypher": "MATCH (n:Condition) RETURN n"},
            {"kind": "answer", "status": "unsupported", "target": "", "path": []},
        ]))
        result = resolve_entry(Mock(read=Mock(return_value=[])), model, raw)
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(model.chat.call_count, 3)
        self.assertEqual(model.chat.call_args.kwargs, {"answer_only": True})

    def test_answer_only_schema_cannot_request_another_query(self):
        model = Foundry({"endpoint": "https://example.cognitiveservices.azure.com",
                         "baseline_deployment": "Sol"})
        query = {"kind": "query", "cypher": "MATCH (n) RETURN n",
                 "status": "clarify", "target": "", "path": []}
        with patch.object(model, "post", return_value={
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(query)}}],
        }) as post:
            with self.assertRaisesRegex(InferenceError, "invalid structured output"):
                model.chat([], answer_only=True)
        schema = post.call_args.args[2]["response_format"]["json_schema"]["schema"]
        self.assertEqual(schema["properties"]["kind"]["enum"], ["answer"])

    def test_sol_cannot_reuse_hybrid_query_history_or_hidden_start(self):
        graph, queries, answers, _ = generate()
        model = Mock(chat=Mock(return_value={"kind": "answer", **answers[0]}))
        history = [{"role": "user", "content": "Previously retrieved graph rows"}]
        with self.assertRaisesRegex(ValueError, "without successfully querying"):
            llm_cypher(MemoryGraph(graph), model, queries[0], entry_messages=history)
        self.assertNotEqual(model.chat.call_args.args[0][0], history[0])
        state = json.loads(model.chat.call_args.args[0][1]["content"])
        self.assertEqual(state, raw_input(queries[0]))
        self.assertNotIn("start_node", state)
        self.assertNotIn("current_node", state)
        self.assertEqual(model.chat.call_count, 1)

    def test_sol_first_query_can_return_complete_route_then_answer_without_intake(self):
        graph, queries, answers, _ = generate()
        oracle = {answer["id"]: answer for answer in answers}
        query = next(query for query in queries if oracle[query["id"]]["status"] == "root_cause")
        answer = oracle[query["id"]]
        procedure = answer["procedure_id"]

        class ReturnedGraph(MemoryGraph):
            def read(self, cypher, *, model_authored):
                self.queried = True
                return [json.dumps({
                    "nodes": [node for node in self.nodes.values() if node.get("procedure_id") == procedure],
                    "edges": [edge for edge in self.edges if edge.get("procedure_id") == procedure],
                })]

        model = Mock(chat=Mock(side_effect=[
            {"kind": "query", "cypher": "MATCH (n)-[r]->(m) RETURN {source:properties(n),edge:properties(r),target:properties(m)}"},
            {"kind": "answer", **answer},
        ]))
        store = ReturnedGraph(graph)
        events = []
        result = llm_cypher(store, model, query, emit=events.append)
        self.assertTrue(score(result, answer)["exact"])
        self.assertEqual(model.chat.call_count, 2)
        self.assertEqual(len([event for event in events if event["event"] == "cypher"]), 1)
        self.assertNotIn("entry_start", {event["event"] for event in events})
        first = next(event for event in events if event["event"] == "cypher_pending")
        self.assertEqual(json.loads(first["messages"][1]["content"]), raw_input(query))

    def test_non_entry_returned_condition_is_not_a_valid_hybrid_start(self):
        node = {"id": "later-condition", "type": "Condition", "procedure_id": "procedure"}
        graph = Mock(read=Mock(return_value=[json.dumps(node)]),
                     node=Mock(return_value=node), eligible=Mock(return_value=True),
                     is_entry=Mock(return_value=False))
        model = Mock(chat=Mock(side_effect=[
            {"kind": "query", "cypher": "MATCH (c:Condition) RETURN properties(c)"},
            {"kind": "answer", "status": "next_action", "target": node["id"], "path": []},
        ]))
        with self.assertRaisesRegex(ValueError, "ENTRY_POINT"):
            resolve_entry(graph, model, {"id": "test", "question": "An engine warning is on.",
                                        "vehicle_id": "vehicle", "evidence": []})

    def test_sol_unresolved_answers_normalize_empty_target_without_an_invented_path(self):
        for status in ("clarify", "unsupported"):
            model = Mock(chat=Mock(side_effect=[
                {"kind": "query", "cypher": "MATCH (p:Procedure) RETURN properties(p) LIMIT 1"},
                {"kind": "answer", "status": status, "target": "", "path": []},
            ]))
            result = llm_cypher(Mock(read=Mock(return_value=[])), model,
                                {"question": "Which vehicle is this?", "vehicle_id": "", "evidence": []})
            self.assertEqual(result["status"], status)
            self.assertIsNone(result["target"])
            self.assertEqual(result["path"], [])

    def test_probabilities_reject_malformed_or_nonfinite_values(self):
        options = {"a": "first", "b": "second"}
        good = {"answers": {"transition": {"type": "choice", "choice": "a",
                                          "probabilities": {"a": .8, "b": .2}}}}
        self.assertEqual(parse_choice(good, options)[0], "a")
        for bad in (True, math.nan, math.inf, -1, 2, "0.8"):
            payload = copy.deepcopy(good)
            payload["answers"]["transition"]["probabilities"]["a"] = bad
            with self.assertRaises(InferenceError):
                parse_choice(payload, options)
        for payload in ({}, {"answers": []}, {"answers": {"transition": {"choice": "a"}}}):
            with self.assertRaises(InferenceError):
                parse_choice(payload, options)

    def test_endpoint_restrictions(self):
        for endpoint in ("http://example.org", "https://example.org", "https://x.services.ai.azure.com/path",
                         "https://user@x.services.ai.azure.com"):
            with self.assertRaises(ValueError):
                Foundry({"endpoint": endpoint})

    def test_query_dialect_blocks_mutation_and_sql_surfaces(self):
        valid = [
            "MATCH (n)-[r]->(m) RETURN {a: properties(n), b: properties(r), c: properties(m)} LIMIT 50",
            "MATCH (n) WHERE n.description = 'DELETE a node; not an instruction' RETURN properties(n)",
            "MATCH (n) WHERE n.id = 'x' RETURN n",
        ]
        for query in valid:
            self.assertEqual(validate_read_query(query), query)
        bad = [
            "MATCH (n) DELETE n RETURN n", "MATCH (n) SET n.id='x' RETURN n",
            "MATCH (n) RETURN n; DROP TABLE x", "CALL something()",
            "MATCH (n) RETURN pg_sleep(100)", "MATCH (n) RETURN ag_catalog.set_config('x','y',true)",
            "MATCH (n) RETURN n // comment", "MATCH (n) RETURN n UNION MATCH (m) RETURN m",
        ]
        for query in bad:
            with self.assertRaises(ValueError, msg=query):
                validate_read_query(query)

    def test_sql_dollar_quote_uses_noncolliding_delimiter(self):
        value = "MATCH (n) WHERE n.id = '$cypher$); DROP TABLE x;' RETURN n"
        result = dollar_quote(value).as_string(None)
        self.assertTrue(result.startswith("$cypher_$"))
        self.assertTrue(result.endswith("$cypher_$"))
        self.assertEqual(literal({"a": "quoted\"string"}), '{a: "quoted\\"string"}')
        self.assertEqual(stored_properties({"x": None, "nested": {"v": 2}}), {"nested": {"v": 2}})

    def test_llm_must_query_before_answering(self):
        graph, queries, answers, _ = generate()

        class NoQuery:
            def chat(self, messages):
                return {"kind": "answer", "cypher": "", **answers[0]}

        with self.assertRaisesRegex(ValueError, "without successfully querying"):
            llm_cypher(MemoryGraph(graph), NoQuery(), queries[0])


@unittest.skipUnless(os.environ.get("AGE_INTEGRATION") == "1", "Set AGE_INTEGRATION=1 for the real AGE integration checks.")
class AgeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from traversal.__main__ import database_url
        cls.graph, cls.queries, cls.answers, _ = generate()
        cls.store = AgeGraph(database_url(), "traversal_" + canonical_hash(cls.graph)[:12])

    @classmethod
    def tearDownClass(cls):
        cls.store.close()

    def test_round_trip_and_prepared_reads(self):
        self.store.verify(self.graph)
        current = self.store.node(self.queries[0]["start_node"])
        self.assertEqual(current["type"], "Condition")
        self.assertEqual(len(self.store.neighbors(current["id"])), 1)

    def test_fixed_query_trace_uses_actual_cypher_parameters_and_rows(self):
        events = []
        self.store.emit = events.append
        try:
            identifier = self.queries[0]["start_node"]
            result = self.store.neighbors(identifier)
            self.assertEqual([event["event"] for event in events], ["graph_query", "graph_rows", "graph_data"])
            self.assertIn("MATCH (n)-[r]->(m)", events[0]["cypher"])
            self.assertEqual(events[0]["parameters"], {"id": identifier})
            self.assertEqual(events[1]["rows"], result)
            self.assertGreaterEqual(events[1]["query_ms"], 0)
            self.assertEqual(events[2]["nodes"], [result[0]["node"]])
            self.assertEqual(events[2]["edges"], [result[0]["edge"]])
            events.clear()
            self.store.read("MATCH (n) RETURN n LIMIT 1", model_authored=True)
            self.assertEqual([event["event"] for event in events], ["graph_data"])
            self.assertTrue(events[0]["model_authored"])
            self.assertEqual(len(events[0]["nodes"]), 1)
            events.clear()
            with self.assertRaises(Exception):
                self.store.read("MATCH (n) RETURN nonexistent_function(n)")
            self.assertEqual([event["event"] for event in events], ["graph_query", "graph_rows"])
            self.assertIn("error", events[-1])
        finally:
            self.store.emit = None

    def test_readonly_transaction_and_role_are_real(self):
        connection = self.store.connection
        self.assertEqual(connection.execute("SELECT current_user").fetchone()[0], "traversal_reader")
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            self.assertEqual(connection.execute("SHOW transaction_read_only").fetchone()[0], "on")
        # Bypass the lexical guard to prove the database itself refuses mutation.
        with self.assertRaises(psycopg.Error) as raised:
            self.store.read("CREATE (n:Condition {id:'must-not-exist'}) RETURN n.id")
        self.assertIn(getattr(raised.exception, "sqlstate", None), {"25006", "42501"})
        self.store.verify(self.graph)

    def test_model_query_returns_actual_graph_maps(self):
        current = self.queries[0]["start_node"]
        result = self.store.read(f"MATCH (n) WHERE n.id = '{current}' RETURN properties(n)", model_authored=True)
        self.assertEqual(json.loads(result[0])["id"], current)


if __name__ == "__main__":
    unittest.main()
