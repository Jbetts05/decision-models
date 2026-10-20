"""Dataset integrity and controller execution, not a model-accuracy benchmark."""

import copy
import json
import unittest
from collections import Counter
from pathlib import Path

from traversal.synthetic import (
    DATASET_VERSION, ENTITY_TYPES, KINDS, RELATION_TYPES, VEHICLE_ID,
    canonical_hash, generate, validate,
)


class SyntheticV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph, cls.queries, cls.answers, cls.manifest = generate()
        cls.nodes = {n["id"]: n for n in cls.graph["nodes"]}
        cls.edges = {e["id"]: e for e in cls.graph["edges"]}
        cls.cases = {q["id"]: q for q in cls.queries}
        cls.oracle = {a["id"]: a for a in cls.answers}

    def test_reproducible_small_authored_corpus(self):
        self.assertEqual(DATASET_VERSION, "3.0.0")
        self.assertEqual(canonical_hash(generate()), canonical_hash(generate()))
        self.assertLess(len(self.queries), 100)
        self.assertGreaterEqual(len(self.queries), 40)
        self.assertEqual(set(self.manifest["nodes"]), ENTITY_TYPES)
        self.assertEqual(set(self.manifest["relationships"]), set(RELATION_TYPES))
        self.assertEqual({n["result_type"] for n in self.nodes.values() if n["type"] == "Action"}, set(KINDS))
        self.assertEqual(self.manifest["coverage"]["published_procedures"], 8)
        self.assertEqual(self.manifest["coverage"]["draft_procedures"], 1)

    def test_generated_files_match_the_versioned_manifest(self):
        directory = Path(__file__).resolve().parents[1] / "data" / "traversal"
        graph = json.loads((directory / "graph.json").read_text(encoding="utf-8"))
        queries = [json.loads(line) for line in (directory / "queries.jsonl").read_text(encoding="utf-8").splitlines()]
        oracle = [json.loads(line) for line in (directory / "oracle.jsonl").read_text(encoding="utf-8").splitlines()]
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        from traversal.journeys import generate as generate_current
        self.assertEqual((graph, queries, oracle, manifest), generate_current())
        for label, value in [("graph", graph), ("queries", queries), ("oracle", oracle)]:
            self.assertEqual(manifest[label + "_sha256"], canonical_hash(value))

    def test_single_recognizable_fictional_vehicle_and_explicit_context(self):
        vehicles = [n for n in self.nodes.values() if n["type"] == "VehicleModel"]
        self.assertEqual(len(vehicles), 1)
        self.assertEqual(vehicles[0]["id"], VEHICLE_ID)
        self.assertEqual((vehicles[0]["make"], vehicles[0]["model"], vehicles[0]["model_year"],
                          vehicles[0]["configuration"]), ("Brand X", "Model A", 2021, "petrol"))
        self.assertTrue(vehicles[0]["fictional"])
        self.assertEqual(self.cases["missing-vehicle"]["vehicle"], {})
        self.assertEqual(self.cases["unsupported-electric"]["vehicle"]["configuration"], "electric")
        self.assertEqual(self.cases["unsupported-year"]["vehicle"]["model_year"], 2018)

    def test_customer_demonstrations_stop_without_inventing_observations(self):
        symptom_cases = [q for q in self.queries if q["category"] == "symptom_only"]
        self.assertEqual(len(symptom_cases), 8)
        for query in symptom_cases:
            with self.subTest(query=query["id"]):
                answer = self.oracle[query["id"]]
                self.assertTrue(query["demo"])
                self.assertEqual(query["intent"], "customer")
                self.assertEqual(query["evidence"], [])
                self.assertEqual(answer["status"], "next_action")
                self.assertEqual(len(answer["path"]), 1)
                self.assertEqual(self.edges[answer["path"][0]]["type"], "NEXT_ACTION")
                self.assertEqual(self.nodes[answer["target"]]["type"], "Action")
        self.assertEqual(self.manifest["demonstrations"], sum(q["demo"] for q in self.queries))
        self.assertEqual(self.manifest["adversarial_evaluation"], sum(not q["demo"] for q in self.queries))

    def test_real_rewrite_no_artificial_profiles_or_latch_contract(self):
        graph_text = json.dumps(self.graph).lower()
        for artifact in ["simv", "simms", "retained-warning", "operating profile", "vehicle-sim-a"]:
            self.assertNotIn(artifact, graph_text)
        for query in self.queries:
            self.assertTrue(query["title"].strip())
            self.assertNotIn("procedure-", query["question"])
            self.assertNotIn("operating profile", query["question"])
            for observation in query["evidence"]:
                self.assertTrue(observation["check"].strip())
                self.assertNotIn("procedure-", observation["check"])

    def test_graph_topologies_are_varied_and_normal_checks_handoff(self):
        action_counts = Counter(n["procedure_id"] for n in self.nodes.values() if n["type"] == "Action")
        self.assertGreaterEqual(len(set(action_counts.values())), 4)
        branch_counts = Counter(e["source"] for e in self.edges.values() if e["type"] == "RESULT")
        self.assertIn(3, branch_counts.values())
        self.assertIn(2, branch_counts.values())
        self.assertTrue(any(e["type"] == "INDICATES" for e in self.edges.values()))
        for name in ["misfire-unresolved", "lean-unlocalized", "lean-normal-pressure",
                     "slow-crank-not-battery", "coolant-normal", "remote-no-spare"]:
            answer = self.oracle[name]
            self.assertEqual(answer["status"], "next_action", name)
            self.assertTrue(self.nodes[answer["target"]]["handoff"], name)

    def test_codes_and_numeric_clues_do_not_establish_component_causes(self):
        for name in ["misfire-code-only", "no-start-code-only", "lean-trim-only",
                     "slow-crank-low-voltage", "lean-low-pressure", "coolant-discrepancy",
                     "blower-pattern-only", "remote-spare-only"]:
            self.assertEqual(self.oracle[name]["status"], "next_action", name)
        self.assertEqual(self.oracle["code-near-match"]["status"], "next_action")
        self.assertTrue(all(a["status"] == "clarify" for a in self.answers
                            if self.cases[a["id"]]["category"] in {
                                "contradiction", "wrong_unit", "uncertain", "incomplete", "injection",
                            }))

    def test_intake_ambiguity_is_labeled_separately_from_scoped_paths(self):
        for name in ["ambiguous-warning", "missing-vehicle"]:
            self.assertEqual(self.oracle[name]["entry_expectation"],
                             {"status": "clarify", "target": None})
        for name in ["draft-infotainment", "unsupported-electric", "unsupported-year"]:
            self.assertEqual(self.oracle[name]["status"], "unsupported")
            self.assertEqual(self.oracle[name]["path"], [])
            self.assertIsNone(self.oracle[name]["target"])

    def test_every_authored_oracle_path_executes_in_the_controller(self):
        from traversal.runtime import decision_walk, validate_answer

        outer = self

        class MemoryGraph:
            def node(self, identifier):
                return outer.nodes[identifier]

            def neighbors(self, identifier):
                return [{"edge": e, "node": outer.nodes[e["target"]]}
                        for e in outer.edges.values() if e["source"] == identifier]

            def eligible(self, node, vehicle):
                pid = node["procedure_id"]
                return outer.nodes[pid]["status"] == "published" and any(
                    e["type"] == "APPLIES_TO" and e["source"] == pid and e["target"] == vehicle
                    for e in outer.edges.values()
                )

        class AuthoredChoice:
            def __init__(self, answer):
                self.choices = iter([e for e in answer["path"] if outer.edges[e]["type"] == "RESULT"]
                                    + (["__clarify__"] if answer["status"] == "clarify" else
                                       ["__next_action__"] if answer["status"] == "next_action" else []))

            def choose(self, state, options):
                choice = next(self.choices)
                if choice not in options:
                    raise AssertionError(f"Unavailable authored branch: {choice}")
                return choice, {key: float(key == choice) for key in options}

        graph = MemoryGraph()
        for query in self.queries:
            with self.subTest(query=query["id"]):
                expected = self.oracle[query["id"]]
                result = decision_walk(graph, AuthoredChoice(expected), query)
                self.assertEqual({key: result[key] for key in ("status", "target", "path")},
                                 {key: expected[key] for key in ("status", "target", "path")})
                if expected["status"] != "unsupported":
                    validate_answer(graph, query, result)

    def test_validation_rejects_missing_endpoints_oracle_jumps_and_unobserved_results(self):
        bad_graph = copy.deepcopy(self.graph)
        bad_graph["edges"][0]["target"] = "missing"
        with self.assertRaisesRegex(ValueError, "endpoint"):
            validate(bad_graph, self.queries, self.answers)
        bad_answers = copy.deepcopy(self.answers)
        bad_answers[0]["path"] = [self.answers[1]["path"][0]]
        with self.assertRaises(ValueError):
            validate(self.graph, self.queries, bad_answers)
        bad_queries = copy.deepcopy(self.queries)
        next(q for q in bad_queries if q["id"] == "misfire-coil-confirmed")["evidence"] = []
        with self.assertRaisesRegex(ValueError, "no recorded evidence"):
            validate(self.graph, bad_queries, self.answers)

    def test_validation_rejects_split_leakage_and_fabricated_handoff_findings(self):
        bad_queries = copy.deepcopy(self.queries)
        bad_queries[0]["split"] = "test"
        with self.assertRaisesRegex(ValueError, "leakage"):
            validate(self.graph, bad_queries, self.answers)
        bad_graph = copy.deepcopy(self.graph)
        action = next(n for n in bad_graph["nodes"] if n.get("handoff") and n["procedure_id"] == "procedure-rough-idle")
        edge = copy.deepcopy(next(e for e in bad_graph["edges"] if e["type"] == "RESULT"
                                  and e["procedure_id"] == action["procedure_id"]))
        edge.update(id="invented", source=action["id"], result_type="observation")
        bad_graph["edges"].append(edge)
        with self.assertRaisesRegex(ValueError, "handoff"):
            validate(bad_graph, self.queries, self.answers)

    def test_publication_provenance_and_disclaimers_are_explicit(self):
        for node in self.nodes.values():
            self.assertTrue(node["source_reference"])
            if node["type"] == "Procedure":
                self.assertEqual(node["version"], 3)
                self.assertIn("petrol", node["applicability"])
                if node["status"] == "published":
                    self.assertTrue(node["publication_date"])
        self.assertFalse(self.manifest["provenance"]["expert_validation"])
        self.assertFalse(self.manifest["provenance"]["external_vehicle_data"])
        self.assertIn("not", self.graph["notice"])

    def test_root_confirmation_contract_rejects_a_negative_check_shortcut(self):
        bad_graph = copy.deepcopy(self.graph)
        edge = next(e for e in bad_graph["edges"] if e["type"] == "RESULT"
                    and self.nodes[e["target"]]["type"] == "RootCause"
                    and e["result_type"] == "boolean")
        edge["rule"]["value"] = False
        with self.assertRaisesRegex(ValueError, "negative check"):
            validate(bad_graph, self.queries, self.answers)
        bad_graph = copy.deepcopy(self.graph)
        edge = next(e for e in bad_graph["edges"] if e["type"] == "INDICATES")
        del edge["confirmation_basis"]
        with self.assertRaisesRegex(ValueError, "confirmation evidence"):
            validate(bad_graph, self.queries, self.answers)


if __name__ == "__main__":
    unittest.main()
