"""Paired synthetic-query evaluation. Oracles are loaded only by the scorer."""

import json
import math
import random
import statistics
import time
from collections import Counter
from pathlib import Path

import psycopg

from traversal.foundry import InferenceError
from traversal.runtime import decision_walk, llm_cypher
from traversal.synthetic import canonical_hash, dump


def read_lines(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def sample_queries(queries, split, limit, seed):
    pool = [q for q in queries if q["split"] == split]
    if not pool:
        raise ValueError("No queries for the requested split.")
    if not 1 <= limit <= len(pool):
        raise ValueError(f"limit must be between 1 and {len(pool)} for this split.")
    # Round-robin shuffled categories, not the first N adjacent template variants.
    rng = random.Random(seed)
    categories = sorted({q["category"] for q in pool})
    rng.shuffle(categories)
    buckets = {category: [q for q in pool if q["category"] == category] for category in categories}
    for bucket in buckets.values():
        rng.shuffle(bucket)
    selected = []
    while len(selected) < limit:
        for category in categories:
            if buckets[category]:
                selected.append(buckets[category].pop())
                if len(selected) == limit:
                    break
    return selected


def score(result, oracle):
    path = result.get("path", [])
    expected = oracle["path"]
    return {
        "exact": all(result.get(key) == oracle[key] for key in ("status", "target", "path")),
        "target_correct": result.get("target") == oracle["target"] and result.get("status") == oracle["status"],
        "wrong_transition": any(i >= len(expected) or edge != expected[i] for i, edge in enumerate(path)),
        "expected_status": oracle["status"],
    }


def wilson(correct, total):
    if not total:
        return None
    z = 1.96
    p = correct / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    spread = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [round(max(0, center - spread), 4), round(min(1, center + spread), 4)]


def summarize(records):
    summaries = {}
    for method in sorted({r["method"] for r in records}):
        subset = [r for r in records if r["method"] == method]
        modeled = [r for r in subset if r["calls"]]
        latencies = sorted(r["elapsed_ms"] for r in modeled)
        abstention = [r for r in modeled if r["score"]["expected_status"] == "clarify"]
        complete = [r for r in modeled if r["score"]["expected_status"] == "root_cause"]
        call_records = [call for r in subset for call in r["calls"]]
        costs = [c["estimated_cost_usd"] for c in call_records]
        summaries[method] = {
            "cases": len(subset), "modeled_cases": len(modeled),
            "policy_only_cases": len(subset) - len(modeled),
            "exact_correct": sum(r["score"]["exact"] for r in subset),
            "modeled_exact_correct": sum(r["score"]["exact"] for r in modeled),
            "modeled_exact_accuracy": sum(r["score"]["exact"] for r in modeled) / len(modeled) if modeled else None,
            "modeled_exact_wilson_95": wilson(sum(r["score"]["exact"] for r in modeled), len(modeled)),
            "wrong_path_cases": sum(r["score"]["wrong_transition"] for r in modeled),
            "clarify_cases": len(abstention),
            "correct_clarifications": sum(r["score"]["exact"] for r in abstention),
            "root_cause_cases": len(complete),
            "correct_complete_paths": sum(r["score"]["exact"] for r in complete),
            "errors": sum(r["result"]["status"] == "error" for r in subset),
            "p50_modeled_elapsed_ms": statistics.median(latencies) if latencies else None,
            "p95_modeled_elapsed_ms": latencies[math.ceil(0.95 * len(latencies)) - 1] if latencies else None,
            "inference_calls": len(call_records),
            "input_tokens_reported": sum(c["usage"]["input_tokens"] for c in call_records if c["usage"]),
            "output_tokens_reported": sum(c["usage"]["output_tokens"] for c in call_records if c["usage"]),
            "calls_without_usage": sum(c["usage"] is None for c in call_records),
            "estimated_cost_usd": sum(costs) if costs and all(c is not None for c in costs) else None,
            "categories": {
                category: {"cases": sum(r["category"] == category for r in subset),
                           "exact": sum(r["category"] == category and r["score"]["exact"] for r in subset)}
                for category in sorted({r["category"] for r in subset})
            },
        }
    paired = {}
    if set(summaries) == {"decision", "llm-cypher"}:
        by_case = {}
        for record in records:
            by_case.setdefault(record["query_id"], {})[record["method"]] = record
        counts = Counter()
        for pair in by_case.values():
            if len(pair) == 2 and any(r["calls"] for r in pair.values()):
                counts[(pair["decision"]["score"]["exact"], pair["llm-cypher"]["score"]["exact"])] += 1
        paired = {
            "both_correct": counts[(True, True)], "decision_only_correct": counts[(True, False)],
            "llm_only_correct": counts[(False, True)], "both_incorrect": counts[(False, False)],
        }
    return {"methods": summaries, "paired_modeled_cases": paired}


def evaluate(graph, model, queries, oracle, output, *, threshold=0.0, seed=7):
    directory = Path(output)
    directory.mkdir(parents=True, exist_ok=False)
    oracle = {row["id"]: row for row in oracle}
    records = []
    # Acquire credentials outside measured case time; no excluded paid warm-up calls.
    model.headers()
    rng = random.Random(seed)
    methods = ["decision", "llm-cypher"]
    with (directory / "records.jsonl").open("w", encoding="utf-8") as stream:
        for query in queries:
            order = methods.copy()
            rng.shuffle(order)
            for method in order:
                before = len(model.calls)
                before_queries, before_ms = graph.query_count, graph.query_ms
                started = time.perf_counter()
                try:
                    if method == "decision":
                        result = decision_walk(graph, model, query, threshold)
                    else:
                        result = llm_cypher(graph, model, query)
                except (InferenceError, ValueError, psycopg.Error) as exc:
                    result = {"status": "error", "target": None, "path": [], "error": str(exc)[:1500]}
                record = {
                    "query_id": query["id"], "category": query["category"], "split": query["split"],
                    "method": method, "result": result,
                    "score": score(result, oracle[query["id"]]),
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                    "graph_queries": graph.query_count - before_queries,
                    "graph_query_ms": round(graph.query_ms - before_ms, 3),
                    "calls": model.calls[before:],
                }
                records.append(record)
                stream.write(json.dumps(record) + "\n")
                stream.flush()
                print(f"{query['id']:30} {method:11} {result['status']:12} exact={record['score']['exact']}", flush=True)
    summary = summarize(records)
    summary.update({
        "source": "live_foundry_and_apache_age", "graph": graph.name,
        "selected_query_ids": [q["id"] for q in queries],
        "selected_queries_sha256": canonical_hash(queries),
        "threshold": threshold, "order_seed": seed,
        "decision_deployment": model.config["decision_deployment"],
        "baseline_deployment": model.config["baseline_deployment"],
        "baseline_reasoning_effort": model.config.get("baseline_reasoning_effort", "medium"),
        "pricing": model.config.get("pricing", {}),
        "limitations": [
            "Synthetic template-authored queries; not real technician sessions.",
            "Known starting nodes, mandatory actions, and supplied evidence; no entry retrieval or action-utility study.",
            "A smoke/sample run does not establish statistical equivalence or production reliability.",
            "Wilson intervals treat cases as independent; shared procedure/template correlations limit interpretation.",
            "Latency includes client/network/graph/controller time; token costs exclude calls without returned usage.",
            "Decision-1 local selection and LLM generated-Cypher are different architectures, not a model-only comparison.",
            "No retries hidden outside the LLM's recorded, bounded query correction turns.",
        ],
    })
    dump(directory / "summary.json", summary)
    return summary
