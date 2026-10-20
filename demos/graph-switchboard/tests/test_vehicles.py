"""Independent semantic assertions for the authored vehicle schedule, not model accuracy."""

import json
import os
import unittest
from unittest.mock import Mock

from traversal.journeys import SOURCES, generate, validate
from traversal.foundry import ENTRY_DECISION_INSTRUCTIONS, InferenceError
from traversal.runtime import raw_input, resolve_decision_entry, validate_entry
from traversal.vehicles import vehicle_profiles
from test_traversal import MemoryGraph, ScriptedChoice


class VehicleCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph, queries, answers, cls.manifest = generate()
        cls.cases = {item["id"]: item for item in queries}
        cls.answers = {item["id"]: item for item in answers}
        cls.nodes = {item["id"]: item for item in cls.graph["nodes"]}
        cls.store = MemoryGraph(cls.graph)

    def test_ten_vehicles_preserve_three_base_procedures_and_explicit_additions(self):
        vehicles = [node for node in self.nodes.values() if node["type"] == "VehicleModel"]
        self.assertEqual(len(vehicles), 10)
        self.assertEqual(len(self.nodes), 417)
        self.assertEqual(len(self.graph["edges"]), 423)
        for vehicle in vehicles:
            owners = [edge["source"] for edge in self.graph["edges"]
                      if edge["type"] == "APPLIES_TO" and edge["target"] == vehicle["id"]]
            self.assertEqual(len([owner for owner in owners if owner.startswith("procedure-v4-")]), 3)
            self.assertEqual(len(owners), 3 if vehicle["model"] in {"Model A", "Model I", "Model J"} else 4)
            self.assertTrue(all(self.nodes[owner]["status"] == "published" for owner in owners))

    def test_matched_reports_differ_only_in_selected_vehicle(self):
        for pressure in (310, 500):
            cases = [query for query in self.cases.values()
                     if query.get("pair_group") == f"matched-pressure-{pressure}"]
            self.assertEqual(len(cases), 10)
            original = raw_input(cases[0])
            for case in cases:
                public = raw_input(case)
                self.assertEqual(public["question"], original["question"])
                self.assertEqual(public["evidence"], original["evidence"])
                self.assertNotIn("pair_group", public)
                self.assertNotIn("start_node", public)

    def test_pressure_routes_match_independently_authored_schedule(self):
        in_band = {
            310: {"a21", "c22", "e23", "i20"},
            500: {"b21", "d22", "f23", "g24", "j20"},
        }
        for pressure, inside in in_band.items():
            for key in ("a21", "b21", "c22", "d22", "e23", "f23", "g24", "h24", "i20", "j20"):
                answer = self.answers[f"vehicle-{key}-pressure-{pressure}"]
                description = self.nodes[answer["target"]]["description"].lower()
                self.assertEqual("localisation" in description, key in inside, (pressure, key))
                self.assertEqual("out-of-band" in description, key not in inside, (pressure, key))
                self.assertEqual(answer["status"], "next_action")

    def test_plug_first_changes_actual_entry_and_terminal_cause(self):
        for key, first, terminal in (("a21", "coil", "plug"), ("b21", "plug", "coil"),
                                     ("d22", "plug", "coil"), ("g24", "coil", "plug")):
            query = self.cases[f"vehicle-{key}-misfire-return"]
            first_action, = self.store.neighbors(query["start_node"])
            self.assertIn(first, first_action["node"]["description"].lower())
            answer = self.answers[query["id"]]
            self.assertIn(terminal, self.nodes[answer["target"]]["description"].lower())
            if first == "plug":
                self.assertIn("no earlier coil comparison is required", first_action["node"]["instruction"])

    def test_fan_patterns_and_pressure_rules_are_vehicle_specific(self):
        b = self.nodes["procedure-v4-airflow-a-pattern-b21"]["instruction"]
        a = self.nodes["procedure-v4-airflow-a-pattern"]["instruction"]
        self.assertIn("absent at stages 1-2", b)
        self.assertIn("stages 3-4", b)
        self.assertIn("stages 1, 2 and 3", a)
        pressure = self.nodes["procedure-v4-lean-a-pressure-b21"]["instruction"]
        self.assertIn("450 through 600 kPa", pressure)
        self.assertNotIn("250 through 400", pressure)
        self.assertIn("5.25 bar", pressure)

    def test_cross_vehicle_paths_are_rejected(self):
        entry = self.nodes[self.cases["vehicle-a21-pressure-310"]["start_node"]]
        with self.assertRaisesRegex(ValueError, "applicability"):
            validate_entry(self.store, entry, self.cases["vehicle-b21-pressure-310"]["vehicle_id"])
        graph, queries, answers, _ = generate()
        case = next(query for query in queries if query["id"] == "vehicle-b21-pressure-310")
        case["vehicle_id"] = self.cases["vehicle-a21-pressure-310"]["vehicle_id"]
        with self.assertRaisesRegex(ValueError, "vehicle context"):
            validate(graph, queries, answers)

    def test_no_hidden_resolved_vehicle_for_missing_identity(self):
        for identifier in ("vehicle-missing", "vehicle-model-missing", "vehicle-year-missing"):
            query = self.cases[identifier]
            self.assertEqual(raw_input(query)["vehicle_id"], "")
            self.assertIsNone(query["start_node"])
            self.assertEqual(self.answers[identifier]["status"], "clarify")
            self.assertEqual(self.answers[identifier]["path"], [])
        for identifier in ("vehicle-context-conflict", "vehicle-unsupported-year",
                           "vehicle-unsupported-model", "vehicle-unsupported-configuration"):
            self.assertIsNone(self.answers[identifier]["target"])
            self.assertEqual(self.answers[identifier]["path"], [])

    def test_schedule_rejects_unreviewed_changes_to_original_journeys(self):
        source = (SOURCES / "SG-04-vehicle-applicability.md").read_text(encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "original staged"):
            vehicle_profiles(source.replace("| 250 | 400 |", "| 250 | 401 |"))
        with self.assertRaisesRegex(ValueError, "ten uniquely"):
            vehicle_profiles("\n".join(line for line in source.splitlines() if not line.startswith("| j20 |")))

    def test_future_and_reviewer_metadata_never_enters_public_inputs(self):
        for query in self.cases.values():
            public = raw_input(query)
            self.assertEqual(set(public), {"vehicle", "vehicle_id", "question", "evidence"})
            for field in ("pair_group", "split", "intent", "category", "start_node", "expected"):
                self.assertNotIn(field, public)
        self.assertFalse(self.manifest["applicability_evaluation"]["independent_test_set"])

    def test_review_regression_no_stale_variant_joint_or_fan_rules(self):
        for key, joint in (("b21", "L"), ("c22", "M"), ("d22", "N"), ("e23", "P"),
                           ("f23", "Q"), ("g24", "R"), ("h24", "S"), ("i20", "T"), ("j20", "U")):
            text = self.nodes[f"procedure-v4-lean-a-localisation-{key}"]["instruction"]
            self.assertNotIn("to J.", text)
            self.assertIn("to " + joint + ".", text)
        for key in ("b21", "c22", "f23", "g24", "j20"):
            for node in self.nodes.values():
                if node.get("procedure_id") == "procedure-v4-airflow-" + key:
                    text = json.dumps(node)
                    self.assertNotIn("1, 2 and 3", text, node["id"])
                    self.assertNotIn("1-3", text, node["id"])
                    self.assertNotIn("stage 4", text, node["id"])

    def test_review_regression_no_expected_status_in_public_identity(self):
        for query in self.cases.values():
            identity = raw_input(query)["vehicle_id"]
            self.assertFalse(any(word in identity for word in ("unsupported", "clarify", "root_cause", "next_action")))

    def test_review_regression_same_report_can_change_order_and_fan_route(self):
        for suffix, a_target, b_target in (
            ("coil-only", "ignition-coil fault", "plug comparison"),
            ("fan-1-3", "control-unit comparison", "unhandled fan-stage pattern"),
            ("fan-1-2", "unhandled fan-stage pattern", "control-unit comparison"),
        ):
            a, b = self.cases["vehicle-a21-" + suffix], self.cases["vehicle-b21-" + suffix]
            self.assertEqual(a["question"], b["question"])
            self.assertEqual(a["evidence"], b["evidence"])
            for query, target in ((a, a_target), (b, b_target)):
                answer = self.answers[query["id"]]
                self.assertIn(target, self.nodes[answer["target"]]["description"])
        self.assertEqual(self.answers["vehicle-a21-coil-only"]["status"], "root_cause")
        self.assertEqual(self.answers["vehicle-b21-coil-only"]["status"], "next_action")

    def test_independent_terminal_semantics_for_every_vehicle(self):
        expected = {
            "a21": ("one", "spark-plug", "J"), "b21": ("one", "ignition-coil", "L"),
            "c22": ("two", "spark-plug", "M"), "d22": ("three", "ignition-coil", "N"),
            "e23": ("one", "spark-plug", "P"), "f23": ("two", "spark-plug", "Q"),
            "g24": ("three", "spark-plug", "R"), "h24": ("four", "ignition-coil", "S"),
            "i20": ("two", "ignition-coil", "T"), "j20": ("four", "ignition-coil", "U"),
        }
        for key, (cylinder, component, joint) in expected.items():
            for suffix, description in (
                ("misfire-return", f"Cylinder-{cylinder} {component} fault"),
                ("lean-return", "Unmetered-air leak at intake joint " + joint),
                ("airflow-return", "Original low-speed fan control-unit fault"),
            ):
                answer = self.answers[f"vehicle-{key}-{suffix}"]
                self.assertEqual(answer["status"], "root_cause")
                self.assertEqual(self.nodes[answer["target"]]["description"], description)
                self.assertEqual(len(answer["path"]), 4)


class DecisionEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, queries, _, _ = generate()
        cls.query = next(query for query in queries if query["id"] == "vehicle-a21-pressure-310")
        cls.memory = MemoryGraph(cls.data)
        cls.rows = []
        for applicability in cls.data["edges"]:
            if applicability["type"] != "APPLIES_TO" or applicability["target"] != cls.query["vehicle_id"]:
                continue
            procedure = cls.memory.nodes[applicability["source"]]
            for edge in cls.data["edges"]:
                if edge["type"] == "ENTRY_POINT" and edge["source"] == procedure["id"]:
                    cls.rows.append({"procedure": procedure,
                                     "vehicle": cls.memory.nodes[applicability["target"]],
                                     "entry_condition": cls.memory.nodes[edge["target"]],
                                     "applicability_edge": applicability, "entry_edge": edge})

    def fixtures(self, choice=None, probability=1.0):
        graph = Mock(wraps=self.memory)
        graph.entries = Mock(return_value=self.rows)
        graph.is_entry = lambda node: any(edge["type"] == "ENTRY_POINT" and edge["target"] == node["id"]
                                         for edge in self.data["edges"])
        model = Mock()
        selected = choice or self.query["start_node"]

        def choose(state, options, *, instructions):
            return selected, {key: probability if key == selected else (1 - probability) / (len(options) - 1)
                              for key in options}

        model.choose.side_effect = choose
        return graph, model

    def test_md1_selects_only_from_actual_entries_without_sol_or_fixture_hints(self):
        graph, model = self.fixtures()
        events = []
        result = resolve_decision_entry(graph, model, self.query, emit=events.append)
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["target"], self.query["start_node"])
        self.assertEqual(result["resolver"], "md1")
        state, options = model.choose.call_args.args
        self.assertEqual(state, raw_input(self.query))
        self.assertEqual(len(options), 5)
        self.assertEqual(set(options) - {"__clarify__", "__unsupported__"},
                         {row["entry_condition"]["id"] for row in self.rows})
        self.assertTrue(all(json.loads(value)["procedure"]["entry_criteria"]
                            for key, value in options.items() if not key.startswith("__")))
        self.assertEqual(model.choose.call_args.kwargs["instructions"], ENTRY_DECISION_INSTRUCTIONS)
        model.choose.assert_called_once()
        model.chat.assert_not_called()
        graph.entries.assert_called_once_with(self.query["vehicle"])
        self.assertEqual(events[-1]["event"], "entry_selected")

    def test_missing_vehicle_fields_remain_unknown_without_graph_or_model_call(self):
        for vehicle in ({}, None, {"make": "Brand X", "model": "Model A"}):
            graph, model = self.fixtures()
            result = resolve_decision_entry(graph, model, {**self.query, "vehicle": vehicle})
            self.assertEqual(result["status"], "clarify")
            graph.entries.assert_not_called()
            model.choose.assert_not_called()
            self.assertIn("year", result["reason"])

    def test_no_applicable_entries_is_unsupported_without_a_model_call(self):
        graph, model = self.fixtures()
        graph.entries.return_value = []
        result = resolve_decision_entry(graph, model, self.query)
        self.assertEqual(result["status"], "unsupported")
        model.choose.assert_not_called()

    def test_explicit_abstentions_and_low_confidence_do_not_start_traversal(self):
        for choice, probability, threshold, status in (
            ("__clarify__", 1.0, 0, "clarify"),
            ("__unsupported__", 1.0, 0, "unsupported"),
            (None, .4, .5, "clarify"),
            ("__unsupported__", .4, .5, "clarify"),
        ):
            graph, model = self.fixtures(choice, probability)
            result = resolve_decision_entry(graph, model, self.query, threshold=threshold)
            self.assertEqual(result["status"], status)
            self.assertIsNone(result["target"])
            graph.eligible.assert_not_called()

    def test_choice_not_in_the_actual_menu_is_an_explicit_error(self):
        graph, model = self.fixtures()
        model.choose.return_value = ("foreign", {"foreign": 1.0})
        model.choose.side_effect = None
        with self.assertRaisesRegex(InferenceError, "outside"):
            resolve_decision_entry(graph, model, self.query)

    def test_returned_entry_still_requires_publication_and_vehicle_validation(self):
        graph, model = self.fixtures()
        graph.eligible.return_value = False
        with self.assertRaisesRegex(ValueError, "applicability"):
            resolve_decision_entry(graph, model, self.query)


@unittest.skipUnless(os.environ.get("AGE_INTEGRATION") == "1",
                     "Set AGE_INTEGRATION=1 for the real expanded-graph checks.")
class RealVehicleGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from traversal.__main__ import database_url
        from traversal.age import AgeGraph, load_graph
        cls.graph, cls.queries, answers, _ = generate()
        cls.answers = {answer["id"]: answer for answer in answers}
        cls.nodes = {node["id"]: node for node in cls.graph["nodes"]}
        cls.edges = {edge["id"]: edge for edge in cls.graph["edges"]}
        dsn = database_url()
        cls.store = AgeGraph(dsn, load_graph(dsn, cls.graph))

    @classmethod
    def tearDownClass(cls):
        cls.store.close()

    def test_entire_expanded_graph_matches_actual_stored_properties(self):
        self.store.verify(self.graph)

    def test_fixed_entry_query_returns_all_and_only_published_vehicle_entries(self):
        vehicles = [node for node in self.graph["nodes"] if node["type"] == "VehicleModel"]
        for vehicle in vehicles:
            filters = {**vehicle, "year": vehicle["model_year"]}
            rows = self.store.entries(filters)
            self.assertEqual(len(rows), 3 if vehicle["model"] in {"Model A", "Model I", "Model J"} else 4)
            self.assertTrue(all(row["vehicle"]["id"] == vehicle["id"] for row in rows))
            self.assertTrue(all(row["procedure"]["status"] == "published" for row in rows))
            self.assertTrue(all(row["entry_condition"]["type"] == "Condition" for row in rows))
        self.assertEqual(self.store.entries({**filters, "model": "Model Z"}), [])

    def test_all_resolved_authored_paths_execute_over_real_age(self):
        from traversal.runtime import decision_walk
        for query in self.queries:
            answer = self.answers[query["id"]]
            if answer["target"] is None:
                continue
            choices = [identifier for identifier in answer["path"]
                       if self.edges[identifier]["type"] == "RESULT"]
            if answer["status"] != "root_cause" and not self.nodes[answer["target"]].get("handoff"):
                choices.append("__clarify__" if answer["status"] == "clarify" else "__next_action__")
            result = decision_walk(self.store, ScriptedChoice(choices), query)
            for field in ("status", "target", "path"):
                self.assertEqual(result[field], answer[field], query["id"])


if __name__ == "__main__":
    unittest.main()
