"""Offline authored-corpus checks; these do not measure model accuracy."""

import copy
import json
import re
import unittest
from collections import Counter
from decimal import Decimal
from pathlib import Path

from traversal.synthetic import DATASET_VERSION, VEHICLE_ID, canonical_hash, generate, validate


class CorpusQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph, cls.queries, cls.answers, cls.manifest = generate()
        cls.nodes = {node["id"]: node for node in cls.graph["nodes"]}
        cls.edges = {edge["id"]: edge for edge in cls.graph["edges"]}
        cls.oracle = {answer["id"]: answer for answer in cls.answers}
        cls.cases = {query["id"]: query for query in cls.queries}

    def results(self, identifier):
        return [self.edges[eid] for eid in self.oracle[identifier]["path"]
                if self.edges[eid]["type"] == "RESULT"]

    def test_rewritten_graph_has_one_vehicle_and_varied_published_routes(self):
        vehicles = [node for node in self.nodes.values() if node["type"] == "VehicleModel"]
        self.assertEqual([node["id"] for node in vehicles], [VEHICLE_ID])
        procedures = [node for node in self.nodes.values() if node["type"] == "Procedure"]
        self.assertEqual(Counter(node["status"] for node in procedures), {"published": 8, "draft": 1})
        sizes = Counter(node["procedure_id"] for node in self.nodes.values()
                        if node["type"] != "VehicleModel")
        self.assertGreaterEqual(len(set(sizes.values())), 4)
        for query in self.queries:
            self.assertTrue(query["title"].strip())
            self.assertNotIn("operating profile", query["question"].lower())
            self.assertNotIn("procedure-", query["question"])

    def test_findings_require_confirmation_and_normal_checks_do_not_diagnose(self):
        for node in self.nodes.values():
            if node["type"] == "Action":
                self.assertLess(len(node["description"]), 90)
                self.assertIn("fictional", node["safety_metadata"].lower())
                self.assertIn("not", node["safety_metadata"].lower())
            if node["type"] == "RootCause":
                self.assertTrue(node["confirmation_required"])
                self.assertRegex(node["description"].lower(), r"confirm|isolat")
                self.assertNotIn("retained-warning", node["description"].lower())
        for edge in self.edges.values():
            if self.nodes[edge["target"]]["type"] != "RootCause":
                continue
            self.assertTrue(edge["confirmation_basis"])
            if edge["type"] == "RESULT":
                self.assertTrue(edge["establishes_finding"])
                self.assertNotIn(edge["result_type"], {"dtc", "numeric", "range"})
                self.assertIsNot(edge["rule"].get("value"), False)
            else:
                self.assertEqual(edge["type"], "INDICATES")
                self.assertTrue(self.nodes[edge["source"]]["established_finding"])
        for identifier in ["misfire-unresolved", "lean-unlocalized", "lean-normal-pressure",
                           "slow-crank-not-battery", "coolant-normal"]:
            answer = self.oracle[identifier]
            self.assertEqual(answer["status"], "next_action")
            self.assertTrue(self.nodes[answer["target"]]["handoff"])

    def test_persisted_artifacts_equal_generator_and_hashes(self):
        directory = Path(__file__).resolve().parents[1] / "data" / "traversal"
        graph = json.loads((directory / "graph.json").read_text(encoding="utf-8"))
        queries = [json.loads(line) for line in (directory / "queries.jsonl").read_text(encoding="utf-8").splitlines()]
        oracle = [json.loads(line) for line in (directory / "oracle.jsonl").read_text(encoding="utf-8").splitlines()]
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        from traversal.journeys import generate as generate_current
        self.assertEqual((graph, queries, oracle, manifest), generate_current())
        for key, value in (("graph", graph), ("queries", queries), ("oracle", oracle)):
            self.assertEqual(canonical_hash(value), manifest[f"{key}_sha256"])
        self.assertEqual(manifest["dataset_version"], "4.2.0")
        self.assertFalse(manifest["provenance"]["expert_validation"])
        self.assertFalse(manifest["provenance"]["external_vehicle_data"])
        self.assertIn("Reviewer-authored", manifest["provenance"]["oracle"])
        self.assertIn("not comparable", manifest["comparison_compatibility"])
        self.assertTrue(all(node.get("source_reference") for node in self.nodes.values()))
        self.assertTrue(all(edge.get("source_reference") for edge in self.edges.values()))
        for procedure in (n for n in self.nodes.values() if n["type"] == "Procedure"):
            self.assertEqual(procedure["version"], 3)
            self.assertIn("petrol", procedure["applicability"])
            self.assertEqual(bool(procedure["publication_date"]), procedure["status"] == "published")

    def test_no_oracle_values_in_model_input(self):
        from traversal.runtime import raw_input

        root_ids = {node["id"] for node in self.nodes.values() if node["type"] == "RootCause"}
        for query in self.queries:
            self.assertFalse({"expected", "status", "path", "target", "entry_expectation"} & query.keys())
            public = raw_input(query)
            self.assertFalse({"start_node", "procedure_id", "demo", "category", "split"} & public.keys())
            text = json.dumps(public)
            self.assertFalse(any(identifier in text for identifier in root_ids), query["id"])
            self.assertFalse(any(identifier in text for identifier in self.edges), query["id"])
            for observation in public["evidence"]:
                self.assertEqual(set(observation), {"check", "observation"})
                self.assertNotIn("action_id", observation)

    def test_boundary_and_negation_golden_labels(self):
        # Bind specific authored language to independently stated rules, without an LLM.
        golden = [
            ("voltage-at-cutoff", -1, "exactly 12.2 V", {"operator": "gte", "threshold": 12.2, "unit": "V"}),
            ("pressure-at-lower-bound", -1, "exactly 250 kPa",
             {"operator": "between_inclusive", "minimum": 250, "maximum": 400, "unit": "kPa"}),
            ("temperature-at-upper-bound", -1, "exactly +5 degC",
             {"operator": "between_inclusive", "minimum": -5, "maximum": 5, "unit": "degC"}),
            ("slow-crank-not-battery", -1, "does not confirm battery failure", {"operator": "eq", "value": False}),
            ("misfire-unresolved", -1, "does not confirm compression loss", {"operator": "eq", "value": False}),
            ("misfire-coil-confirmed", -1, "confirms the cylinder-one coil", {"operator": "eq", "value": "coil confirmed"}),
            ("misfire-plug-confirmed", -1, "substituting the cylinder-one plug resolved", {"operator": "eq", "value": "plug confirmed"}),
            ("blower-pattern-only", -1, "high speed but not at lower fan speeds", {"operator": "eq", "value": "some speeds"}),
            ("historical-voltage", -1, "current resting battery reading is 11.9 V",
             {"operator": "lt", "threshold": 12.2, "unit": "V"}),
        ]
        for identifier, index, phrase, expected_rule in golden:
            with self.subTest(case=identifier):
                self.assertIn(phrase, self.cases[identifier]["evidence"][index]["observation"])
                self.assertEqual(self.results(identifier)[index]["rule"], expected_rule)
        self.assertIn("12.6 V, not current evidence",
                      self.cases["historical-voltage"]["evidence"][0]["observation"])

    def test_numeric_and_range_rules_partition_exact_and_near_boundary_values(self):
        epsilon = Decimal("0.000001")
        checked = Counter()

        def matches(rule, value):
            number = lambda key: Decimal(str(rule[key]))
            operator = rule["operator"]
            if operator == "lt":
                return value < number("threshold")
            if operator == "gte":
                return value >= number("threshold")
            if operator == "outside":
                return value < number("minimum") or value > number("maximum")
            if operator == "between_inclusive":
                return number("minimum") <= value <= number("maximum")
            self.fail("Unexpected numeric rule operator")

        for action in (node for node in self.nodes.values()
                       if node["type"] == "Action" and node["result_type"] in {"numeric", "range"}):
            rules = [edge["rule"] for edge in self.edges.values()
                     if edge["type"] == "RESULT" and edge["source"] == action["id"]]
            self.assertEqual(len(rules), 2)
            self.assertTrue(all(rule["unit"] == action["expected_unit"] for rule in rules))
            if action["result_type"] == "numeric":
                by_operator = {rule["operator"]: rule for rule in rules}
                self.assertEqual(set(by_operator), {"lt", "gte"})
                threshold = Decimal(str(by_operator["lt"]["threshold"]))
                self.assertEqual(threshold, Decimal(str(by_operator["gte"]["threshold"])))
                values = [threshold - epsilon, threshold, threshold + epsilon]
                self.assertFalse(matches(by_operator["lt"], threshold))
                self.assertTrue(matches(by_operator["gte"], threshold))
            else:
                by_operator = {rule["operator"]: rule for rule in rules}
                self.assertEqual(set(by_operator), {"outside", "between_inclusive"})
                low, high = [Decimal(str(by_operator["outside"][key])) for key in ("minimum", "maximum")]
                self.assertLess(low, high)
                for key in ("minimum", "maximum"):
                    self.assertEqual(by_operator["outside"][key], by_operator["between_inclusive"][key])
                values = [low - epsilon, low, low + epsilon, high - epsilon, high, high + epsilon]
                self.assertTrue(matches(by_operator["between_inclusive"], low))
                self.assertTrue(matches(by_operator["between_inclusive"], high))
            for value in values:
                self.assertEqual(sum(matches(rule, value) for rule in rules), 1,
                                 (action["id"], str(value)))
            checked[action["result_type"]] += 1
        self.assertGreaterEqual(checked["numeric"], 3)
        self.assertGreaterEqual(checked["range"], 3)

    def test_exact_diagnostic_tokens_not_substrings_and_explicit_absence(self):
        golden = [
            ("code-near-match", "P0301", "not_contains", "P03010 only"),
            ("misfire-no-code", "P0301", "not_contains", "P0301 is absent"),
            ("misfire-code-only", "P0301", "contains", "lists P0301"),
            ("no-start-code-only", "P0335", "contains", "lists P0335"),
            ("no-start-key", "P0335", "not_contains", "no P0335 code"),
        ]
        for identifier, code, operator, phrase in golden:
            self.assertIn(phrase, self.cases[identifier]["evidence"][0]["observation"])
            self.assertEqual(self.results(identifier)[0]["rule"], {"operator": operator, "value": code})
        text = self.cases["code-near-match"]["evidence"][0]["observation"]
        codes = re.findall(r"\bP\d{4,5}\b", text)
        self.assertEqual(codes, ["P03010", "P0301"])
        # Exact token boundaries reject prefixed and suffixed codes; absence still
        # requires interpreting the record's negation, not testing token presence.
        self.assertIsNone(re.search(r"\bP0301\b", "P03010 XP0301 P0301X"))
        for identifier in ["misfire-code-only", "no-start-code-only", "code-near-match"]:
            self.assertEqual(self.oracle[identifier]["status"], "next_action")

    def test_ambiguity_and_action_identity_cases_have_authored_stops(self):
        unusable = [q for q in self.queries if q["category"] in {
            "uncertain", "contradiction", "incomplete", "not_performed", "wrong_unit", "injection",
        }]
        self.assertGreaterEqual(len(unusable), 10)
        for query in unusable:
            answer = self.oracle[query["id"]]
            self.assertEqual(answer["status"], "clarify", query["id"])
            self.assertEqual(self.nodes[answer["target"]]["type"], "Action")
            self.assertIn(answer["target"], [item["action_id"] for item in query["evidence"]])
        query, answer = self.cases["out-of-order-misfire"], self.oracle["out-of-order-misfire"]
        self.assertEqual(answer["status"], "next_action")
        self.assertNotIn(answer["target"], [item["action_id"] for item in query["evidence"]])
        query, answer = self.cases["reordered-lean-records"], self.oracle["reordered-lean-records"]
        self.assertEqual(answer["status"], "root_cause")
        self.assertEqual([item["action_id"] for item in query["evidence"]],
                         [edge["source"] for edge in reversed(self.results(query["id"]))])
        for identifier in ["ambiguous-warning", "missing-vehicle"]:
            self.assertEqual(self.oracle[identifier]["entry_expectation"]["status"], "clarify")

    def test_result_alternatives_discriminate_without_paraphrase_inflation(self):
        seen = set()
        for node in (n for n in self.nodes.values() if n["type"] == "Action" and not n.get("handoff")):
            results = [edge for edge in self.edges.values() if edge["type"] == "RESULT"
                       and edge["source"] == node["id"]]
            rules = [edge["rule"] for edge in results]
            self.assertEqual(len({canonical_hash(rule) for rule in rules}), len(rules))
            self.assertEqual(len({edge["description"] for edge in results}), len(results))
            if all(rule["operator"] == "eq" for rule in rules):
                self.assertEqual(len({json.dumps(rule["value"]) for rule in rules}), len(rules))
            seen.add(node["result_type"])
        self.assertEqual(seen, {"boolean", "categorical", "numeric", "range", "dtc", "observation"})
        self.assertLess(len(self.queries), 100)
        repeated_titles = {title: count for title, count in
                           Counter(q["title"] for q in self.queries).items() if count > 1}
        self.assertEqual(repeated_titles, {"Recorded value at an illustrative boundary": 3})

    def test_validator_rejects_competing_action_and_wrong_evidence(self):
        graph = copy.deepcopy(self.graph)
        edge = next(edge for edge in graph["edges"] if edge["type"] == "NEXT_ACTION")
        graph["edges"].append({**edge, "id": "extra-action"})
        with self.assertRaisesRegex(ValueError, "exactly one"):
            validate(graph, self.queries, self.answers)
        queries = copy.deepcopy(self.queries)
        query = next(query for query in queries if query["evidence"])
        query["evidence"][0]["action_id"] = query["start_node"]
        with self.assertRaisesRegex(ValueError, "Evidence must reference an action"):
            validate(self.graph, queries, self.answers)

    def test_authored_graph_descriptions_do_not_reintroduce_known_placeholders(self):
        placeholders = {"observe indicator"} | {
            "observe " + kind for kind in
            ("boolean", "categorical", "numeric", "range", "dtc", "observation")
        }
        for node in self.nodes.values():
            if node["type"] == "Action":
                self.assertNotIn(node["description"].strip().rstrip(".").lower(), placeholders)
            if node["type"] == "Condition":
                self.assertFalse(node["description"].startswith("The preceding recorded findings require"))
        self.assertEqual(self.nodes["procedure-blower-a-pattern"]["description"],
                         "Review recorded cabin fan-speed pattern.")
        self.assertIn("fan observation", self.nodes["procedure-blower-a-pattern"]["instruction"])
        self.assertEqual(self.nodes["procedure-blower-c-motor"]["description"],
                         "The recorded cabin fan observation reports no air flow at any selected fan speed. "
                         "A blower motor fault has not been established.")
        self.assertEqual(self.nodes["procedure-rough-idle-c-isolation"]["description"],
                         "The saved engine scan contains P0301. "
                         "The cause of the cylinder-one misfire has not been isolated.")


if __name__ == "__main__":
    unittest.main()
