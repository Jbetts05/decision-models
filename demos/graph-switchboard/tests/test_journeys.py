import copy
import json
import re
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from traversal.journeys import generate, released_turns, validate, PACK, VERSION
from traversal.runtime import decision_walk, raw_input, llm_cypher
from traversal.server import AppStore, Service, valid_run
from traversal.synthetic import canonical_hash
from test_traversal import MemoryGraph, ScriptedChoice


class JourneyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph, cls.queries, cls.oracle, cls.manifest = generate()
        cls.cases = {q["id"]: q for q in cls.queries}
        cls.answers = {a["id"]: a for a in cls.oracle}
        cls.edges = {e["id"]: e for e in cls.graph["edges"]}

    def service(self):
        with patch("traversal.server.initialize_app_store"), patch("traversal.server.AppStore"):
            return Service("unused", {"decision_deployment": "Decision-1",
                                     "baseline_deployment": "Sol"}, Path("data") / "traversal")

    def test_reproducible_journeys_and_vehicle_cases(self):
        self.assertEqual(VERSION, "4.2.0")
        self.assertEqual(self.manifest["demonstrations"], 10)
        self.assertEqual(self.manifest["journey_turns"], 40)
        self.assertEqual(len(self.queries), 143)
        self.assertEqual(canonical_hash(generate()), canonical_hash(generate()))
        self.assertEqual(len(self.manifest["sources"]), 11)

    def test_sources_have_real_sections_and_no_required_indicates_fabrication(self):
        self.assertNotIn("INDICATES", self.manifest["relationships"])
        for node in self.graph["nodes"]:
            self.assertTrue(node["source_reference"])
        for edge in self.graph["edges"]:
            if edge["type"] == "RESULT":
                self.assertTrue(edge["selection_criteria"])

    def test_each_snapshot_only_contains_released_records(self):
        for key in {q["journey_id"] for q in self.queries if q.get("demo")}:
            for index in range(3):
                current, following = self.cases[f"{key}-turn-{index}"], self.cases[f"{key}-turn-{index + 1}"]
                self.assertEqual(following["evidence"][:len(current["evidence"])], current["evidence"])
                self.assertGreater(len(following["evidence"]), len(current["evidence"]))
                self.assertEqual(current["next_case"], following["id"])
                self.assertNotIn(following["evidence"][-1]["observation"], json.dumps(raw_input(current)))

    def test_public_inputs_have_no_graph_or_reviewer_hints(self):
        graph_ids = {n["id"] for n in self.graph["nodes"] if n["type"] != "VehicleModel"}
        for query in self.queries:
            public = raw_input(query)
            self.assertEqual(set(public), {"question", "vehicle_id", "vehicle", "evidence"})
            text = json.dumps(public)
            self.assertNotIn("Reviewer only", text)
            self.assertFalse(any(identifier in text for identifier in graph_ids))
            self.assertTrue(all(set(record) == {"check", "observation"} for record in public["evidence"]))

    def test_customer_text_has_no_synthetic_speaker_or_stage_prefixes(self):
        blocks = re.split(r"^## Journey \d+:", PACK.read_text(encoding="utf-8"), flags=re.M)[1:]
        for key, block in zip(("misfire", "lean", "airflow"), blocks, strict=True):
            turns = released_turns(block.split("### Contrast:", 1)[0])
            for index in range(4):
                query = self.cases[f"{key}-turn-{index}"]
                self.assertEqual(query["question"], "\n\n".join(question for question, _ in turns[:index + 1]))
                self.assertEqual(query["evidence"][0]["check"], "Job card")
        for query in self.queries:
            self.assertNotRegex(json.dumps(raw_input(query)),
                                r"(?i)\b(?:customer|technician|workshop)\s+(?:release|turn|stage)\s+\d+")

    def test_label_cleanup_preserves_all_graph_content_and_expected_answers(self):
        prior = next(item for item in self.manifest["prior_versions"] if item["version"] == "4.1.2")
        graph = {**self.graph, "dataset_version": "4.1.2",
                 "nodes": [n for n in self.graph["nodes"] if not n.get("procedure_id", "").startswith("procedure-v42-")],
                 "edges": [e for e in self.graph["edges"] if not e["procedure_id"].startswith("procedure-v42-")]}
        queries = copy.deepcopy([q for q in self.queries if q["category"] != "problem_journey"])
        for query in queries:
            if query["id"].startswith("vehicle-") and query["id"].endswith("-pressure-310"):
                query["demo"] = True
        old_ids = {q["id"] for q in queries}
        self.assertEqual(len(old_ids), 87)
        self.assertEqual(canonical_hash(graph), prior["graph_sha256"])
        self.assertEqual(canonical_hash(queries), prior["queries_sha256"])
        self.assertEqual(canonical_hash([a for a in self.oracle if a["id"] in old_ids]), prior["oracle_sha256"])

    def test_catalog_excludes_future_releases(self):
        service = self.service()
        cases = service.catalog()["cases"]
        self.assertEqual(len(cases), 123)
        self.assertEqual(sum(c["demo"] for c in cases), 20)
        self.assertEqual(service.catalog()["default_case_id"], "weak-washers-turn-0")
        self.assertTrue(next(c for c in cases if c["id"] == service.catalog()["default_case_id"])["demo"])
        self.assertTrue(all(not {"journey_id", "turn", "turn_count", "next_case"} & c.keys() for c in cases))
        self.assertNotIn("P0302, no P0301", json.dumps(
            [c for c in cases if c["demo"] and c["input_kind"] == "problem"]))
        self.assertEqual(service.catalog()["input_policy"], "single-problem-v1")

    def test_record_examples_are_complete_upfront_inputs_not_released_continuations(self):
        service = self.service()
        cases = [case for case in service.catalog()["cases"] if case["input_kind"] == "with_records"]
        self.assertEqual(len(cases), 10)
        for case in cases:
            family = case["id"].removesuffix("-records")
            final = self.cases[f"{family}-turn-3"]
            self.assertEqual(case["evidence"], raw_input(final)["evidence"])
            self.assertEqual(case["vehicle"], final["vehicle"])
            self.assertNotIn("\n\n", case["question"])
            query, scorable = valid_run({"case_id": case["id"]}, service.queries)
            self.assertTrue(scorable)
            self.assertNotIn("journey_id", query)
            self.assertEqual(service.oracle[case["id"]],
                             {**self.answers[final["id"]], "id": case["id"]})
            self.assertEqual(set(raw_input(query)), {"question", "vehicle_id", "vehicle", "evidence"})

    def test_startup_rejects_source_text_not_matching_the_graph_manifest(self):
        with patch.object(Path, "read_bytes", return_value=b"unversioned change"):
            with self.assertRaisesRegex(ValueError, "Source guide"):
                self.service()

    def test_invalid_previous_identifiers_never_reach_the_database(self):
        store = AppStore.__new__(AppStore)
        store.connection = Mock()
        for identifier in (None, 3, {}, "../other", "g" * 32, "a" * 31):
            with self.assertRaises(ValueError):
                store.get_record(identifier)
        store.connection.assert_not_called()

    def test_controller_can_execute_every_authored_resolved_path(self):
        store = MemoryGraph(self.graph)
        for query in self.queries:
            answer = self.answers[query["id"]]
            if answer["target"] is None:
                continue
            choices = [identifier for identifier in answer["path"] if self.edges[identifier]["type"] == "RESULT"]
            if not store.nodes[answer["target"]].get("handoff") and answer["status"] != "root_cause":
                choices.append("__clarify__" if answer["status"] == "clarify" else "__next_action__")
            result = decision_walk(store, ScriptedChoice(choices), query)
            for field in ("status", "target", "path"):
                self.assertEqual(result[field], answer[field], query["id"])

    def test_completed_nonlocalising_record_is_referral_not_clarification(self):
        self.assertEqual(self.answers["lean-turn-3"]["status"], "next_action")
        self.assertEqual(self.answers["lean-recurrence"]["status"], "root_cause")
        main, contrast = self.cases["lean-turn-3"], self.cases["lean-recurrence"]
        self.assertIn("+4%", main["evidence"][-1]["observation"])
        self.assertEqual(main["evidence"][:-1], contrast["evidence"][:-1])
        self.assertIn("+23%", contrast["evidence"][-1]["observation"])

    def test_release_requires_completed_unedited_record_from_same_graph(self):
        service = self.service()
        previous = {"graph": service.name, "scorable": True,
                    "query": service.queries["misfire-turn-0"]}
        service.records.get_record.return_value = previous
        released = service.release("run")
        self.assertEqual(released["id"], "misfire-turn-1")
        previous["scorable"] = False
        with self.assertRaises(ValueError):
            service.release("run")

    def test_continuation_rejects_cross_journey_skips_and_resets_edited_context(self):
        service = self.service()
        service.records.get_record.return_value = {
            "graph": service.name, "scorable": True, "query": service.queries["misfire-turn-0"]}
        good = service.continue_query(service.queries["misfire-turn-1"], True, "run")
        self.assertIn("_previous_record", good)
        for case in ("misfire-turn-2", "airflow-turn-1"):
            with self.assertRaises(ValueError):
                service.continue_query(service.queries[case], True, "run")
        edited = service.continue_query(service.queries["misfire-turn-1"], False, "run")
        self.assertNotIn("_previous_record", edited)
        with self.assertRaises(ValueError):
            service.continue_query(service.queries["misfire-turn-1"], True, None)

    def test_context_is_whitelisted_and_scoring_disabled_for_edits(self):
        service = self.service()
        q, scorable = valid_run({"case_id": "lean-turn-1"}, service.queries)
        self.assertTrue(scorable)
        _, scorable = valid_run({"case_id": "lean-turn-1", "question": "Different problem"}, service.queries)
        self.assertFalse(scorable)
        self.assertNotIn("next_case", raw_input(q))

    def test_baseline_can_use_its_own_retrieved_context_without_another_read(self):
        query = self.cases["misfire-turn-3"]
        expected = self.answers[query["id"]]
        prior = {"messages": [{"role": "system", "content": "prior own context"}],
                 "nodes": {n["id"]: n for n in self.graph["nodes"]}, "edges": self.edges}
        original = copy.deepcopy(prior)
        model = Mock()
        model.chat.return_value = {"kind": "answer", "cypher": "", **expected}
        result = llm_cypher(MemoryGraph(self.graph), model, query, prior_context=prior)
        self.assertEqual(result["target"], expected["target"])
        self.assertEqual(prior, original)
        self.assertIn("released_evidence_update", model.chat.call_args.args[0][1]["content"])

    def test_invalid_graph_cannot_pass_source_validation(self):
        broken = copy.deepcopy(self.graph)
        result = next(e for e in broken["edges"] if e.get("establishes_finding"))
        result["confirmation_basis"] = None
        with self.assertRaisesRegex(ValueError, "confirmation"):
            validate(broken, self.queries, self.oracle)


if __name__ == "__main__":
    unittest.main()
