"""Run with .venv\\Scripts\\python.exe -m traversal --help."""

import argparse
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import psycopg
from psycopg import sql

from traversal.age import AgeGraph, load_graph
from traversal.evaluate import evaluate, read_lines, sample_queries
from traversal.foundry import Foundry, InferenceError, load_config
from traversal.synthetic import canonical_hash, validate as validate_legacy
from traversal.journeys import save, validate as validate_journeys

DATA = Path("data") / "traversal"


def database_url():
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    if Path(".env").exists():
        settings = dict(
            line.split("=", 1) for line in Path(".env").read_text().splitlines()
            if line and not line.startswith("#") and "=" in line
        )
        password = settings.get("POSTGRES_PASSWORD")
        if password:
            return "postgresql://postgres:" + quote(password, safe="") + "@127.0.0.1:55432/traversal"
    raise ValueError("Run db-up or configure DATABASE_URL.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("generate", help="Reproduce the versioned synthetic corpus.")
    sub.add_parser("validate", help="Validate schema, paths and split isolation offline.")
    sub.add_parser("db-up", help="Start the isolated loopback-only AGE container; creates a local random password.")
    sub.add_parser("load", help="Load the corpus into a new content-addressed graph and verify contents.")
    sub.add_parser("bootstrap", help="Initialize the private cloud graph, runtime role and durable store.")
    sub.add_parser("inspect", help="Verify the real graph and read recent durable run metrics without inference.")
    server = sub.add_parser("serve", help="Start the comparison UI using local or environment configuration.")
    server.add_argument("--config", default="config.local.json")
    server.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8766")))
    start = sub.add_parser("start", help="Validate, start the local database, load the graph and serve. No startup inference.")
    start.add_argument("--config", default="config.local.json")
    start.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8766")))
    run = sub.add_parser("evaluate", help="Run paired LIVE Foundry/AGE inference. Incurs inference charges.")
    run.add_argument("--config", default="config.local.json")
    run.add_argument("--split", choices=["development", "validation", "test"], default="test")
    run.add_argument("--limit", type=int, default=12)
    run.add_argument("--seed", type=int, default=7)
    run.add_argument("--threshold", type=float, default=0.0)
    run.add_argument("--output", required=True, help="New directory for durable raw traces and summary.")
    args = parser.parse_args()
    if args.command in ("serve", "start"):
        config = load_config(args.config)
        if args.command == "start":
            for key in ("endpoint", "decision_deployment", "baseline_deployment"):
                if "YOUR-" in config[key].upper():
                    raise ValueError(f"Replace the {key} placeholder in {args.config} before starting.")
            Foundry(config)
            for command in ("validate", "db-up", "load"):
                print(f"Starting: {command}", flush=True)
                subprocess.run([sys.executable, "-m", "traversal", command], check=True)
        from traversal.server import serve
        serve(database_url(), config, DATA, args.port)
        return
    if args.command == "generate":
        print(json.dumps(save(DATA), indent=2))
        return
    if args.command == "db-up":
        env_path = Path(".env")
        if not env_path.exists():
            env_path.write_text("POSTGRES_PASSWORD=" + secrets.token_urlsafe(32) + "\n", encoding="utf-8")
        subprocess.run(["docker", "compose", "up", "-d", "--wait", "--quiet-pull"], check=True)
        return
    graph = json.loads((DATA / "graph.json").read_text())
    queries, oracle = read_lines(DATA / "queries.jsonl"), read_lines(DATA / "oracle.jsonl")
    (validate_journeys if str(graph.get("dataset_version", "")).startswith("4.") else validate_legacy)(graph, queries, oracle)
    manifest = json.loads((DATA / "manifest.json").read_text())
    for name, value in (("graph", graph), ("queries", queries), ("oracle", oracle)):
        if canonical_hash(value) != manifest[name + "_sha256"]:
            raise ValueError(f"{name} contents do not match the versioned manifest.")
    if args.command == "validate":
        print(f"Validated {len(graph['nodes'])} nodes, {len(graph['edges'])} relationships, {len(queries)} queries.")
        return
    dsn = database_url()
    if args.command == "inspect":
        dsn = os.environ.get("APP_DATABASE_URL", dsn)
    graph_name = "traversal_" + canonical_hash(graph)[:12]
    if args.command in ("load", "bootstrap"):
        graph_name = load_graph(dsn, graph)
    if args.command == "bootstrap":
        from traversal.server import initialize_app_store
        app_password = os.environ.get("APP_DATABASE_PASSWORD")
        app_dsn = os.environ.get("APP_DATABASE_URL")
        if not app_password or not app_dsn:
            raise ValueError("Bootstrap requires APP_DATABASE_PASSWORD and APP_DATABASE_URL.")
        with psycopg.connect(dsn, autocommit=True) as connection:
            exists = connection.execute(
                "SELECT rolsuper FROM pg_roles WHERE rolname = %s", ("traversal_app",)
            ).fetchone()
            if exists and exists[0]:
                raise ValueError("Refusing to alter an existing superuser runtime role.")
            operation = "ALTER ROLE" if exists else "CREATE ROLE"
            # Managed PostgreSQL admins cannot ALTER the SUPERUSER attribute.
            superuser_clause = "" if exists else " NOSUPERUSER"
            connection.execute(sql.SQL(
                operation + " {} LOGIN INHERIT" + superuser_clause + " NOCREATEDB NOCREATEROLE PASSWORD {}"
            ).format(sql.Identifier("traversal_app"), sql.Literal(app_password)))
        initialize_app_store(dsn, app_role="traversal_app")
        runtime = AgeGraph(app_dsn, graph_name)
        try:
            runtime.verify(graph)
        finally:
            runtime.close()
        with psycopg.connect(app_dsn) as connection:
            privileges = connection.execute(
                "SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = current_user"
            ).fetchone()
            if privileges != (False, False, False):
                raise ValueError("Runtime database role has unexpected administrative privileges.")
            if connection.execute(
                "SELECT has_schema_privilege(current_user, %s, 'CREATE')", (graph_name,)
            ).fetchone()[0]:
                raise ValueError("Runtime database role can modify the graph schema.")
        print(f"Initialized and verified persistent AGE graph and least-privilege runtime: {graph_name}")
        return
    store = AgeGraph(dsn, graph_name)
    try:
        store.verify(graph)
        if args.command == "inspect":
            with psycopg.connect(dsn) as connection:
                connection.execute("SET TRANSACTION READ ONLY")
                runs = connection.execute(
                    "SELECT r.id, r.status, r.graph_name, r.created_at, r.finished_at, "
                    "(SELECT count(*) FROM traversal_app.calls c WHERE c.run_id = r.id) "
                    "FROM traversal_app.runs r WHERE budget_key = 'interactive' "
                    "ORDER BY created_at DESC LIMIT 5"
                ).fetchall()
                calls = connection.execute(
                    "SELECT c.run_id, c.method, c.call_index, "
                    "c.record->>'deployment', c.record->>'status', "
                    "c.record #>> '{usage,input_tokens}', c.record #>> '{usage,output_tokens}', "
                    "c.record #>> '{usage,cached_input_tokens}', c.record->>'estimated_cost_usd' "
                    "FROM traversal_app.calls c WHERE c.run_id = "
                    "(SELECT id FROM traversal_app.runs WHERE budget_key = 'interactive' "
                    "ORDER BY created_at DESC LIMIT 1) ORDER BY c.method, c.call_index"
                ).fetchall()
                budgets = connection.execute(
                    "SELECT day, call_limit, reserved_calls FROM traversal_app.budgets "
                    "WHERE budget_key = 'interactive' ORDER BY day DESC LIMIT 2"
                ).fetchall()
            print(json.dumps({
                "verified_graph": graph_name,
                "verified_nodes": len(graph["nodes"]),
                "verified_edges": len(graph["edges"]),
                "runs": [dict(zip(
                    ("id", "status", "graph_name", "created_at", "finished_at", "call_count"), row
                )) for row in runs],
                "latest_calls": [dict(zip(
                    ("run_id", "method", "call_index", "deployment", "status", "input_tokens",
                     "output_tokens", "cached_input_tokens", "estimated_cost_usd"), row
                )) for row in calls],
                "daily_budgets": [dict(zip(
                    ("day", "call_limit", "reserved_calls"), row
                )) for row in budgets],
            }, default=str, indent=2))
            return
        if args.command == "load":
            print(f"Loaded and verified real AGE graph: {graph_name}")
            return
        selected = sample_queries(queries, args.split, args.limit, args.seed)
        config = load_config(args.config)
        summary = evaluate(
            store, Foundry(config), selected, oracle, args.output,
            threshold=args.threshold, seed=args.seed,
        )
        print(json.dumps(summary["methods"], indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    try:
        main()
    except (ValueError, InferenceError, OSError, subprocess.SubprocessError, psycopg.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
