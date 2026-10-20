"""Source fidelity, input isolation and varied customer-to-answer examples."""

import copy
import json
import unittest

from traversal.examples import extend_examples
from traversal.journeys import PROBLEMS, SOURCES, generate, source_sections
from traversal.runtime import raw_input


class ProblemExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph, cls.queries, cls.oracle, cls.manifest = generate()
        cls.nodes = {n["id"]: n for n in cls.graph["nodes"]}
        cls.edges = {e["id"]: e for e in cls.graph["edges"]}
        cls.new_queries = [q for q in cls.queries if q["category"] == "problem_journey"]
        cls.answers = {a["id"]: a for a in cls.oracle}
        cls.sections = {}
        for path in SOURCES.glob("SG-*.md"):
            cls.sections.update(source_sections(path))

    def test_main_picker_is_ten_different_problems_not_repeated_vehicle_tests(self):
        starts = [q for q in self.queries if q["demo"] and q.get("turn", 0) == 0]
        self.assertEqual(len(starts), 10)
        self.assertEqual(len({q["question"] for q in starts}), 10)
        self.assertEqual(len({self.answers[q["id"]]["procedure_id"] for q in starts}), 10)
        self.assertFalse(any(q["demo"] for q in self.queries if q["category"] == "vehicle_applicability"))
        self.assertEqual(len({q["vehicle_id"] for q in starts}), 8)

    def test_new_paths_have_distinct_depths_and_independent_localisation_routes(self):
        terminal = [self.answers[q["id"]] for q in self.new_queries if q.get("turn") == 3]
        self.assertEqual(len(terminal), 7)
        self.assertTrue(all(a["status"] == "root_cause" for a in terminal))
        self.assertEqual({len(a["path"]) for a in terminal}, {4, 6, 8})
        self.assertEqual(len({a["target"] for a in terminal}), 7)
        roots = {a["target"] for a in self.oracle if a["status"] == "root_cause"
                 and a["procedure_id"].startswith("procedure-v42-")}
        self.assertEqual(len(roots), 10)

    def test_every_new_published_outcome_has_an_authored_positive_or_negative_case(self):
        covered = {eid for q in self.new_queries for eid in self.answers[q["id"]]["path"]}
        for edge in self.edges.values():
            if edge["procedure_id"].startswith("procedure-v42-") and edge["type"] == "RESULT":
                self.assertIn(edge["id"], covered, edge)

    def test_initial_and_partial_reports_never_establish_a_cause(self):
        for q in self.new_queries:
            if q.get("turn") == 0:
                self.assertEqual(self.answers[q["id"]]["status"], "next_action")
            if q.get("turn") == 2:
                self.assertEqual(self.answers[q["id"]]["status"], "clarify")
                self.assertEqual(self.nodes[self.answers[q["id"]]["target"]]["type"], "Action")
            public = raw_input(q)
            self.assertEqual(set(public), {"question", "vehicle_id", "vehicle", "evidence"})
            self.assertNotIn("customer_response", json.dumps(public))
            self.assertNotIn("expected", json.dumps(public))

    def test_source_text_drives_every_response_and_branch_not_a_second_rule_copy(self):
        for node in self.nodes.values():
            if not node.get("procedure_id", "").startswith("procedure-v42-"):
                continue
            section = node["source_reference"].split(":")[-1]
            body = self.sections[section]
            if node["type"] in {"Action", "RootCause"}:
                self.assertIn("Response: " + node["customer_response"], body)
                self.assertTrue(node["customer_response"].strip())
            if node["type"] == "Action":
                self.assertEqual(node["instruction"], body)
        for edge in self.edges.values():
            if edge["procedure_id"].startswith("procedure-v42-") and edge["type"] == "RESULT":
                body = self.sections[edge["source_reference"].split(":")[-1]]
                self.assertIn(edge["description"], body)
                self.assertIn(edge["selection_criteria"], body)
                self.assertIn(json.dumps(edge["rule"], separators=(",", ":")), body)
                self.assertEqual(edge["result_type"], self.nodes[edge["source"]]["result_type"])

    def test_source_applicability_cannot_silently_disagree_with_selected_vehicle(self):
        pack = json.loads(PROBLEMS.read_text())
        sections = copy.deepcopy(self.sections)
        sections["G5.0"] = sections["G5.0"].replace("Model B", "Model A")
        profile = {"key": "b21", "year": 2021, "model": "Model B", "configuration": "petrol"}
        with self.assertRaisesRegex(ValueError, "exact applicability"):
            extend_examples({"nodes": [], "edges": []}, [], [], [profile], sections, pack[:1])

    def test_safety_metadata_names_the_actual_applicable_vehicle(self):
        vehicles = {edge["source"]: self.nodes[edge["target"]]
                    for edge in self.edges.values() if edge["type"] == "APPLIES_TO"}
        for node in self.nodes.values():
            if node.get("procedure_id", "").startswith("procedure-v42-") and node["type"] in {"Procedure", "Action"}:
                self.assertIn("Brand X " + vehicles[node["procedure_id"]]["model"] + " is fictional.",
                              node["safety_metadata"])
