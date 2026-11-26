import io
import json
import socket
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from compliance import server  # noqa: E402
from compliance.foundry import FoundryError  # noqa: E402

CONFIG = {"endpoint": "https://example.cognitiveservices.azure.com", "decision_deployment": "d",
          "auth_mode": "azure_cli", "timeout_seconds": 5, "daily_max_calls": 3}


def handler_for(app, wfile):
    handler = server.Handler.__new__(server.Handler)
    handler.app, handler.wfile = app, wfile
    handler.send_response = lambda *a: None
    handler.headers_common = lambda *a, **k: None
    return handler


def free_permits(app):
    return app.runs._value


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = server.App(CONFIG)

    def test_image_paths_stay_inside_scenario_images(self):
        good = self.app.image_path("coffee-shelf", "visits/01/bay.jpg")
        self.assertTrue(good and good.is_file())
        for scenario, rel in (("coffee-shelf", "../visits.json"), ("coffee-shelf", "../../../config.local.json"),
                              ("coffee-shelf", "visits/../../policies/x.jpg"), ("nope", "visits/01/bay.jpg"),
                              ("coffee-shelf", "visits\\01\\bay.jpg")):
            self.assertIsNone(self.app.image_path(scenario, rel))

    def test_daily_budget(self):
        budget = server.DailyBudget(3)
        self.assertTrue(budget.take(2))
        self.assertFalse(budget.take(2))
        self.assertTrue(budget.take(1))
        self.assertEqual(budget.remaining(), 0)

    def test_catalog_hides_configuration(self):
        text = self.app.catalog_json.decode("utf-8")
        self.assertNotIn(CONFIG["endpoint"], text)
        self.assertEqual(len(json.loads(text)["scenarios"]), 3)

    def test_demo_shows_only_live_campaigns_and_chosen_visits(self):
        coffee = self.app.scenarios["coffee-shelf"]
        self.assertEqual(list(coffee["campaigns"]), coffee["demo"]["campaigns"])
        self.assertEqual([v["id"] for v in coffee["visits"]], [c["visit"] for c in coffee["demo"]["cases"]])
        self.assertTrue(all(set(v["expected"]) == set(coffee["campaigns"]) for v in coffee["visits"]))
        view = next(s for s in json.loads(self.app.catalog_json)["scenarios"] if s["id"] == "coffee-shelf")
        files = [d["file"] for d in view["documents"]]
        self.assertEqual(len(files), len(set(files)))  # shared standards appear once
        self.assertEqual({d for c in view["campaigns"] for d in c["documents"]}, {d["id"] for d in view["documents"]})

    def test_audit_rejects_visits_outside_the_demo(self):
        hidden = next(v["id"] for v in server.catalog.load_scenario("coffee-shelf")["visits"]
                      if v["id"] not in {c["id"] for c in self.app.scenarios["coffee-shelf"]["visits"]})
        body = json.dumps({"scenario": "coffee-shelf", "visit": hidden}).encode("utf-8")
        handler = handler_for(self.app, io.BytesIO())
        handler.path, handler.rfile, handler.deadline = "/api/audit", io.BytesIO(body), mock.Mock()
        handler.headers = {"Content-Length": str(len(body)), "Content-Type": "application/json"}
        handler.send_json, handler.stream = mock.Mock(), mock.Mock()
        handler.do_POST()
        handler.stream.assert_not_called()
        self.assertEqual(handler.send_json.call_args.args[0], 400)

    def test_disconnect_keeps_permit_until_calls_finish(self):
        app, release = server.App(CONFIG), threading.Event()

        def slow(*args, **kwargs):
            release.wait(5)
            raise FoundryError("boom")

        wfile = mock.Mock()
        wfile.write.side_effect = BrokenPipeError  # the client leaves immediately
        scenario = app.scenarios["drinks-fridge"]
        app.runs.acquire(blocking=False)
        with mock.patch.object(app.client, "post", side_effect=slow):
            handler_for(app, wfile).stream(scenario, scenario["visits"][:1])
            self.assertEqual(free_permits(app), server.MAX_CONCURRENT_RUNS - 1)  # still held
            release.set()
            for _ in range(100):
                if free_permits(app) == server.MAX_CONCURRENT_RUNS:
                    break
                time.sleep(0.05)
        self.assertEqual(free_permits(app), server.MAX_CONCURRENT_RUNS)

    def test_upstream_error_detail_is_not_streamed(self):
        app = server.App(CONFIG)
        out = io.BytesIO()
        scenario = app.scenarios["drinks-fridge"]
        app.runs.acquire(blocking=False)
        with mock.patch.object(app.client, "post",
                               side_effect=FoundryError("Foundry returned HTTP 400. {secret detail}")), \
                mock.patch("builtins.print"):
            handler_for(app, out).stream(scenario, scenario["visits"][:1])
        events = [json.loads(line) for line in out.getvalue().splitlines()]
        text = out.getvalue().decode("utf-8")
        self.assertNotIn("secret detail", text)
        result = next(e["result"] for e in events if e["event"] == "visit_result")
        self.assertEqual(result["error"], "The model call failed. Try again later.")
        self.assertEqual(free_permits(app), server.MAX_CONCURRENT_RUNS)

    def test_truncated_body_never_starts_an_audit(self):
        app = server.App(CONFIG)
        body = b'{"scenario": "drinks-fridge", "visit": "01"}'  # valid JSON, but shorter than declared
        handler = handler_for(app, io.BytesIO())
        handler.path, handler.rfile, handler.deadline = "/api/audit", io.BytesIO(body), mock.Mock()
        handler.headers = {"Content-Length": str(len(body) + 10), "Content-Type": "application/json"}
        handler.stream = mock.Mock()
        handler.do_POST()
        handler.stream.assert_not_called()
        self.assertEqual(app.budget.remaining(), CONFIG["daily_max_calls"])
        self.assertEqual(free_permits(app), server.MAX_CONCURRENT_RUNS)

    def test_worker_start_failure_releases_permit(self):
        app = server.App(CONFIG)
        scenario = app.scenarios["drinks-fridge"]
        app.runs.acquire(blocking=False)
        with mock.patch.object(server.threading.Thread, "start", side_effect=RuntimeError("no threads")):
            with self.assertRaises(RuntimeError):
                handler_for(app, io.BytesIO()).stream(scenario, scenario["visits"][:1])
        self.assertEqual(free_permits(app), server.MAX_CONCURRENT_RUNS)

    def test_slow_and_excess_connections_are_dropped(self):
        server.Handler.app = self.app
        httpd = server.BoundedServer(("127.0.0.1", 0), server.Handler, max_connections=1)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        address = httpd.server_address
        try:
            with mock.patch.object(server, "REQUEST_DEADLINE", 0.5), mock.patch("builtins.print"):
                slow = socket.create_connection(address, timeout=5)
                slow.sendall(b"GET /healthz HTTP/1.1\r\n")  # never finishes its headers
                time.sleep(0.2)
                extra = socket.create_connection(address, timeout=5)
                self.assertEqual(extra.recv(100), b"")  # no free handler: closed at once
                extra.close()
                self.assertEqual(slow.recv(100), b"")  # dropped at the request deadline
                slow.close()
                time.sleep(0.2)
                ok = socket.create_connection(address, timeout=5)
                ok.sendall(b"GET /healthz HTTP/1.0\r\n\r\n")
                self.assertTrue(ok.recv(100).startswith(b"HTTP/1.0 200"))
                ok.close()
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
