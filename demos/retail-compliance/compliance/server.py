"""Web server: static UI, scenario catalogue, and streamed live audits."""

import json
import queue
import socket
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from . import audit, catalog
from .foundry import Foundry

WEB = Path(__file__).resolve().parent.parent / "web"
SCENARIO_ORDER = ("drinks-fridge", "coffee-shelf", "clothing-display")  # simplest story first
STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/static/style.css": ("style.css", "text/css; charset=utf-8"),
          "/static/app.js": ("app.js", "text/javascript; charset=utf-8")}
MAX_BODY = 1024
MAX_CONCURRENT_RUNS = 4
MAX_CONNECTIONS = 64  # handler threads; extra connections are closed immediately
REQUEST_DEADLINE = 10  # seconds to send the whole request (line, headers and body)
CSP = ("default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")


class DailyBudget:
    """In-memory UTC-day call ceiling. Deploy with one replica so it is shared."""

    def __init__(self, limit):
        self.limit, self.day, self.used = limit, None, 0
        self.lock = threading.Lock()

    def take(self, calls):
        with self.lock:
            today = datetime.now(timezone.utc).date()
            if today != self.day:
                self.day, self.used = today, 0
            if self.used + calls > self.limit:
                return False
            self.used += calls
            return True

    def remaining(self):
        with self.lock:
            today = datetime.now(timezone.utc).date()
            return self.limit if today != self.day else self.limit - self.used


def document_title(text):
    first = text.lstrip().splitlines()[0] if text.strip() else ""
    return first.lstrip("#").strip() or "Untitled document"


def public_catalog(scenarios, deployment_label):
    def scenario_view(s):
        sid, documents, doc_ids = s["id"], [], {}

        def document(relative, text, kind, images=None):
            if relative not in doc_ids:
                doc_ids[relative] = f"doc{len(documents) + 1}"
                documents.append({"id": doc_ids[relative], "kind": kind, "file": relative.rsplit("/", 1)[-1],
                                  "title": document_title(text), "text": text, "images": images or {}})
            return doc_ids[relative]

        campaigns = []
        for c in s["campaigns"].values():
            q, images = c["questions"], {}
            if c.get("reference"):  # the brief links its lookbook relative to policies/
                images["../" + c["reference"]] = f"/images/{sid}/{c['reference'].removeprefix('images/')}"
            docs = [document(c["brief"], c["brief_text"], "Campaign brief", images)]
            if c.get("standards"):
                docs.append(document(c["standards"], c["standards_text"], "Standards"))
            campaigns.append({
                "id": c["id"], "name": c["name"], "documents": docs, "reference": next(iter(images.values()), None),
                "checks": [{k: check[k] for k in ("id", "rule", "requirement", "question", "photos", "uses_reference")}
                           for check in q["checks"]],
                "not_checkable": q.get("not_checkable", []), "review_notes": q["review"]["notes"],
                "reviewed_on": q["review"].get("reviewed_on"),
                "extraction": {k: q["extraction"].get(k)
                               for k in ("model", "reasoning_effort", "usage", "latency_ms", "extracted_at")}})
        return {"id": sid, "name": s["name"], "note": s["note"], "store": s["demo"]["store"],
                "audit": s["demo"]["audit"], "photo_types": s["photo_types"], "documents": documents,
                "campaigns": campaigns,
                "visits": [{"id": v["id"], "title": v["title"], "summary": v["summary"], "shows": v["shows"],
                            "expected": v["expected"],
                            "photos": [{"type": t, "url": f"/images/{sid}/visits/{v['id']}/{t}.jpg"}
                                       for t in v["photo_paths"]]} for v in s["visits"]]}

    return {"model": deployment_label, "price_per_million_input": audit.INPUT_PRICE_PER_MILLION,
            "scenarios": [scenario_view(s) for s in scenarios.values()]}


class App:
    def __init__(self, config):
        self.config = config
        self.client = Foundry(config)
        ids = catalog.scenario_ids()
        ordered = [s for s in SCENARIO_ORDER if s in ids] + [s for s in ids if s not in SCENARIO_ORDER]
        self.scenarios = {sid: catalog.load_scenario(sid, demo=True) for sid in ordered}
        self.catalog_json = json.dumps(public_catalog(self.scenarios, "Microsoft-Decision-1.1")).encode("utf-8")
        self.budget = DailyBudget(config["daily_max_calls"])
        self.runs = threading.BoundedSemaphore(MAX_CONCURRENT_RUNS)

    def image_path(self, scenario_id, relative):
        scenario = self.scenarios.get(scenario_id)
        if not scenario or not relative.endswith(".jpg") or "\\" in relative:
            return None
        root = (scenario["folder"] / "images").resolve()
        path = (root / relative).resolve()
        return path if root in path.parents and path.is_file() else None


class Handler(BaseHTTPRequestHandler):
    server_version = "RetailCompliance"
    sys_version = ""
    timeout = 30  # per-read socket timeout; REQUEST_DEADLINE bounds the whole request
    app = None

    def setup(self):
        super().setup()
        self.deadline = threading.Timer(REQUEST_DEADLINE, self.drop_slow_client)
        self.deadline.daemon = True
        self.deadline.start()

    def drop_slow_client(self):
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def finish(self):
        self.deadline.cancel()
        super().finish()

    def log_message(self, fmt, *args):
        print(f"{self.log_date_time_string()} {self.command} {urlsplit(self.path).path} -> {args[1] if len(args) > 1 else ''}")

    def headers_common(self, content_type, length=None, cache="no-store"):
        self.send_header("Content-Type", content_type)
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", cache)
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()

    def send_bytes(self, status, data, content_type, cache="no-store"):
        self.send_response(status)
        self.headers_common(content_type, len(data), cache)
        if self.command != "HEAD":
            self.wfile.write(data)

    def send_json(self, status, value):
        self.send_bytes(status, json.dumps(value).encode("utf-8"), "application/json")

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        self.deadline.cancel()  # request fully received
        path = urlsplit(self.path).path
        if path in STATIC:
            name, content_type = STATIC[path]
            return self.send_bytes(200, (WEB / name).read_bytes(), content_type, "no-cache")
        if path == "/healthz":
            return self.send_json(200, {"status": "ok"})
        if path == "/api/catalog":
            return self.send_bytes(200, self.app.catalog_json, "application/json", "no-cache")
        if path == "/api/budget":
            return self.send_json(200, {"remaining_calls_today": self.app.budget.remaining()})
        if path.startswith("/images/"):
            parts = path.split("/", 3)
            image = self.app.image_path(parts[2], parts[3]) if len(parts) == 4 else None
            if image:
                return self.send_bytes(200, image.read_bytes(), "image/jpeg", "public, max-age=3600")
        return self.send_json(404, {"error": "Not found."})

    def do_POST(self):
        if urlsplit(self.path).path != "/api/audit":
            return self.send_json(404, {"error": "Not found."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if not 0 < length <= MAX_BODY or not self.headers.get("Content-Type", "").startswith("application/json"):
            return self.send_json(400, {"error": "Send a small JSON body."})
        body = self.rfile.read(length)
        self.deadline.cancel()  # request fully received, or the client stopped early
        if len(body) != length:  # cut off (e.g. by REQUEST_DEADLINE): never admit a partial request
            self.close_connection = True
            return
        try:
            request = json.loads(body)
            scenario = self.app.scenarios[request["scenario"]]
            visits = scenario["visits"] if request["visit"] == "all" else [catalog.find_visit(scenario, request["visit"])]
        except (json.JSONDecodeError, KeyError, TypeError, catalog.CatalogError):
            return self.send_json(400, {"error": "Choose a known scenario and visit."})
        if not self.app.runs.acquire(blocking=False):
            return self.send_json(429, {"error": "The demo is busy. Try again in a moment."})
        if not self.app.budget.take(len(visits)):
            self.app.runs.release()
            return self.send_json(429, {"error": "Today's live-call limit is reached. Try again tomorrow (UTC)."})
        self.stream(scenario, visits)  # the worker releases the run permit when its calls finish

    def stream(self, scenario, visits):
        events = queue.Queue()
        started = time.perf_counter()

        def emit(event):
            events.put(dict(event, t_ms=round((time.perf_counter() - started) * 1000, 1)))

        def publish(result):
            if "error" in result:  # keep upstream detail in operator logs only
                print(f"visit {result['scenario']}/{result['visit']} failed: {result['error']}")
                result = dict(result, error="The model is busy; try again shortly." if "429" in result["error"]
                              else "The model call failed. Try again later.")
            emit({"event": "visit_result", "result": result})

        def worker():
            try:
                results = audit.audit_many(self.app.client, scenario, visits, self.app.config["decision_deployment"],
                                           workers=12, on_result=publish)
                emit({"event": "run_finished", "summary": audit.summarise(results),
                      "wall_ms": round((time.perf_counter() - started) * 1000, 1)})
            except Exception as exc:  # report, never leak a traceback to the client
                print(f"run failed: {exc!r}")
                emit({"event": "run_error", "error": "The audit failed. Try again later."})
            finally:
                self.app.runs.release()
                events.put(None)

        try:
            plans = []
            for visit in visits:
                plan = audit.plan_visit(scenario, visit)
                asked = [p for p in plan if p["asked"]]
                plans.append({"visit": visit["id"], "questions": len(asked), "skipped": len(plan) - len(asked)})
            emit({"event": "run_started", "scenario": scenario["id"], "calls": len(visits), "plans": plans})
            threading.Thread(target=worker, daemon=True).start()  # from here the worker owns the permit
        except BaseException:
            self.app.runs.release()
            raise
        self.send_response(200)
        self.headers_common("application/x-ndjson")
        try:
            while (event := events.get()) is not None:
                self.wfile.write(json.dumps(event).encode("utf-8") + b"\n")
                self.wfile.flush()
        except OSError:
            pass  # the client left; in-flight calls still finish, are billed, then free the permit


class BoundedServer(ThreadingHTTPServer):
    """ThreadingHTTPServer with a cap on concurrent handler threads."""

    daemon_threads = True

    def __init__(self, address, handler, max_connections=MAX_CONNECTIONS):
        super().__init__(address, handler)
        self.slots = threading.BoundedSemaphore(max_connections)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


def serve(config, host, port):
    Handler.app = App(config)
    server = BoundedServer((host, port), Handler)
    print(f"Retail compliance demo on http://{host}:{port}  (daily call limit {config['daily_max_calls']})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
