"""Command line: extract questions, audit visits, or serve the web demo."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import audit, catalog, extract
from .foundry import Foundry, FoundryError, load_config

ROOT = Path(__file__).resolve().parent.parent


def cmd_extract(args, config):
    deployment = config.get("extraction_deployment")
    if not deployment:
        raise ValueError("Configure extraction_deployment in config.local.json or EXTRACTION_DEPLOYMENT.")
    client = Foundry(config)
    for scenario_id in args.scenario or catalog.scenario_ids():
        scenario = catalog.load_scenario(scenario_id)
        for campaign_id, campaign in scenario["campaigns"].items():
            target = scenario["folder"] / "questions" / f"{campaign_id}.json"
            if target.exists() and not args.force:
                print(f"{scenario_id} {campaign_id}: exists, skipped (use --force to replace)", file=sys.stderr)
                continue
            result = extract.extract(client, scenario, campaign, deployment, args.reasoning_effort)
            target.parent.mkdir(exist_ok=True)
            target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"{scenario_id} {campaign_id}: {len(result['checks'])} checks, "
                  f"{len(result['not_checkable'])} not checkable, usage={result['extraction']['usage']}",
                  file=sys.stderr)


def cmd_audit(args, config):
    client = Foundry(config)
    report = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "rounds": []}
    for round_number in range(1, args.repeats + 1):
        results = []
        for scenario_id in args.scenario or catalog.scenario_ids():
            scenario = catalog.load_scenario(scenario_id)
            visits = [catalog.find_visit(scenario, v) for v in args.visit] if args.visit else scenario["visits"]
            results += audit.audit_many(client, scenario, visits, config["decision_deployment"])
        summary = audit.summarise(results)
        report["rounds"].append({"round": round_number, "summary": summary, "results": results})
        print(f"round {round_number}: {summary['matches']}/{summary['campaign_verdicts']} campaign verdicts "
              f"match (always-fail baseline {summary['always_fail_baseline']}), {summary['errors']} errors, "
              f"{summary['questions_asked']} questions, "
              f"{summary['input_tokens']} input tokens, ${summary['estimated_cost_usd']:.6f}", file=sys.stderr)
        for expected, bucket in sorted(summary["by_expected"].items()):
            print(f"  expected {expected}: {bucket['correct']}/{bucket['total']} correct, got {bucket['got']}",
                  file=sys.stderr)
        for miss in summary["mismatches"]:
            print(f"  mismatch {miss['scenario']} {miss['visit']} {miss['campaign']}: "
                  f"expected {miss['expected']}, got {miss['verdict']}", file=sys.stderr)
    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if all(not r["summary"]["errors"] for r in report["rounds"]) else 1


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m compliance", description=__doc__)
    parser.add_argument("--config", help="Path to a config file (default: config.local.json).")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("extract", help="Extract questions from policies with the extraction model (billable).")
    p.add_argument("--scenario", action="append", choices=catalog.scenario_ids())
    p.add_argument("--reasoning-effort", default="high", choices=["low", "medium", "high"])
    p.add_argument("--force", action="store_true", help="Replace existing question files.")
    p = sub.add_parser("audit", help="Audit visits with Decision-1.1 (billable).")
    p.add_argument("--scenario", action="append", choices=catalog.scenario_ids())
    p.add_argument("--visit", action="append", help="Visit id; requires exactly one --scenario.")
    p.add_argument("--repeats", type=int, default=1, choices=range(1, 6))
    p.add_argument("--output", help="Write the full report to this JSON file.")
    p = sub.add_parser("serve", help="Serve the web demo.")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8780)
    args = parser.parse_args(argv)
    if getattr(args, "visit", None) and len(args.scenario or []) != 1:
        parser.error("--visit requires exactly one --scenario.")
    try:
        config = load_config(args.config)
        if args.command == "extract":
            return cmd_extract(args, config) or 0
        if args.command == "audit":
            return cmd_audit(args, config)
        from .server import serve
        serve(config, args.host, args.port)
        return 0
    except (FoundryError, catalog.CatalogError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
