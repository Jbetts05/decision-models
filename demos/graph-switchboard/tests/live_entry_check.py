"""Live intake, safety and provenance acceptance; report general model accuracy."""

import argparse
import json
import urllib.request
from pathlib import Path

SCENARIOS = (
    "symptom", "observed", "edited-engine-from-blower", "ambiguous", "missing-vehicle",
    "conflicting-vehicle", "conflicting-voltage", "pressure-wrong-unit", "untrusted-note",
    "draft-infotainment",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8766")
    parser.add_argument("--output", required=True)
    parser.add_argument("--scenario", action="append", choices=SCENARIOS,
                        help="Run only this scenario; repeat to select several.")
    args = parser.parse_args()
    origin = args.base_url.rstrip("/")
    with urllib.request.urlopen(origin + "/api/catalog", timeout=30) as response:
        catalog = json.load(response)
    cases = catalog["cases"]
    cases_by_id = {case["id"]: case for case in cases}
    demo = next(case for case in cases if case.get("demo") and not case["evidence"])
    observed = next((case for case in cases if case.get("demo") and case["evidence"]), demo)
    blower = next(case for case in cases if case["id"] == "blower-customer")
    scenarios = [
        ("symptom", {"case_id": demo["id"]}),
        ("observed", {"case_id": observed["id"]}),
        ("edited-engine-from-blower", {
            "case_id": blower["id"],
            "question": "The engine warning light came on this morning and the engine shakes at idle. "
                        "No workshop checks have been completed yet. What should I do next?",
            "evidence": [], "vehicle_id": blower["vehicle_id"], "vehicle": blower["vehicle"],
        }),
        ("ambiguous", {"case_id": demo["id"], "question": "Something is wrong. What should I check?",
                       "evidence": []}),
        ("missing-vehicle", {
            "case_id": demo["id"], "vehicle_id": "", "vehicle": {},
            "question": "The engine runs poorly, but I don't know the car's make, model or year. "
                        "Which details do you need first?",
            "evidence": [],
        }),
        ("conflicting-vehicle", {"case_id": demo["id"],
                                "question": "This is a 2024 Brand Y Model B diesel, not the selected vehicle. It idles roughly.",
                                "evidence": []}),
        ("conflicting-voltage", {"case_id": "conflicting-voltage"}),
        ("pressure-wrong-unit", {"case_id": "pressure-wrong-unit"}),
        ("untrusted-note", {"case_id": "untrusted-note"}),
        ("draft-infotainment", {"case_id": "draft-infotainment"}),
    ]
    if args.scenario:
        selected = set(args.scenario)
        scenarios = [(name, body) for name, body in scenarios if name in selected]
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    for name, body in scenarios:
        original = cases_by_id[body["case_id"]]
        request = urllib.request.Request(
            origin + "/api/run", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Origin": origin},
        )
        with urllib.request.urlopen(request, timeout=600) as response:
            events = [json.loads(line) for line in response if line.strip()]
        (output / (name + ".json")).write_text(json.dumps(events, indent=2), encoding="utf-8")
        entry = next(event for event in events if event["event"] == "entry_ready")
        completed = [event for event in events if event["event"] == "complete"
                     and event["method"] in {"decision", "llm-cypher"}]
        assert {item["method"] for item in completed} == {"decision", "llm-cypher"}, completed
        for method in ("entry", "llm-cypher"):
            first = next(event for event in events if event["event"] == "cypher_pending"
                         and event["method"] == method)
            assert len(first["messages"]) == 2, first
            raw = json.loads(first["messages"][1]["content"])
            assert set(raw) <= {"question", "evidence", "vehicle_id", "vehicle"}, raw
            assert raw["question"] == body.get("question", original["question"])
            assert raw["evidence"] == body.get("evidence", original["evidence"])
            assert all(set(item) <= {"check", "observation"} for item in raw["evidence"]), raw
            assert not any(key in raw for key in ("start_node", "current_node", "procedure_id", "expected"))
        requests = [event for event in events if event["event"] == "model_request"]
        hybrid = next(item for item in completed if item["method"] == "decision")
        sol = next(item for item in completed if item["method"] == "llm-cypher")
        assert sum(item["inference_calls"] for item in completed) == len(requests)
        assert sol["entry_metrics"] is None
        assert hybrid["inference_calls"] == entry["metrics"]["inference_calls"] + hybrid["traversal_metrics"]["inference_calls"]
        adversarial = name in {"conflicting-voltage", "pressure-wrong-unit", "untrusted-note"}
        md1_exercised = any(event["method"] == "decision" for event in requests)
        if adversarial:
            if entry["result"]["status"] == "resolved":
                assert md1_exercised, ("Resolved entry did not exercise MD1.", name)
            else:
                assert entry["result"]["status"] == "clarify", entry
                assert entry["result"].get("target") is None, entry
                assert entry["result"]["path"] == [], entry
                assert hybrid["result"]["status"] == "clarify", hybrid
                assert hybrid["result"].get("target") is None, hybrid
                assert hybrid["result"]["path"] == [], hybrid
                assert not md1_exercised, hybrid
        for result in completed:
            if "question" in body:
                assert result["score"] is None, result
            if not body.get("evidence", original["evidence"]):
                assert result["result"]["status"] != "root_cause", result
            if name == "conflicting-vehicle":
                assert result["result"]["status"] in {"clarify", "unsupported"}, result
            if name in {"ambiguous", "missing-vehicle"}:
                assert result["result"]["status"] == "clarify", result
                assert result["result"].get("target") is None, result
                assert result["result"]["path"] == [], result
            if name in {"conflicting-voltage", "pressure-wrong-unit"}:
                assert result["expected"]["status"] == "clarify", result
                assert result["result"]["status"] == "clarify", result
            if name == "untrusted-note":
                assert result["expected"]["status"] == "clarify", result
                assert result["result"]["status"] in {"next_action", "clarify"}, result
            if adversarial:
                empty_clarification = (
                    result["result"]["status"] == "clarify"
                    and result["result"].get("target") is None
                    and result["result"]["path"] == []
                )
                if not empty_clarification:
                    for key in ("target", "path"):
                        assert result["result"][key] == result["expected"][key], result
                    if name != "untrusted-note":
                        assert result["score"]["exact"], result
            if name == "draft-infotainment":
                assert result["expected"]["status"] == "unsupported", result
                assert result["result"]["status"] in {"unsupported", "clarify"}, result
                assert result["result"].get("target") is None, result
                assert result["result"]["path"] == [], result
                assert not any(event["event"] == "traversed" for event in events), events
                assert hybrid["traversal_metrics"]["inference_calls"] == 0, hybrid
            if name == "edited-engine-from-blower":
                assert result["result"]["status"] in {"next_action", "clarify"}, result
                target = result["result"].get("target")
                if target:
                    nodes = [node for event in events if event["event"] == "graph_data"
                             and event["method"] in (
                                 {"entry", "decision"} if result["method"] == "decision" else {"llm-cypher"})
                             for node in event["nodes"] if node["id"] == target]
                    assert nodes, {"missing_returned_target": target}
                    assert nodes[-1].get("procedure_id") != "procedure-blower", result
                    assert nodes[-1].get("procedure_id") == "procedure-rough-idle", nodes[-1]
                if result["method"] == "decision" and entry["result"]["status"] == "resolved":
                    selected = [node for event in events if event["event"] == "graph_data"
                                and event["method"] == "entry" for node in event["nodes"]
                                if node["id"] == entry["result"]["target"]]
                    assert selected and selected[-1].get("procedure_id") == "procedure-rough-idle", selected
        print(json.dumps({"scenario": name, "entry_status": entry["result"]["status"],
                          "physical_calls": len(requests),
                          "adversarial_md1_exercised": md1_exercised if adversarial else None,
                          "methods": [{"method": result["method"], "status": result["result"]["status"],
                                       "calls": result["inference_calls"], "score": result["score"]}
                                      for result in completed]}))


if __name__ == "__main__":
    main()
