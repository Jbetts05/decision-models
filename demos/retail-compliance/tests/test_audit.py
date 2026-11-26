import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from compliance import audit, catalog  # noqa: E402
from compliance.foundry import FoundryError  # noqa: E402


def answer(choice, p=0.9):
    rest = (1 - p) / 2
    return {"type": "choice", "choice": choice,
            "probabilities": {o: (p if o == choice else rest) for o in audit.OPTIONS}}


class FakeClient:
    def __init__(self, choose=lambda key: "compliant"):
        self.choose, self.bodies = choose, []

    def post(self, path, body):
        assert path == audit.DECISION_PATH
        self.bodies.append(body)
        answers = {key: answer(self.choose(key)) for key in body["questions"]}
        return {"model": "microsoft-decision-1.1", "answers": answers,
                "usage": {"input_tokens": 1000, "output_tokens": len(answers)}}, 12.5


class CatalogTests(unittest.TestCase):
    def test_every_scenario_loads_with_approved_questions(self):
        for scenario_id in catalog.scenario_ids():
            scenario = catalog.load_scenario(scenario_id)
            for campaign in scenario["campaigns"].values():
                self.assertIn("questions", campaign)
                self.assertEqual(campaign["questions"]["review"]["status"], "approved")
            for visit in scenario["visits"]:
                for path in visit["photo_paths"].values():
                    self.assertTrue(path.is_file(), path)

    def test_invalid_questions_are_rejected(self):
        good = {"checks": [{"id": "a", "rule": "r", "requirement": "q", "question": "q", "compliant": "y",
                            "not_compliant": "n", "photos": ["bay"], "uses_reference": False}]}
        catalog.validate_questions(good, {"bay": ""}, "A")
        for mutate in (lambda c: c.update(photos=["unknown"]), lambda c: c.update(id="Bad Id"),
                       lambda c: c.update(question=""), lambda c: c.update(uses_reference="yes")):
            bad = json.loads(json.dumps(good))
            mutate(bad["checks"][0])
            with self.assertRaises(catalog.CatalogError):
                catalog.validate_questions(bad, {"bay": ""}, "A")


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.scenario = catalog.load_scenario("coffee-shelf")

    def visit(self, visit_id):
        return catalog.find_visit(self.scenario, visit_id)

    def test_questions_reference_only_their_own_photos(self):
        visit = self.visit("05")
        plan = audit.plan_visit(self.scenario, visit)
        body = audit.build_request(self.scenario, visit, plan, "dep")
        self.assertNotIn("image:", body["state"])
        for item in plan:
            if item["asked"]:
                text = body["questions"][item["key"]]["instructions"]
                for photo_type in visit["photo_paths"]:
                    self.assertEqual(f"image:{photo_type}.jpg" in text, photo_type in item["photos"])
        self.assertLessEqual(len(body["assets"]), audit.MAX_IMAGES_PER_CALL)
        self.assertTrue(all(q["criteria"]["cannot_assess"] == audit.CANNOT_ASSESS for q in body["questions"].values()))

    def test_missing_photo_is_cannot_assess_without_asking(self):
        visit = self.visit("04")  # no top close-up
        client = FakeClient()
        result = audit.audit_visit(client, self.scenario, visit, "dep")
        skipped = [c for c in result["checks"] if not c["asked"]]
        self.assertTrue(skipped)
        self.assertTrue(all(c["outcome"] == "cannot_assess" and "top" in c["reason"] for c in skipped))
        self.assertTrue(all(audit.question_key(c["campaign"], c["id"]) not in client.bodies[0]["questions"]
                            for c in skipped))
        self.assertEqual(result["campaigns"]["C"]["verdict"], "cannot_assess")

    def test_verdict_rule(self):
        self.assertEqual(audit.verdict(["compliant", "cannot_assess", "not_compliant"]), "fail")
        self.assertEqual(audit.verdict(["compliant", "cannot_assess"]), "cannot_assess")
        self.assertEqual(audit.verdict(["compliant"]), "pass")

    def test_single_failed_check_fails_only_its_campaign(self):
        key = audit.question_key("A", "original_price_label")
        client = FakeClient(lambda k: "not_compliant" if k == key else "compliant")
        result = audit.audit_visit(client, self.scenario, self.visit("01"), "dep")
        self.assertEqual(result["campaigns"]["A"]["verdict"], "fail")
        self.assertEqual(result["campaigns"]["A"]["failed"], ["original_price_label"])
        self.assertEqual(result["campaigns"]["C"]["verdict"], "pass")
        self.assertAlmostEqual(result["estimated_cost_usd"], 1000 * 0.042 / 1_000_000)

    def test_low_confidence_answers_go_to_review(self):
        key = audit.question_key("A", "original_price_label")

        class Unsure(FakeClient):
            def post(self, path, body):
                payload, ms = super().post(path, body)
                payload["answers"][key] = {"type": "choice", "choice": "not_compliant",
                                           "probabilities": {"compliant": 0.3, "not_compliant": 0.4, "cannot_assess": 0.3}}
                return payload, ms
        result = audit.audit_visit(Unsure(), self.scenario, self.visit("01"), "dep")
        row = next(c for c in result["checks"] if c["campaign"] == "A" and c["id"] == "original_price_label")
        self.assertEqual((row["outcome"], row["model_leaning"]), ("cannot_assess", "not_compliant"))
        self.assertEqual(result["campaigns"]["A"]["verdict"], "cannot_assess")

    def test_low_confidence_gate_uses_unrounded_probability(self):
        key = audit.question_key("A", "original_price_label")

        class Edge(FakeClient):
            def post(self, path, body):
                payload, ms = super().post(path, body)
                payload["answers"][key] = {"type": "choice", "choice": "compliant",
                                           "probabilities": {"compliant": 0.49996, "not_compliant": 0.3, "cannot_assess": 0.20004}}
                return payload, ms
        result = audit.audit_visit(Edge(), self.scenario, self.visit("01"), "dep")
        row = next(c for c in result["checks"] if c["campaign"] == "A" and c["id"] == "original_price_label")
        self.assertEqual(row["outcome"], "cannot_assess")

    def test_malformed_answers_are_rejected(self):
        for bad in ({"type": "choice", "choice": "maybe", "probabilities": {}},
                    {"type": "noul", "noul": 0.5},
                    {"type": "choice", "choice": "compliant",
                     "probabilities": {"compliant": 0.9, "not_compliant": 0.9, "cannot_assess": 0.1}}):
            with self.assertRaises(FoundryError):
                audit.read_answer(bad)

    def test_missing_answers_raise(self):
        class Partial(FakeClient):
            def post(self, path, body):
                payload, ms = super().post(path, body)
                payload["answers"].popitem()
                return payload, ms
        with self.assertRaises(FoundryError):
            audit.audit_visit(Partial(), self.scenario, self.visit("01"), "dep")

    def test_reference_image_is_added_for_lookbook_checks(self):
        scenario = catalog.load_scenario("clothing-display")
        visit = catalog.find_visit(scenario, "01")
        plan = audit.plan_visit(scenario, visit)
        body = audit.build_request(scenario, visit, plan, "dep")
        self.assertIn("reference_a.jpg", body["assets"])
        self.assertIn("reference_b.jpg", body["assets"])
        ref_questions = [item for item in plan if item["reference"]]
        self.assertTrue(ref_questions)
        for item in ref_questions:
            ref = "reference_" + item["campaign"].lower() + ".jpg"
            self.assertIn(f"image:{ref}", body["questions"][item["key"]]["instructions"])

    def test_audit_many_reports_errors_per_visit(self):
        class Failing(FakeClient):
            def post(self, path, body):
                raise FoundryError("boom")
        results = audit.audit_many(Failing(), self.scenario, self.scenario["visits"][:2], "dep")
        self.assertEqual([r["error"] for r in results], ["boom", "boom"])
        self.assertEqual(audit.summarise(results)["errors"], 2)


if __name__ == "__main__":
    unittest.main()
