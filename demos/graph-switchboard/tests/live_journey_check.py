"""Actual staged Foundry/AGE acceptance, including same-lane context reuse."""

import argparse
import json
from pathlib import Path
from statistics import median
import urllib.request
import urllib.error


def get(url):
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def run(origin, output, selected=None, contrasts=False, vehicles=False, case_ids=None, all_cases=False, problems=False):
    output.mkdir(parents=True, exist_ok=False)
    catalog = get(origin + "/api/catalog")
    cases = [c for c in catalog["cases"] if all_cases or
             (c["category"] == "vehicle_applicability" if vehicles else
              c["category"] in ({"problem_journey"} if problems else {"staged_journey", "problem_journey"})
              and c["demo"] != contrasts)]
    if selected:
        cases = [c for c in cases if c.get("journey_id") == selected]
    if case_ids:
        if set(case_ids) - {case["id"] for case in cases}:
            raise AssertionError("Requested case does not exist in the selected suite.")
        cases = [case for case in cases if case["id"] in case_ids]
    if not cases:
        raise AssertionError("No matching journey.")
    data = Path(__file__).resolve().parents[1] / "data" / "traversal"
    manifest = json.loads((data / "manifest.json").read_text())
    if any(catalog["manifest"][key] != manifest[key] for key in
           ("graph_sha256", "queries_sha256", "oracle_sha256")):
        raise AssertionError("The service does not serve the frozen evaluation corpus.")
    fixtures = {item["id"]: item for item in (
        json.loads(line) for line in (data / "queries.jsonl").read_text().splitlines())}
    oracle = {item["id"]: item for item in (
        json.loads(line) for line in (data / "oracle.jsonl").read_text().splitlines())}
    (output / "corpus.json").write_text(json.dumps(catalog["manifest"], indent=2), encoding="utf-8")
    (output / "workflow.json").write_text(json.dumps({
        "workflow": catalog["workflow"], "decision": catalog["decision_deployment"],
        "sol": catalog["baseline_deployment"], "remaining_calls_at_start": catalog["remaining_calls"],
    }, indent=2), encoding="utf-8")
    summary, failures, operational_errors = [], [], []
    for first in cases:
        case, previous = first, None
        while True:
            request = urllib.request.Request(
                origin + "/api/run",
                data=json.dumps({"case_id": case["id"], "previous_run_id": previous}).encode(),
                headers={"Content-Type": "application/json", "Origin": origin},
            )
            try:
                with urllib.request.urlopen(request, timeout=240) as response:
                    events = [json.loads(line) for line in response if line.strip()]
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                error = {"case": case["id"], "error": str(exc), "next_case_not_run": case.get("next_case")}
                operational_errors.append(error)
                failures.append(case["id"] + "/transport-error")
                (output / "operational-errors.json").write_text(json.dumps(operational_errors, indent=2), encoding="utf-8")
                print(json.dumps(error), flush=True)
                break
            (output / (case["id"] + ".json")).write_text(json.dumps(events, indent=2), encoding="utf-8")
            results = [e for e in events if e["event"] == "complete"
                       and e.get("method") in {"decision", "llm-cypher"}]
            if len(results) != 2:
                failures.append(case["id"] + "/incomplete-lanes")
                operational_errors.append({"case": case["id"], "error": "Both lanes did not complete.",
                                           "next_case_not_run": case.get("next_case")})
                break
            entry = next((event["result"] for event in events if event["event"] == "entry_ready"), {})
            expected = oracle[case["id"]]
            expected_entry_status = expected.get("entry_expectation", {}).get("status") or (
                expected["status"] if expected["target"] is None else "resolved")
            expected_entry_target = fixtures[case["id"]]["start_node"] if expected_entry_status == "resolved" else None
            for result in results:
                item = {"case": case["id"], "lane": result["method"],
                        "group": case["intent"], "score": result["score"],
                        "invalid_graph_reads": sum(
                            event.get("event") == "graph_result" and "error" in event
                            for event in events if event.get("method") in (
                                {"decision", "entry"} if result["method"] == "decision" else {"llm-cypher"}
                            )),
                        "status": result["result"]["status"], "target": result["result"].get("target"),
                        "exact": result["score"]["exact"], "calls": result["inference_calls"],
                        "models": result["model_calls_by_deployment"],
                        "cost": result["estimated_cost_usd"], "elapsed_ms": result["elapsed_ms"],
                        "entry_status": entry.get("status") if result["method"] == "decision" else None,
                        "entry_status_correct": entry.get("status") == expected_entry_status
                            if result["method"] == "decision" else None,
                        "entry_target_correct": entry.get("target") == expected_entry_target
                            if result["method"] == "decision" else None}
                summary.append(item)
                print(json.dumps(item), flush=True)
                if not item["exact"]:
                    failures.append(f"{item['case']}/{item['lane']}")
                if item["lane"] == "decision":
                    if item["models"].get(catalog["baseline_deployment"], 0):
                        failures.append(case["id"] + "/unexpected-Sol-in-MD1-lane")
                    if result["entry_metrics"]["inference_calls"] > 1:
                        failures.append(case["id"] + "/entry-call-limit")
            (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            if any(r["result"]["status"] == "error" for r in results):
                operational_errors.append({"case": case["id"], "error": "Model error; raw evidence retained.",
                                           "next_case_not_run": case.get("next_case")})
                break
            if not case.get("next_case"):
                break
            previous = results[0]["run_id"]
            case = get(origin + "/api/release/" + previous)
    groups = {}
    for item in summary:
        group = groups.setdefault(item["group"] + "/" + item["lane"],
                                  {"cases": 0, "exact": 0, "target_correct": 0,
                                   "wrong_transition": 0, "invalid_graph_reads": 0})
        group["cases"] += 1
        group["exact"] += item["exact"]
        for field in ("target_correct", "wrong_transition"):
            group[field] += item["score"][field]
        group["invalid_graph_reads"] += item["invalid_graph_reads"]
        if item["lane"] == "decision":
            group["entry_status_correct"] = group.get("entry_status_correct", 0) + item["entry_status_correct"]
            group["entry_target_correct"] = group.get("entry_target_correct", 0) + item["entry_target_correct"]
    for key, group in groups.items():
        rows = [item for item in summary if item["group"] + "/" + item["lane"] == key]
        group["calls"] = sum(item["calls"] for item in rows)
        group["median_elapsed_ms"] = median(item["elapsed_ms"] for item in rows)
        costs = [item["cost"] for item in rows]
        group["total_cost_usd"] = sum(costs) if all(value is not None for value in costs) else None
        group["median_cost_usd"] = median(costs) if all(value is not None for value in costs) else None
    (output / "groups.json").write_text(json.dumps(groups, indent=2), encoding="utf-8")
    (output / "operational-errors.json").write_text(json.dumps(operational_errors, indent=2), encoding="utf-8")
    if failures:
        raise AssertionError("Non-exact outcomes retained: " + ", ".join(failures))
    print(f"Passed {len(summary)} lane outcomes.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8766")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--journey", help="Filter by the published journey identifier.")
    parser.add_argument("--contrasts", action="store_true")
    parser.add_argument("--vehicles", action="store_true", help="Run the multi-vehicle applicability suite.")
    parser.add_argument("--problems", action="store_true", help="Run the seven additional problem families.")
    parser.add_argument("--all", action="store_true", dest="all_cases", help="Run every frozen snapshot.")
    parser.add_argument("--case", action="append", dest="case_ids", help="Run only these case IDs; repeatable.")
    args = parser.parse_args()
    if args.vehicles and (args.contrasts or args.journey or args.problems):
        parser.error("--vehicles cannot be combined with --contrasts or --journey")
    if args.all_cases and (args.vehicles or args.contrasts or args.journey or args.problems):
        parser.error("--all cannot be combined with suite selectors")
    run(args.url.rstrip("/"), args.output, args.journey, args.contrasts, args.vehicles, args.case_ids, args.all_cases, args.problems)
