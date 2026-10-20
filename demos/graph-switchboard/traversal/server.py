"""Same-origin comparison service with durable admission and real inference."""

import json
import copy
import logging
import os
import queue
import re
import hashlib
import signal
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from traversal.age import AgeGraph
from traversal.evaluate import read_lines, sample_queries, score
from traversal.foundry import Foundry, InferenceError
from traversal.runtime import decision_walk, llm_cypher, resolve_decision_entry
from traversal.synthetic import canonical_hash, dump

WEB = Path(__file__).resolve().parent.parent / "web"
LOG = logging.getLogger("graph-switchboard")
WORKFLOW = "md1-entry-v1"
RUN_ALLOWANCES = {"entry": 1, "decision": 16, "llm-cypher": 5}
RUN_RESERVATION = sum(RUN_ALLOWANCES.values())


def visible_vehicle(value):
    vehicle = {key: value[key] for key in ("make", "model", "configuration") if key in value}
    year = value.get("year", value.get("model_year"))
    if year is not None:
        vehicle["year"] = year
    return vehicle


def initialize_app_store(admin_dsn, app_role="traversal_app"):
    """Admin-only bootstrap, after load_graph and creation of the runtime login."""
    with psycopg.connect(admin_dsn, connect_timeout=10) as connection:
        connection.execute("SELECT pg_advisory_xact_lock(731402918)")
        connection.execute("CREATE SCHEMA IF NOT EXISTS traversal_app")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS traversal_app.budgets (
                budget_key text NOT NULL, day date NOT NULL,
                call_limit integer NOT NULL CHECK (call_limit > 0),
                reserved_calls integer NOT NULL DEFAULT 0 CHECK (reserved_calls >= 0),
                PRIMARY KEY (budget_key, day)
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS traversal_app.runs (
                id text PRIMARY KEY, budget_key text NOT NULL, day date NOT NULL,
                graph_name text NOT NULL, status text NOT NULL
                    CHECK (status IN ('running', 'completed', 'error')),
                reserved_calls integer NOT NULL, request jsonb NOT NULL,
                record jsonb, error text, created_at timestamptz NOT NULL DEFAULT now(),
                finished_at timestamptz,
                FOREIGN KEY (budget_key, day) REFERENCES traversal_app.budgets (budget_key, day)
            )
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS runs_running ON traversal_app.runs (budget_key)
            WHERE status = 'running'
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS traversal_app.calls (
                run_id text NOT NULL REFERENCES traversal_app.runs (id),
                method text NOT NULL CHECK (method IN ('entry', 'decision', 'llm-cypher')),
                call_index integer NOT NULL CHECK (call_index > 0),
                record jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY (run_id, method, call_index)
            )
        """)
        connection.execute("ALTER TABLE traversal_app.calls DROP CONSTRAINT IF EXISTS calls_method_check")
        connection.execute("""
            ALTER TABLE traversal_app.calls ADD CONSTRAINT calls_method_check
            CHECK (method IN ('entry', 'decision', 'llm-cypher'))
        """)
        if app_role is not None:
            role = sql.Identifier(app_role)
            connection.execute(sql.SQL("GRANT traversal_reader TO {}").format(role))
            connection.execute(sql.SQL("GRANT USAGE ON SCHEMA traversal_app TO {}").format(role))
            connection.execute(sql.SQL(
                "GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA traversal_app TO {}"
            ).format(role))


class AdmissionError(RuntimeError):
    def __init__(self, message):
        super().__init__(message)
        self.status = 429


class AppStore:
    """Reservations survive process loss. Abandoned running rows fail closed."""

    def __init__(self, dsn, daily_limit=1000, budget_key="interactive"):
        if isinstance(daily_limit, bool) or not isinstance(daily_limit, int) or daily_limit < 1:
            raise ValueError("server_daily_max_calls must be a positive integer.")
        self.dsn, self.daily_limit, self.budget_key = dsn, daily_limit, budget_key
        with self.connection() as connection:
            connection.execute("SELECT id FROM traversal_app.runs LIMIT 0")

    def connection(self):
        return psycopg.connect(self.dsn, connect_timeout=10, options="-c timezone=UTC -c statement_timeout=10000")

    def budget(self, connection):
        # This transaction lock also serializes admissions across UTC midnight.
        connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (self.budget_key,))
        connection.execute("""
            INSERT INTO traversal_app.budgets (budget_key, day, call_limit)
            VALUES (%s, CURRENT_DATE, %s) ON CONFLICT DO NOTHING
        """, (self.budget_key, self.daily_limit))
        connection.execute("""
            UPDATE traversal_app.budgets SET call_limit = LEAST(call_limit, %s)
            WHERE budget_key = %s AND day = CURRENT_DATE
        """, (self.daily_limit, self.budget_key))
        return connection.execute("""
            SELECT day, LEAST(call_limit, %s), reserved_calls
            FROM traversal_app.budgets WHERE budget_key = %s AND day = CURRENT_DATE FOR UPDATE
        """, (self.daily_limit, self.budget_key)).fetchone()

    def remaining(self):
        with self.connection() as connection:
            _, limit, used = self.budget(connection)
            return max(0, limit - used)

    def reserve(self, graph_name, query, scorable):
        identifier = uuid.uuid4().hex
        with self.connection() as connection:
            day, limit, used = self.budget(connection)
            running = connection.execute("""
                SELECT 1 FROM traversal_app.runs WHERE budget_key = %s AND status = 'running' LIMIT 1
            """, (self.budget_key,)).fetchone()
            if running:
                raise AdmissionError("A comparison is already running; retry after it finishes.")
            if used + RUN_RESERVATION > limit:
                raise AdmissionError("UTC daily inference ceiling reached; retry after the next UTC day.")
            connection.execute("""
                UPDATE traversal_app.budgets SET reserved_calls = reserved_calls + %s
                WHERE budget_key = %s AND day = %s
            """, (RUN_RESERVATION, self.budget_key, day))
            connection.execute("""
                INSERT INTO traversal_app.runs
                    (id, budget_key, day, graph_name, status, reserved_calls, request)
                VALUES (%s, %s, %s, %s, 'running', %s, %s)
            """, (identifier, self.budget_key, day, graph_name, RUN_RESERVATION,
                  Jsonb({"query": query, "scorable": scorable})))
        return identifier

    def call(self, identifier, method, index, record):
        if method not in RUN_ALLOWANCES or not 1 <= index <= RUN_ALLOWANCES[method]:
            raise InferenceError("Durable inference allowance exceeded.")
        with self.connection() as connection:
            run = connection.execute("""
                SELECT status FROM traversal_app.runs WHERE id = %s AND budget_key = %s FOR UPDATE
            """, (identifier, self.budget_key)).fetchone()
            if not run or run[0] != "running":
                raise InferenceError("Inference requires an active durable reservation.")
            connection.execute("""
                INSERT INTO traversal_app.calls (run_id, method, call_index, record)
                VALUES (%s, %s, %s, %s) ON CONFLICT (run_id, method, call_index)
                DO UPDATE SET record = EXCLUDED.record
            """, (identifier, method, index, Jsonb(record)))

    def finish(self, identifier, record=None, error=None):
        with self.connection() as connection:
            connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (self.budget_key,))
            run = connection.execute("""
                SELECT day, reserved_calls, status FROM traversal_app.runs
                WHERE id = %s AND budget_key = %s FOR UPDATE
            """, (identifier, self.budget_key)).fetchone()
            if not run:
                raise ValueError("Unknown durable run.")
            if run[2] != "running":
                return
            attempts = connection.execute(
                "SELECT count(*) FROM traversal_app.calls WHERE run_id = %s", (identifier,)
            ).fetchone()[0]
            status = "error" if error else "completed"
            connection.execute("""
                UPDATE traversal_app.runs SET status = %s, record = %s, error = %s, finished_at = now()
                WHERE id = %s
            """, (status, Jsonb(record) if record is not None else None, error, identifier))
            connection.execute("""
                UPDATE traversal_app.budgets SET reserved_calls = reserved_calls - %s
                WHERE budget_key = %s AND day = %s
            """, (max(0, run[1] - attempts), self.budget_key, run[0]))

    def get_record(self, identifier):
        if not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-f]{32}", identifier):
            raise ValueError("Invalid previous run identifier.")
        with self.connection() as connection:
            row = connection.execute(
            "SELECT record FROM traversal_app.runs WHERE id = %s AND budget_key = %s "
            "AND status = 'completed'", (identifier, self.budget_key)
            ).fetchone()
        if not row or not row[0]:
            raise ValueError("Previous comparison is missing or did not complete successfully.")
        return row[0]


def valid_run(body, queries):
    if (not isinstance(body, dict) or not isinstance(body.get("case_id"), str)
            or body["case_id"] not in queries):
        raise ValueError("Choose a known synthetic case.")
    original = queries[body["case_id"]]
    question = body.get("question", original["question"])
    evidence = body.get("evidence", original["evidence"])
    vehicle = body.get("vehicle", original.get("vehicle"))
    vehicle_id = body.get("vehicle_id", original.get("vehicle_id"))
    if (not isinstance(vehicle_id, str) or len(vehicle_id) > 200
            or (vehicle is not None and (not isinstance(vehicle, dict)
                or set(vehicle) - {"make", "model", "year", "configuration", "id"}
                or any(not isinstance(value, (str, int)) or isinstance(value, bool)
                       for value in vehicle.values())))):
        raise ValueError("Supply a valid visible vehicle context.")
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 4000:
        raise ValueError("Question must contain 1-4000 characters.")
    if not isinstance(evidence, list) or len(evidence) > 12:
        raise ValueError("Supply at most 12 observations.")
    for item in evidence:
        if (not isinstance(item, dict) or set(item) != {"check", "observation"}
                or not isinstance(item["check"], str) or not 1 <= len(item["check"]) <= 1000
                or not isinstance(item["observation"], str) or not 1 <= len(item["observation"]) <= 4000
                ):
            raise ValueError("Each observation needs a check description and 1-4000 characters of text.")
    result = {**original, "question": question.strip(), "evidence": evidence, "vehicle_id": vehicle_id}
    if vehicle is not None:
        result["vehicle"] = vehicle
    else:
        result.pop("vehicle", None)
    return result, (
        question.strip() == original["question"] and evidence == original["evidence"]
        and vehicle_id == original.get("vehicle_id") and vehicle == original.get("vehicle")
    )


class Service:
    def __init__(self, dsn, config, data):
        self.dsn, self.config, self.data = dsn, config, data
        self.graph = json.loads((data / "graph.json").read_text())
        self.name = "traversal_" + canonical_hash(self.graph)[:12]
        self.manifest = json.loads((data / "manifest.json").read_text())
        self.oracle = {q["id"]: q for q in read_lines(data / "oracle.jsonl")}
        # Fixture metadata authors human-readable inputs/scoring only. No AGE topology
        # is prefetched at startup, and none is exposed through the case catalogue.
        self.nodes = {node["id"]: node for node in self.graph["nodes"]}
        self.vehicle = next(node for node in self.graph["nodes"] if node["type"] == "VehicleModel")
        self.vehicles = {node["id"]: node for node in self.graph["nodes"] if node["type"] == "VehicleModel"}
        fixtures = read_lines(data / "queries.jsonl")
        self.queries = {}
        for fixture in fixtures:
            self.queries[fixture["id"]] = {
                "id": fixture["id"], "vehicle_id": fixture["vehicle_id"],
                "vehicle": visible_vehicle(fixture.get("vehicle", self.vehicles.get(fixture["vehicle_id"], {}))),
                "title": fixture.get("title", fixture["question"]),
                "question": fixture["question"],
                "demo": fixture.get("demo", False), "category": fixture["category"],
                "intent": fixture.get("intent", fixture.get("scenario", "")),
                "evidence": [{"check": item.get("check") or self.nodes[item["action_id"]]["description"],
                              "observation": item["observation"]} for item in fixture["evidence"]],
            }
            for key in ("journey_id", "turn", "turn_count", "next_case"):
                if key in fixture:
                    self.queries[fixture["id"]][key] = fixture[key]
        cases = sorted(fixtures, key=lambda q: (not q.get("demo", False), q["id"]))
        self.case_ids = [q["id"] for q in cases]
        self.record_cases = []
        for first in cases:
            if not first.get("demo") or first.get("turn") != 0:
                continue
            final = self.queries[f"{first['journey_id']}-turn-{first['turn_count'] - 1}"]
            identifier = f"{first['journey_id']}-records"
            complaint = first["question"].rsplit(". ", 1)[0] + "."
            self.queries[identifier] = {
                **{key: value for key, value in self.queries[first["id"]].items()
                   if key not in {"journey_id", "turn", "turn_count", "next_case"}},
                "id": identifier,
                "question": complaint + " What do the supplied records support, and what should the technician do next?",
                "evidence": copy.deepcopy(final["evidence"]),
            }
            self.oracle[identifier] = {**self.oracle[final["id"]], "id": identifier}
            self.record_cases.append(identifier)
        if self.manifest["graph_sha256"] != canonical_hash(self.graph):
            raise ValueError("Graph differs from versioned manifest.")
        for filename, expected in self.manifest.get("sources", {}).items():
            if (Path(filename).name != filename
                    or hashlib.sha256((data / "source-material" / filename).read_bytes()).hexdigest() != expected):
                raise ValueError("Source guide differs from versioned manifest.")
        if os.environ.get("APP_STORE_INITIALIZE", "1") != "0":
            initialize_app_store(dsn, app_role=None)
        self.records = AppStore(dsn, config.get("server_daily_max_calls", 1000))
        self.output = Path(os.environ.get("RESULTS_DIR", str(Path("results") / "local" / "interactive")))
        self.result_files = os.environ.get("RESULT_FILES", "0" if os.environ.get("PUBLIC_ORIGIN") else "1") == "1"

    def catalog(self):
        cases = []
        for identifier in self.case_ids + self.record_cases:
            query = self.queries[identifier]
            if query.get("turn", 0) != 0:
                continue
            cases.append({
                **{key: value for key, value in query.items()
                   if key not in {"journey_id", "turn", "turn_count", "next_case"}},
                "input_kind": "with_records" if identifier in self.record_cases else "problem",
            })
        return {
            "default_case_id": "weak-washers-turn-0",
            "cases": cases,
            "input_policy": "single-problem-v1",
            "vehicle": {"id": self.vehicle["id"], **visible_vehicle(self.vehicle)},
            "vehicles": [{"id": node["id"], **visible_vehicle(node)} for node in self.vehicles.values()],
            "manifest": self.manifest, "graph_name": self.name, "workflow": WORKFLOW,
            "decision_deployment": self.config["decision_deployment"],
            "baseline_deployment": self.config["baseline_deployment"],
            "threshold": self.config.get("threshold", 0.0),
            "pricing": self.config.get("pricing", {}),
            "remaining_calls": self.records.remaining(),
        }

    def admit(self, query, scorable):
        return self.records.reserve(self.name, {k: v for k, v in query.items()
                                               if k != "_previous_record"}, scorable)

    def release(self, previous_id):
        previous = self.records.get_record(previous_id)
        if previous["graph"] != self.name or not previous.get("scorable"):
            raise ValueError("Only an unedited completed journey can release its next records.")
        next_case = previous["query"].get("next_case")
        if not next_case or next_case not in self.queries:
            raise ValueError("This journey has no further record release.")
        return self.queries[next_case]

    def ready(self):
        store = AgeGraph(self.dsn, self.name)
        try:
            store.read("MATCH (n) RETURN count(n)")
            with self.records.connection() as connection:
                connection.execute("SELECT id FROM traversal_app.runs LIMIT 0")
        finally:
            store.close()

    def compare(self, query, scorable, publish, reservation=None):
        reservation = reservation or self.admit(query, scorable)
        lane_starts = {}
        previous = query.get("_previous_record")
        query = {key: value for key, value in query.items() if key != "_previous_record"}
        previous_results = {r["method"]: r for r in previous["results"]} if previous else {}

        def emit_for(method):
            def emit(event):
                clock = "decision" if method == "entry" else method
                publish(copy.deepcopy({"method": method, "elapsed_ms": round(
                    (time.perf_counter() - lane_starts[clock]) * 1000, 2), **event}))
            return emit

        def make_model(method):
            model = Foundry(self.config)
            model.max_calls = RUN_ALLOWANCES[method]
            model.record_call = lambda record, index: self.records.call(reservation, method, index, record)
            model.emit = emit_for(method)
            return model

        def metrics(model, store, since):
            calls = list(model.calls)
            costs = [call["estimated_cost_usd"] for call in calls]
            return {
                "elapsed_ms": round((time.perf_counter() - since) * 1000, 2),
                "inference_calls": len(calls),
                "input_tokens": sum(c["usage"]["input_tokens"] for c in calls if c["usage"]),
                "output_tokens": sum(c["usage"]["output_tokens"] for c in calls if c["usage"]),
                "calls_without_usage": sum(c["usage"] is None for c in calls),
                "estimated_cost_usd": sum(costs) if all(c is not None for c in costs) else None,
                "graph_queries": store.query_count if store else 0,
                "graph_query_ms": round(store.query_ms if store else 0, 2),
                "calls": calls,
            }

        def close(model, store):
            if store:
                store.close()
            if model.credential:
                model.credential.close()

        def execute(method):
            lane_starts[method] = time.perf_counter()
            lane_started = lane_starts[method]
            model = make_model(method)
            store = None
            emit = emit_for(method)
            entry_summary = None
            entry_metrics = None
            try:
                if method == "decision":
                    entry_model, entry_store = make_model("entry"), None
                    try:
                        entry_store = AgeGraph(self.dsn, self.name, emit=emit_for("entry"))
                        old_entry = previous.get("entry") if previous else None
                        if (old_entry and old_entry["result"]["status"] == "resolved"
                                and old_entry["result"].get("resolver") == "md1"):
                            from traversal.runtime import validate_entry
                            target = old_entry["result"]["target"]
                            validate_entry(entry_store, entry_store.node(target), query["vehicle_id"])
                            entry = {"status": "resolved", "target": target, "path": [], "resolver": "md1",
                                     "messages": [], "query": {**query, "start_node": target}}
                            emit_for("entry")({"event": "entry_selected", "node": target,
                                              "policy": "reuse_own_verified_entry"})
                        else:
                            entry = resolve_decision_entry(
                                entry_store, entry_model, query,
                                threshold=self.config.get("threshold", 0.0), emit=emit_for("entry"))
                    except Exception as exc:
                        LOG.warning("MD1 entry selection failed: %s", exc)
                        entry = {"status": "error", "target": None, "path": [],
                                 "error": str(exc)[:1500], "messages": []}
                    finally:
                        entry_metrics = metrics(entry_model, entry_store, lane_started)
                        close(entry_model, entry_store)
                    entry_summary = {
                        "result": {key: value for key, value in entry.items() if key not in {"query", "messages"}},
                        "metrics": entry_metrics, "messages": entry["messages"],
                    }
                    emit_for("entry")({"event": "entry_ready", **entry_summary})
                    traversal_started = time.perf_counter()
                    if entry["status"] != "resolved":
                        result = entry_summary["result"]
                    else:
                        model.headers()
                        store = AgeGraph(self.dsn, self.name, emit=emit)
                        result = decision_walk(store, model, entry["query"], self.config.get("threshold", 0.0), emit)
                else:
                    traversal_started = lane_started
                    model.headers()
                    store = AgeGraph(self.dsn, self.name, emit=emit)
                    old = previous_results.get(method, {}).get("result", {})
                    result = llm_cypher(store, model, query, emit=emit, prior_context=old.get("context"))
            except Exception as exc:
                LOG.warning("%s failed: %s", method, exc)
                result = {"status": "error", "target": None, "path": [], "error": str(exc)[:1500]}
            finally:
                lane_metrics = metrics(model, store, locals().get("traversal_started", lane_started))
                close(model, store)
            calls = (entry_metrics["calls"] if entry_metrics else []) + lane_metrics["calls"]
            costs = [c["estimated_cost_usd"] for c in calls]
            expected = None
            if scorable:
                expected = self.oracle[query["id"]]
                if expected.get("entry_expectation"):
                    expected = {**expected, **expected["entry_expectation"], "path": []}
            response = {
                "event": "complete", "method": method, "result": result,
                "run_id": reservation,
                "elapsed_ms": round((time.perf_counter() - lane_started) * 1000, 2),
                "hops": len(result.get("path", [])), "inference_calls": len(calls),
                "input_tokens": sum(c["usage"]["input_tokens"] for c in calls if c["usage"]),
                "output_tokens": sum(c["usage"]["output_tokens"] for c in calls if c["usage"]),
                "calls_without_usage": sum(c["usage"] is None for c in calls),
                "estimated_cost_usd": sum(costs) if all(c is not None for c in costs) else None,
                "graph_queries": (entry_metrics["graph_queries"] if entry_metrics else 0) + lane_metrics["graph_queries"],
                "graph_query_ms": round((entry_metrics["graph_query_ms"] if entry_metrics else 0) + lane_metrics["graph_query_ms"], 2),
                "score": score(result, expected) if expected else None,
                "calls": calls, "entry_metrics": entry_metrics, "traversal_metrics": lane_metrics,
                "model_calls_by_deployment": dict(Counter(c["deployment"] for c in calls)),
                "expected": ({key: expected[key] for key in ("status", "target", "path")}
                             if expected else None),
            }
            publish({**response, "event": "lane_ready", "expected": None})
            return response, entry_summary

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(execute, method) for method in ("decision", "llm-cypher")]
                completed = [future.result() for future in futures]
                results = [item[0] for item in completed]
                entry_summary = completed[0][1]
            record = {
                "source": "live_foundry_and_apache_age", "graph": self.name,
                "corpus": self.manifest, "workflow": WORKFLOW,
                "run_id": reservation, "query": query, "scorable": scorable, "results": results,
                "entry": entry_summary,
                "actual_inference_calls": sum(r["inference_calls"] for r in results),
                "config": {key: self.config[key] for key in (
                    "decision_deployment", "baseline_deployment", "baseline_reasoning_effort", "pricing"
                ) if key in self.config},
            }
            if self.result_files:
                self.output.mkdir(parents=True, exist_ok=True)
                dump(self.output / (reservation + ".json"), record)
            errors = [result["result"]["error"] for result in results if result["result"]["status"] == "error"]
            self.records.finish(reservation, record, "; ".join(errors)[:3000] if errors else None)
        except Exception as exc:
            self.records.finish(reservation, error=str(exc)[:3000])
            raise
        # Terminal success/error events only follow durable persistence.
        emit_for("entry")({"event": "complete", **entry_summary})
        for result in results:
            publish(result)

    def continue_query(self, query, scorable, previous_id):
        if not previous_id:
            if query.get("turn", 0) > 0:
                raise ValueError("Release this stage from its preceding completed comparison.")
            return query
        previous = self.records.get_record(previous_id)
        old_query = previous["query"]
        if (previous["graph"] != self.name or not previous.get("scorable")
                or not query.get("journey_id")
                or old_query.get("journey_id") != query["journey_id"]
                or old_query.get("next_case") != query["id"]):
            raise ValueError("Previous comparison is not the preceding release of this journey.")
        current = {**query, "previous_run_id": previous_id}
        if scorable:
            current["_previous_record"] = previous
        return current


class Handler(BaseHTTPRequestHandler):
    server_version = "GraphSwitchboard"

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def reply(self, status, body, mime="application/json"):
        encoded = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(encoded)))
        if status == 429:
            self.send_header("Retry-After", "30")
        self.security_headers()
        self.end_headers()
        self.wfile.write(encoded)

    def security_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                         "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                         "connect-src 'self'; object-src 'none'; frame-ancestors 'none'")

    def local_request(self):
        public = getattr(self.server, "public_origin", None)
        if public:
            return (self.headers.get("Host", "").lower() == urlsplit(public).netloc.lower()
                    and self.headers.get("Origin") in {None, public})
        origins = {f"http://127.0.0.1:{self.server.server_port}",
                   f"http://localhost:{self.server.server_port}"}
        hosts = {origin.removeprefix("http://") for origin in origins}
        return self.headers.get("Host") in hosts and self.headers.get("Origin") in origins | {None}

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in {"/healthz", "/readyz", "/health/live", "/health/ready"}:
            try:
                if path in {"/readyz", "/health/ready"}:
                    self.server.service.ready()
                self.reply(200, {"status": "ok"})
            except Exception:
                LOG.exception("Readiness check failed.")
                self.reply(503, {"status": "unavailable"})
            return
        if not self.local_request():
            self.reply(403, {"error": "Only requests to the configured same origin are allowed."})
            return
        try:
            if path == "/api/catalog":
                self.reply(200, self.server.service.catalog())
            elif path == "/api/sources":
                sources = self.server.service.data / "source-material"
                self.reply(200, [{"name": p.name, "text": p.read_text(encoding="utf-8")}
                                 for p in sorted(sources.glob("SG-*.md"))])
            elif path in {"/", "/app.js", "/style.css"}:
                name = "index.html" if path == "/" else path[1:]
                mime = {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript",
                        "style.css": "text/css"}[name]
                self.reply(200, (WEB / name).read_bytes(), mime)
            else:
                self.reply(404, {"error": "Not found."})
        except ValueError as exc:
            self.reply(400, {"error": str(exc)})
        except psycopg.Error:
            LOG.exception("Database request failed.")
            self.reply(503, {"error": "Database is unavailable."})

    def do_POST(self):
        if not self.local_request():
            self.reply(403, {"error": "Only requests to the configured same origin are allowed."})
            return
        if self.path != "/api/run":
            self.reply(404, {"error": "Not found."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if self.headers.get_content_type() != "application/json" or not 1 <= length <= 64000:
                raise ValueError("Send a JSON request of at most 64000 bytes.")
            self.connection.settimeout(10)
            body = json.loads(self.rfile.read(length))
            query, scorable = valid_run(body, self.server.service.queries)
            if body.get("previous_run_id") or query.get("turn", 0) > 0:
                raise ValueError("Submit one problem with all available information upfront; staged continuation is not supported.")
        except (ValueError, UnicodeDecodeError, TimeoutError) as exc:
            self.reply(400, {"error": str(exc)})
            return
        service = self.server.service
        try:
            reservation = service.admit(query, scorable)
        except AdmissionError as exc:
            self.reply(429, {"error": str(exc)})
            return
        except psycopg.Error:
            LOG.exception("Durable admission failed.")
            self.reply(503, {"error": "Database admission is unavailable; no inference was started."})
            return
        events = queue.Queue()
        disconnected = False

        def work():
            try:
                service.compare(query, scorable, events.put, reservation)
            except Exception:
                LOG.exception("Could not persist comparison.")
                events.put({"event": "error", "error": "Comparison failed; inspect the durable run record and server logs."})
            finally:
                events.put(None)

        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Connection", "close")
        self.security_headers()
        self.end_headers()
        self.close_connection = True
        worker = threading.Thread(target=work, daemon=False)
        worker.start()
        while True:
            try:
                event = events.get(timeout=5)
            except queue.Empty:
                event = {"event": "heartbeat"}
            if event is None:
                break
            if not disconnected:
                try:
                    self.wfile.write((json.dumps(event) + "\n").encode())
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, TimeoutError):
                    disconnected = True
        # Accepted inference is not cancelled by closing a browser; results still persist.


def public_origin(value):
    if not value:
        return None
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment):
        raise ValueError("PUBLIC_ORIGIN must be an exact HTTPS origin without a path.")
    # Validate the port rather than accepting malformed authorities.
    parsed.port
    return value


class ComparisonServer(ThreadingHTTPServer):
    request_queue_size = 128
    daemon_threads = False
    block_on_close = True


def serve(dsn, config, data, port=8766):
    port = int(os.environ.get("PORT", port))
    if not 1024 <= port <= 65535:
        raise ValueError("Use an unprivileged port from 1024 through 65535.")
    host = os.environ.get("HOST", "127.0.0.1")
    origin = public_origin(os.environ.get("PUBLIC_ORIGIN"))
    if host not in {"127.0.0.1", "localhost"} and not origin:
        raise ValueError("Non-loopback hosting requires an explicit PUBLIC_ORIGIN.")
    service = Service(dsn, config, data)
    server = ComparisonServer((host, port), Handler)
    server.service = service
    server.public_origin = origin
    print(f"Graph Switchboard ready: {origin or f'http://127.0.0.1:{port}'}", flush=True)
    previous_term = None
    if threading.current_thread() is threading.main_thread():
        previous_term = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown).start())
    try:
        server.serve_forever()
    finally:
        server.server_close()
        if previous_term is not None:
            signal.signal(signal.SIGTERM, previous_term)
