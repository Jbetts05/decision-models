"""Cloud boundary checks; opt in to real PostgreSQL checks with CLOUD_BACKEND_INTEGRATION=1."""

import http.client
import json
import os
import threading
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import psycopg
from psycopg import sql

from traversal.age import connect
from traversal.foundry import Foundry, InferenceError, load_config
from traversal.server import (
    AdmissionError, AppStore, ComparisonServer, Handler, RUN_RESERVATION,
    Service, initialize_app_store, public_origin,
)

ENDPOINT = "https://example.cognitiveservices.azure.com"
ORIGIN = "https://demo.example.azurecontainerapps.io"


class ConfigurationTests(unittest.TestCase):
    def test_environment_configuration_without_local_file(self):
        env = {
            "FOUNDRY_ENDPOINT": ENDPOINT, "DECISION_DEPLOYMENT": "Decision-1",
            "LLM_DEPLOYMENT": "gpt-6-sol", "FOUNDRY_AUTH_MODE": "managed_identity",
            "SERVER_DAILY_MAX_CALLS": "1000",
            "FOUNDRY_PRICING_JSON": '{"source":"dated operator-supplied rates","decision":{"input":null,"output":null}}',
        }
        with patch.dict(os.environ, env, clear=True), patch.object(Path, "exists", return_value=False):
            config = load_config()
        self.assertEqual(config["endpoint"], ENDPOINT)
        self.assertEqual(config["baseline_deployment"], "gpt-6-sol")
        self.assertEqual(config["server_daily_max_calls"], 1000)
        self.assertIsNone(config["pricing"]["decision"]["input"])

    def test_existing_file_and_environment_override(self):
        saved = {"endpoint": ENDPOINT, "decision_deployment": "old", "baseline_deployment": "local",
                 "baseline_reasoning_effort": "medium"}
        with patch.dict(os.environ, {"DECISION_DEPLOYMENT": "new"}, clear=True), \
                patch.object(Path, "exists", return_value=True), \
                patch.object(Path, "read_text", return_value=json.dumps(saved)):
            config = load_config("settings.json")
        self.assertEqual(config["decision_deployment"], "new")
        self.assertEqual(config["baseline_deployment"], "local")
        self.assertEqual(config["baseline_reasoning_effort"], "medium")

    def test_missing_and_invalid_configuration_fails_explicitly(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(Path, "exists", return_value=False):
            with self.assertRaisesRegex(ValueError, "Configure endpoint"):
                load_config()
        with patch.dict(os.environ, {"SERVER_DAILY_MAX_CALLS": "not-an-int"}, clear=True), \
                patch.object(Path, "exists", return_value=False):
            with self.assertRaisesRegex(ValueError, "integer"):
                load_config()

    def test_public_origin_is_exact_https(self):
        self.assertEqual(public_origin(ORIGIN), ORIGIN)
        self.assertIsNone(public_origin(None))
        for value in ("http://example.org", "https://user@example.org", ORIGIN + "/",
                      ORIGIN + "?foo=bar", ORIGIN + "#fragment", ORIGIN + ":bad"):
            with self.assertRaises(ValueError, msg=value):
                public_origin(value)

    def test_preloaded_age_does_not_attempt_load(self):
        connection = Mock()
        with patch.dict(os.environ, {"AGE_PRELOADED": "1"}), \
                patch("traversal.age.psycopg.connect", return_value=connection):
            self.assertIs(connect("unused", initialize=True), connection)
        statements = [call.args[0] for call in connection.execute.call_args_list]
        self.assertIn("CREATE EXTENSION IF NOT EXISTS age", statements)
        self.assertNotIn("LOAD 'age'", statements)

    def test_load_permission_error_is_not_silenced(self):
        connection = Mock()
        connection.execute.side_effect = psycopg.errors.InsufficientPrivilege("LOAD denied")
        with patch.dict(os.environ, {}, clear=True), \
                patch("traversal.age.psycopg.connect", return_value=connection):
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                connect("unused")
        connection.close.assert_called_once()


class AuthenticationAndCallTests(unittest.TestCase):
    def test_streamed_model_io_is_frozen_exact_and_excludes_credentials_and_hidden_fields(self):
        model = Foundry({"endpoint": ENDPOINT})
        events = []
        model.emit = events.append
        body = {"model": "Sol", "messages": [{"role": "user", "content": "Original input"}]}
        payload = {"usage": {"input_tokens": 12, "output_tokens": 3},
                   "choices": [{"finish_reason": "stop", "message": {
                       "role": "assistant", "content": '{"kind":"query"}',
                       "reasoning_content": "private provider field",
                   }}]}
        response = Mock()
        response.read.return_value = json.dumps(payload).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch.object(model, "headers", return_value={"Authorization": "Bearer test-secret"}), \
                patch("traversal.foundry.urllib.request.urlopen", return_value=response) as http:
            model.post("baseline", "/openai/v1/chat/completions", body)
        sent = json.loads(http.call_args.args[0].data)
        body["messages"].append({"role": "assistant", "content": "Future response"})
        self.assertEqual([event["event"] for event in events], ["model_request", "model_response"])
        self.assertEqual(events[0]["request"], sent)
        self.assertEqual(model.calls[0]["request"], sent)
        self.assertEqual(len(events[0]["request"]["messages"]), 1)
        self.assertEqual(events[1]["response"]["choices"][0]["message"]["content"], '{"kind":"query"}')
        self.assertEqual(events[1]["usage"], {"input_tokens": 12, "output_tokens": 3})
        self.assertNotIn("test-secret", json.dumps(events))
        self.assertNotIn("reasoning_content", json.dumps(events))
        self.assertNotIn("private provider field", json.dumps(events))
        self.assertNotIn("reasoning_content", json.dumps(model.calls))
        self.assertNotIn("private provider field", json.dumps(model.calls))

    def test_failed_model_call_emits_explicit_response_without_http_error_body(self):
        import urllib.error
        model, events = Foundry({"endpoint": ENDPOINT}), []
        model.emit = events.append
        with patch.object(model, "headers", return_value={}), \
                patch("traversal.foundry.urllib.request.urlopen",
                      side_effect=urllib.error.HTTPError(ENDPOINT, 429, "rate limited", {}, None)):
            with self.assertRaises(InferenceError):
                model.post("baseline", "/test", {"model": "Sol"})
        self.assertEqual(events[-1]["status"], "failed")
        self.assertEqual(events[-1]["error"], "Foundry HTTP 429")

    def priced_post(self, usage, rates=None):
        model = Foundry({
            "endpoint": ENDPOINT,
            "pricing": {"baseline": rates if rates is not None else {
                "input": 2, "output": 10, "cached_input": .20,
            }},
        })
        response = Mock()
        response.read.return_value = json.dumps({"usage": usage}).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch.object(model, "headers", return_value={}), \
                patch("traversal.foundry.urllib.request.urlopen", return_value=response):
            model.post("baseline", "/test", {"model": "gpt-6-sol"})
        return model.calls[0]

    def test_actual_cached_usage_is_preserved_and_discounted(self):
        for input_key, output_key, details_key in (
            ("prompt_tokens", "completion_tokens", "prompt_tokens_details"),
            ("input_tokens", "output_tokens", "input_tokens_details"),
        ):
            with self.subTest(details=details_key):
                record = self.priced_post({
                    input_key: 1000, output_key: 100, details_key: {"cached_tokens": 600},
                })
                self.assertEqual(record["usage"]["cached_input_tokens"], 600)
                self.assertEqual(record["usage"]["input_tokens"], 1000)
                self.assertAlmostEqual(record["estimated_cost_usd"], (400 * 2 + 600 * .20 + 100 * 10) / 1_000_000)

    def test_absent_cache_usage_is_not_invented(self):
        record = self.priced_post({"prompt_tokens": 1000, "completion_tokens": 100})
        self.assertNotIn("cached_input_tokens", record["usage"])
        self.assertAlmostEqual(record["estimated_cost_usd"], .003)

    def test_reported_zero_cache_and_zero_cached_price_are_supported(self):
        for cached, price in ((0, .20), (1000, 0)):
            record = self.priced_post({
                "input_tokens": 1000, "output_tokens": 100,
                "input_tokens_details": {"cached_tokens": cached},
            }, {"input": 2, "output": 10, "cached_input": price})
            self.assertEqual(record["usage"]["cached_input_tokens"], cached)
            self.assertAlmostEqual(record["estimated_cost_usd"],
                                   ((1000 - cached) * 2 + cached * price + 100 * 10) / 1_000_000)

    def test_unknown_cached_rate_does_not_fabricate_a_cost(self):
        record = self.priced_post({
            "input_tokens": 1000, "output_tokens": 100,
            "input_tokens_details": {"cached_tokens": 600},
        }, {"input": 2, "output": 10})
        self.assertEqual(record["usage"]["cached_input_tokens"], 600)
        self.assertIsNone(record["estimated_cost_usd"])
        record = self.priced_post({"input_tokens": 1000, "output_tokens": 100},
                                 {"input": 2, "output": 10, "cached_input": None})
        self.assertAlmostEqual(record["estimated_cost_usd"], .003)

    def test_invalid_cached_usage_is_rejected(self):
        for cached in (-1, 1001, True, "600", None, 1.5):
            with self.subTest(cached=cached), self.assertRaisesRegex(InferenceError, "cached input"):
                self.priced_post({
                    "input_tokens": 1000, "output_tokens": 100,
                    "input_tokens_details": {"cached_tokens": cached},
                })
        with self.assertRaisesRegex(InferenceError, "conflicting cached"):
            self.priced_post({
                "input_tokens": 1000, "output_tokens": 100, "cached_input_tokens": 500,
                "input_tokens_details": {"cached_tokens": 600},
            })

    def test_invalid_cached_price_is_rejected(self):
        for price in (-1, True, float("nan"), float("inf"), "0.2"):
            with self.subTest(price=price), self.assertRaisesRegex(InferenceError, "token prices"):
                self.priced_post({
                    "input_tokens": 1000, "output_tokens": 100,
                    "input_tokens_details": {"cached_tokens": 600},
                }, {"input": 2, "output": 10, "cached_input": price})

    def test_managed_identity_ignores_api_key_and_cli(self):
        credential = Mock()
        credential.get_token.return_value = SimpleNamespace(token="test-token", expires_on=time.time() + 3600)
        with patch.dict(os.environ, {"AZURE_API_KEY": "not-used", "AZURE_CLIENT_ID": "identity-id"}), \
                patch("azure.identity.ManagedIdentityCredential", return_value=credential) as constructor, \
                patch("traversal.foundry.subprocess.run") as cli:
            model = Foundry({"endpoint": ENDPOINT, "auth_mode": "managed_identity"})
            self.assertEqual(model.headers(), {"Authorization": "Bearer test-token"})
            self.assertEqual(model.headers(), {"Authorization": "Bearer test-token"})
        constructor.assert_called_once_with(client_id="identity-id")
        credential.get_token.assert_called_once_with("https://cognitiveservices.azure.com/.default")
        cli.assert_not_called()

    def test_managed_identity_failure_has_no_fallback(self):
        credential = Mock()
        credential.get_token.side_effect = RuntimeError("identity unavailable")
        with patch("azure.identity.ManagedIdentityCredential", return_value=credential), \
                patch("traversal.foundry.subprocess.run") as cli:
            model = Foundry({"endpoint": ENDPOINT, "auth_mode": "managed_identity"})
            with self.assertRaisesRegex(InferenceError, "Managed identity"):
                model.headers()
        cli.assert_not_called()

    def test_local_cli_subscription_is_preserved(self):
        result = SimpleNamespace(returncode=0, stdout=json.dumps({
            "accessToken": "cli-test-token", "expires_on": time.time() + 3600,
        }))
        with patch.dict(os.environ, {}, clear=True), \
                patch("traversal.foundry.shutil.which", return_value="az"), \
                patch("traversal.foundry.subprocess.run", return_value=result) as cli:
            model = Foundry({"endpoint": ENDPOINT, "subscription": "selected-subscription"})
            self.assertEqual(model.headers(), {"Authorization": "Bearer cli-test-token"})
        self.assertIn("selected-subscription", cli.call_args.args[0])

    def test_call_is_durable_before_http_and_usage_is_real(self):
        order = []
        payload = {"usage": {"input_tokens": 123, "output_tokens": 17}}
        response = Mock()
        response.read.return_value = json.dumps(payload).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        model = Foundry({"endpoint": ENDPOINT})
        model.record_call = lambda record, index: order.append((record["status"], index))

        def send(*args, **kwargs):
            self.assertEqual(order, [("attempted", 1)])
            return response

        with patch.object(model, "headers", return_value={}), \
                patch("traversal.foundry.urllib.request.urlopen", side_effect=send) as http:
            self.assertEqual(model.post("decision", "/test", {"model": "Decision-1"}), payload)
        http.assert_called_once()
        self.assertEqual(order, [("attempted", 1), ("response_received", 1)])
        self.assertEqual(model.calls[0]["usage"], {"input_tokens": 123, "output_tokens": 17})
        self.assertIsNone(model.calls[0]["estimated_cost_usd"])

    def test_database_failure_prevents_inference(self):
        model = Foundry({"endpoint": ENDPOINT})
        model.record_call = Mock(side_effect=psycopg.OperationalError("database unavailable"))
        with patch.object(model, "headers", return_value={}), \
                patch("traversal.foundry.urllib.request.urlopen") as http:
            with self.assertRaises(psycopg.OperationalError):
                model.post("decision", "/test", {"model": "Decision-1"})
        http.assert_not_called()

    def test_failed_http_is_recorded_without_retry(self):
        model = Foundry({"endpoint": ENDPOINT})
        statuses = []
        model.record_call = lambda record, index: statuses.append(record["status"])
        with patch.object(model, "headers", return_value={}), \
                patch("traversal.foundry.urllib.request.urlopen", side_effect=TimeoutError) as http:
            with self.assertRaises(InferenceError):
                model.post("decision", "/test", {"model": "Decision-1"})
        http.assert_called_once()
        self.assertEqual(statuses, ["attempted", "failed"])


class HttpBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.server = ComparisonServer(("127.0.0.1", 0), Handler)
        self.server.public_origin = ORIGIN
        self.server.service = Mock()
        self.server.service.queries = {"case": {"id": "case", "vehicle_id": "vehicle",
                                                "question": "Question", "evidence": []}}
        self.server.service.catalog.return_value = {"remaining_calls": 1000}
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, method, path, headers=None, body=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        request_headers = {"Host": "demo.example.azurecontainerapps.io", **(headers or {})}
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_proxy_https_same_origin_without_trusting_forwarded_host(self):
        self.assertEqual(self.request("GET", "/api/catalog", {"Origin": ORIGIN})[0], 200)
        self.assertEqual(self.request("GET", "/api/catalog", {"Origin": "https://attacker.example"})[0], 403)
        self.assertEqual(self.request("GET", "/api/catalog", {
            "Host": "attacker.example", "X-Forwarded-Host": "demo.example.azurecontainerapps.io",
            "X-Forwarded-Proto": "https", "Origin": ORIGIN,
        })[0], 403)

    def test_health_probes_and_readiness_failure_do_not_infer(self):
        self.assertEqual(self.request("GET", "/health/live", {"Host": "127.0.0.1"})[0], 200)
        self.assertEqual(self.request("GET", "/health/ready", {"Host": "127.0.0.1"})[0], 200)
        self.server.service.ready.side_effect = psycopg.OperationalError("sensitive connection detail")
        status, _, body = self.request("GET", "/health/ready")
        self.assertEqual(status, 503)
        self.assertNotIn(b"sensitive", body)
        self.server.service.compare.assert_not_called()

    def test_durable_admission_rejection_is_429_with_retry_header(self):
        self.server.service.admit.side_effect = AdmissionError("A comparison is already running.")
        status, headers, body = self.request("POST", "/api/run", {
            "Origin": ORIGIN, "Content-Type": "application/json",
        }, json.dumps({"case_id": "case"}))
        self.assertEqual(status, 429)
        self.assertEqual(headers["Retry-After"], "30")
        self.server.service.compare.assert_not_called()

    def test_ndjson_contract_and_no_auth_gate(self):
        def compare(query, scorable, publish, reservation):
            publish({"event": "current", "method": "decision", "node": "node"})
            publish({"event": "complete", "method": "decision", "result": {"status": "clarify"}})

        self.server.service.compare.side_effect = compare
        status, headers, body = self.request("POST", "/api/run", {
            "Origin": ORIGIN, "Content-Type": "application/json",
        }, json.dumps({"case_id": "case"}))
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/x-ndjson")
        self.assertEqual([json.loads(line)["event"] for line in body.splitlines()], ["current", "complete"])

    def test_unhashable_case_id_is_a_bad_request_not_an_unhandled_error(self):
        status, _, _ = self.request("POST", "/api/run", {
            "Origin": ORIGIN, "Content-Type": "application/json",
        }, json.dumps({"case_id": []}))
        self.assertEqual(status, 400)
        self.server.service.admit.assert_not_called()

    def test_staged_inputs_and_release_endpoints_are_not_public_demo_operations(self):
        self.assertEqual(self.request("GET", "/api/release/" + "a" * 32)[0], 404)
        self.server.service.release.assert_not_called()
        for extra in ({"previous_run_id": "a" * 32}, {"previous_run_id": {"bad": "input"}}):
            status, _, body = self.request("POST", "/api/run", {
                "Origin": ORIGIN, "Content-Type": "application/json",
            }, json.dumps({"case_id": "case", **extra}))
            self.assertEqual(status, 400)
            self.assertIn(b"upfront", body)
        self.server.service.queries["case"]["turn"] = 1
        self.assertEqual(self.request("POST", "/api/run", {
            "Origin": ORIGIN, "Content-Type": "application/json",
        }, json.dumps({"case_id": "case"}))[0], 400)
        self.server.service.continue_query.assert_not_called()
        self.server.service.admit.assert_not_called()


class ResultPersistenceTests(unittest.TestCase):
    def service(self):
        service = Service.__new__(Service)
        service.config = {"endpoint": ENDPOINT}
        service.dsn = "unused"
        service.name = "traversal_123456789abc"
        service.manifest = {"dataset_version": "test", "graph_sha256": "test"}
        service.records = Mock()
        service.result_files = False
        service.oracle = {}
        self.enterContext(patch("traversal.server.resolve_decision_entry", return_value={
            "status": "resolved", "target": "state", "path": [], "messages": [],
            "query": {"id": "case", "start_node": "state"},
        }))
        return service

    def test_terminal_events_only_follow_durable_record(self):
        service = self.service()
        order = []
        service.records.finish.side_effect = lambda *args: order.append("persist")
        model = Mock(calls=[], credential=None)
        graph = Mock(query_count=1, query_ms=1)
        result = {"status": "clarify", "target": "action", "path": []}
        with patch("traversal.server.Foundry", return_value=model), \
                patch("traversal.server.AgeGraph", return_value=graph), \
                patch("traversal.server.decision_walk", return_value=result), \
                patch("traversal.server.llm_cypher", return_value=result):
            service.compare({"id": "case"}, False, lambda event: order.append(event["event"]), "reserved")
        self.assertEqual(order.count("lane_ready"), 2)
        self.assertTrue(all(index < order.index("persist") for index, event in enumerate(order)
                            if event == "lane_ready"))
        self.assertEqual(order[order.index("persist"):], ["persist", "complete", "complete", "complete"])
        args = service.records.finish.call_args.args
        self.assertEqual(args[0], "reserved")
        self.assertEqual(args[1]["source"], "live_foundry_and_apache_age")
        self.assertIsNone(args[2])

    def test_inference_failures_are_explicit_error_records(self):
        service = self.service()
        events = []
        model = Mock(calls=[], credential=None)
        graph = Mock(query_count=0, query_ms=0)
        with patch("traversal.server.Foundry", return_value=model), \
                patch("traversal.server.AgeGraph", return_value=graph), \
                patch("traversal.server.decision_walk", side_effect=InferenceError("Decision failed")), \
                patch("traversal.server.llm_cypher", side_effect=InferenceError("LLM failed")):
            service.compare({"id": "case"}, False, events.append, "reserved")
        self.assertTrue(all(event["result"]["status"] == "error" for event in events
                            if event["event"] == "complete" and event["method"] != "entry"))
        self.assertIn("Decision failed", service.records.finish.call_args.args[2])
        self.assertIn("LLM failed", service.records.finish.call_args.args[2])

    def test_lane_metrics_are_published_before_waiting_for_the_peer_in_either_order(self):
        for first in ("decision", "llm-cypher"):
            for fail in (False, True):
                with self.subTest(first=first, fail=fail):
                    service, events = self.service(), []
                    slow_started, first_ready = threading.Event(), threading.Event()
                    result = {"status": "next_action", "target": "action", "path": []}

                    def execute(method):
                        if method != first:
                            slow_started.set()
                            if not first_ready.wait(2):
                                raise AssertionError("The fast lane was withheld while its peer was running.")
                        else:
                            if not slow_started.wait(2):
                                raise AssertionError("The peer did not start independently.")
                            if fail:
                                raise InferenceError("Fast lane failed")
                        return result

                    def publish(event):
                        events.append(event)
                        if event["event"] == "lane_ready":
                            self.assertFalse(service.records.finish.called)
                            self.assertIsNone(event["expected"])
                            if event["method"] == first:
                                first_ready.set()

                    with patch("traversal.server.Foundry", return_value=Mock(calls=[], credential=None)), \
                            patch("traversal.server.AgeGraph", return_value=Mock(query_count=1, query_ms=1)), \
                            patch("traversal.server.decision_walk", side_effect=lambda *a, **k: execute("decision")), \
                            patch("traversal.server.llm_cypher", side_effect=lambda *a, **k: execute("llm-cypher")):
                        service.compare({"id": "case"}, False, publish, "reserved")
                    ready = [event for event in events if event["event"] == "lane_ready"]
                    self.assertEqual([event["method"] for event in ready],
                                     [first, "llm-cypher" if first == "decision" else "decision"])
                    self.assertEqual(ready[0]["result"]["status"], "error" if fail else "next_action")
                    self.assertEqual(ready[1]["result"]["status"], "next_action")
                    for early in ready:
                        final = next(event for event in events if event["event"] == "complete"
                                     and event["method"] == early["method"])
                        for key in ("result", "elapsed_ms", "inference_calls", "input_tokens",
                                    "output_tokens", "estimated_cost_usd", "graph_queries"):
                            self.assertEqual(early[key], final[key])

    def test_persistence_failure_does_not_publish_terminal_success(self):
        service = self.service()
        service.records.finish.side_effect = psycopg.OperationalError("unavailable")
        model = Mock(calls=[], credential=None)
        graph = Mock(query_count=1, query_ms=1)
        events = []
        result = {"status": "clarify", "target": "action", "path": []}
        with patch("traversal.server.Foundry", return_value=model), \
                patch("traversal.server.AgeGraph", return_value=graph), \
                patch("traversal.server.decision_walk", return_value=result), \
                patch("traversal.server.llm_cypher", return_value=result):
            with self.assertRaises(psycopg.OperationalError):
                service.compare({"id": "case"}, False, events.append, "reserved")
        self.assertEqual(sum(event["event"] == "lane_ready" for event in events), 2)
        self.assertFalse(any(event["event"] == "complete" for event in events))

    def test_independent_standalone_costs_sum_to_physical_call_count(self):
        service, events = self.service(), []

        def call(deployment):
            return {"deployment": deployment, "usage": {"input_tokens": 100, "output_tokens": 10},
                    "estimated_cost_usd": .001}

        def entry(graph, model, query, **kwargs):
            model.calls.append(call("Decision-1"))
            return {"status": "resolved", "target": "state", "path": [], "messages": [],
                    "query": {"id": "case", "start_node": "state"}}

        def walk(graph, model, *args, **kwargs):
            model.calls.append(call("Decision-1"))
            return {"status": "next_action", "target": "action", "path": []}

        def baseline(graph, model, *args, **kwargs):
            model.calls.append(call("Sol"))
            return {"status": "next_action", "target": "action", "path": []}

        with patch("traversal.server.Foundry", side_effect=lambda config: Mock(calls=[], credential=None)), \
                patch("traversal.server.AgeGraph", side_effect=lambda *args, **kwargs: Mock(query_count=2, query_ms=3)), \
                patch("traversal.server.resolve_decision_entry", side_effect=entry) as resolver, \
                patch("traversal.server.decision_walk", side_effect=walk), \
                patch("traversal.server.llm_cypher", side_effect=baseline):
            service.compare({"id": "case"}, False, events.append, "reserved")
        resolver.assert_called_once()
        record = service.records.finish.call_args.args[1]
        self.assertEqual(record["actual_inference_calls"], 3)
        for result in record["results"]:
            hybrid = result["method"] == "decision"
            self.assertEqual(result["inference_calls"], 2 if hybrid else 1)
            self.assertEqual(result["input_tokens"], 200 if hybrid else 100)
            self.assertEqual(result["graph_queries"], 4 if hybrid else 2)
            self.assertAlmostEqual(result["estimated_cost_usd"], .002 if hybrid else .001)
            if hybrid:
                self.assertEqual(result["entry_metrics"]["inference_calls"], 1)
            else:
                self.assertIsNone(result["entry_metrics"])
            self.assertEqual(result["traversal_metrics"]["inference_calls"], 1)
        self.assertEqual(record["results"][0]["model_calls_by_deployment"], {"Decision-1": 2})
        self.assertEqual(record["results"][1]["model_calls_by_deployment"], {"Sol": 1})
        self.assertEqual(sum(result["inference_calls"] for result in record["results"]),
                         record["actual_inference_calls"])

    def test_failed_hybrid_entry_does_not_block_independent_sol_lane(self):
        service, events = self.service(), []
        with patch("traversal.server.Foundry", return_value=Mock(calls=[], credential=None)), \
                patch("traversal.server.AgeGraph", return_value=Mock(query_count=0, query_ms=0)), \
                patch("traversal.server.resolve_decision_entry", side_effect=InferenceError("Entry failed")), \
                patch("traversal.server.decision_walk") as walk, \
                patch("traversal.server.llm_cypher", return_value={
                    "status": "next_action", "target": "action", "path": []}) as baseline:
            service.compare({"id": "case"}, False, events.append, "reserved")
        walk.assert_not_called()
        baseline.assert_called_once()
        self.assertEqual(baseline.call_args.args[2], {"id": "case"})
        self.assertNotIn("entry_messages", baseline.call_args.kwargs)
        self.assertIn("Entry failed", service.records.finish.call_args.args[2])
        self.assertEqual(len([event for event in events if event["event"] == "complete"]), 3)
        sol = next(event for event in events if event["event"] == "complete"
                   and event["method"] == "llm-cypher")
        self.assertEqual(sol["result"]["status"], "next_action")

    def test_only_own_md1_entry_is_reused_and_legacy_sol_entry_is_reselected(self):
        for resolver, reuse in (("md1", True), ("sol", False)):
            service, events = self.service(), []
            previous = {"results": [], "entry": {"result": {
                "status": "resolved", "target": "state", "resolver": resolver}}}
            query = {"id": "case", "vehicle_id": "vehicle", "_previous_record": previous}
            result = {"status": "next_action", "target": "action", "path": []}
            with patch("traversal.server.Foundry", return_value=Mock(calls=[], credential=None)), \
                    patch("traversal.server.AgeGraph", return_value=Mock(query_count=1, query_ms=1)), \
                    patch("traversal.server.resolve_decision_entry", return_value={
                        "status": "resolved", "target": "state", "messages": [],
                        "resolver": "md1", "query": {"id": "case", "start_node": "state"}}) as select, \
                    patch("traversal.runtime.validate_entry") as validate, \
                    patch("traversal.server.decision_walk", return_value=result), \
                    patch("traversal.server.llm_cypher", return_value=result):
                service.compare(query, False, events.append, "reserved")
            self.assertEqual(select.call_count, 0 if reuse else 1)
            self.assertEqual(validate.call_count, 1 if reuse else 0)
            selected = [event for event in events if event["event"] == "entry_selected"]
            self.assertEqual(len(selected), 1 if reuse else 0)
            self.assertEqual(service.records.finish.call_args.args[1]["workflow"], "md1-entry-v1")

    def test_raw_intake_expectation_is_scored_not_fixture_scoped_path(self):
        service, events = self.service(), []
        service.oracle = {"case": {"status": "unsupported", "target": None, "path": [],
                                   "entry_expectation": {"status": "clarify", "target": None}}}
        result = {"status": "clarify", "target": None, "path": []}
        with patch("traversal.server.Foundry", side_effect=lambda config: Mock(calls=[], credential=None)), \
                patch("traversal.server.AgeGraph", return_value=Mock(query_count=1, query_ms=1)), \
                patch("traversal.server.resolve_decision_entry", return_value={**result, "messages": []}), \
                patch("traversal.server.llm_cypher", return_value=result):
            service.compare({"id": "case"}, True, events.append, "reserved")
        for event in events:
            if event["event"] == "complete" and event["method"] != "entry":
                self.assertTrue(event["score"]["exact"])
                self.assertEqual(event["expected"]["status"], "clarify")

    def test_catalog_has_raw_inputs_without_graph_or_oracle_and_does_not_prefetch(self):
        config = {"decision_deployment": "Decision-1", "baseline_deployment": "Sol"}
        with patch("traversal.server.AgeGraph") as graph, \
                patch("traversal.server.initialize_app_store"), \
                patch("traversal.server.AppStore", return_value=Mock(remaining=Mock(return_value=1000))):
            service = Service("unused", config, Path("data") / "traversal")
        graph.assert_not_called()
        cases = service.catalog()["cases"]
        fixtures = [json.loads(line) for line in (Path("data") / "traversal" / "queries.jsonl").read_text().splitlines()]
        self.assertEqual(len(cases), sum(q.get("turn", 0) == 0 for q in fixtures) + 10)
        by_id = {fixture["id"]: fixture for fixture in fixtures}
        for case in cases:
            fields = {"id", "vehicle_id", "vehicle", "title", "question",
                      "evidence", "demo", "category", "intent", "input_kind"}
            self.assertEqual(set(case), fields)
            if case["input_kind"] == "problem":
                self.assertEqual(case["question"], by_id[case["id"]]["question"])
            self.assertTrue(all(set(item) == {"check", "observation"} for item in case["evidence"]))


@unittest.skipUnless(os.environ.get("CLOUD_BACKEND_INTEGRATION") == "1",
                     "Set CLOUD_BACKEND_INTEGRATION=1 for real PostgreSQL admission tests.")
class PostgresAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from traversal.__main__ import database_url
        cls.dsn = database_url()
        initialize_app_store(cls.dsn, app_role=None)

    def setUp(self):
        self.key = "test-" + uuid.uuid4().hex
        self.store = AppStore(self.dsn, 1000, self.key)

    def tearDown(self):
        with psycopg.connect(self.dsn) as connection:
            connection.execute("""
                DELETE FROM traversal_app.calls WHERE run_id IN
                (SELECT id FROM traversal_app.runs WHERE budget_key = %s)
            """, (self.key,))
            connection.execute("DELETE FROM traversal_app.runs WHERE budget_key = %s", (self.key,))
            connection.execute("DELETE FROM traversal_app.budgets WHERE budget_key = %s", (self.key,))

    def reserve(self, store=None):
        return (store or self.store).reserve("traversal_123456789abc", {"id": "test"}, True)

    def test_replicas_cannot_bypass_concurrency_and_restart_does_not_reset(self):
        other = AppStore(self.dsn, 1000, self.key)
        barrier = threading.Barrier(2)

        def attempt(store):
            barrier.wait()
            try:
                return self.reserve(store)
            except AdmissionError:
                return None

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(attempt, (self.store, other)))
        self.assertEqual(sum(result is not None for result in results), 1)
        restarted = AppStore(self.dsn, 1000, self.key)
        self.assertEqual(restarted.remaining(), 1000 - RUN_RESERVATION)
        with self.assertRaises(AdmissionError):
            self.reserve(restarted)

    def test_failed_and_completed_runs_have_durable_attempts_and_usage(self):
        identifier = self.reserve()
        self.store.call(identifier, "decision", 1, {"status": "attempted", "usage": None})
        self.store.call(identifier, "decision", 1, {
            "status": "response_received", "usage": {"input_tokens": 45, "output_tokens": 4},
        })
        self.store.finish(identifier, {"results": []}, "Explicit model failure")
        self.store.finish(identifier, {"ignored": True})
        self.assertEqual(self.store.remaining(), 999)
        with self.store.connection() as connection:
            status, error, record = connection.execute(
                "SELECT status, error, record FROM traversal_app.runs WHERE id = %s", (identifier,)
            ).fetchone()
            call = connection.execute(
                "SELECT record FROM traversal_app.calls WHERE run_id = %s", (identifier,)
            ).fetchone()[0]
        self.assertEqual(status, "error")
        self.assertEqual(error, "Explicit model failure")
        self.assertEqual(record, {"results": []})
        self.assertEqual(call["usage"]["input_tokens"], 45)
        completed = self.reserve()
        self.store.finish(completed, {"results": []})
        with self.store.connection() as connection:
            self.assertEqual(connection.execute(
                "SELECT status FROM traversal_app.runs WHERE id = %s", (completed,)
            ).fetchone()[0], "completed")

    def test_daily_limit_cannot_be_raised_by_restart_or_replica(self):
        limited = AppStore(self.dsn, RUN_RESERVATION, self.key)
        identifier = self.reserve(limited)
        limited.call(identifier, "decision", 1, {"status": "failed"})
        limited.finish(identifier, error="test")
        larger = AppStore(self.dsn, 1000, self.key)
        self.assertEqual(larger.remaining(), RUN_RESERVATION - 1)
        with self.assertRaises(AdmissionError):
            self.reserve(larger)

    def test_allowances_and_terminal_run_block_more_calls(self):
        identifier = self.reserve()
        for method, index in (("entry", 4), ("decision", 17), ("llm-cypher", 6), ("unknown", 1)):
            with self.assertRaises(InferenceError):
                self.store.call(identifier, method, index, {})
        self.store.finish(identifier, error="test")
        with self.assertRaises(InferenceError):
            self.store.call(identifier, "decision", 1, {})

    def test_old_method_constraint_migrates_without_losing_attempts(self):
        identifier = self.reserve()
        self.store.call(identifier, "decision", 1, {"status": "old_attempt"})
        try:
            with psycopg.connect(self.dsn) as connection:
                connection.execute("ALTER TABLE traversal_app.calls DROP CONSTRAINT calls_method_check")
                connection.execute("""
                    ALTER TABLE traversal_app.calls ADD CONSTRAINT calls_method_check
                    CHECK (method IN ('decision', 'llm-cypher')) NOT VALID
                """)
            initialize_app_store(self.dsn, app_role=None)
            self.store.call(identifier, "entry", 1, {"status": "new_attempt"})
            with psycopg.connect(self.dsn) as connection:
                rows = connection.execute(
                    "SELECT method, record FROM traversal_app.calls WHERE run_id = %s ORDER BY method", (identifier,)
                ).fetchall()
            self.assertEqual(rows, [("decision", {"status": "old_attempt"}), ("entry", {"status": "new_attempt"})])
            self.store.finish(identifier, {"results": []})
            self.assertEqual(self.store.remaining(), 998)
        finally:
            initialize_app_store(self.dsn, app_role=None)

    def test_previous_day_running_reservation_still_blocks_admission(self):
        identifier = self.reserve()
        with self.store.connection() as connection:
            connection.execute("""
                INSERT INTO traversal_app.budgets (budget_key, day, call_limit, reserved_calls)
                VALUES (%s, CURRENT_DATE - 1, 1000, 21)
            """, (self.key,))
            connection.execute(
                "UPDATE traversal_app.runs SET day = CURRENT_DATE - 1 WHERE id = %s", (identifier,)
            )
        with self.assertRaises(AdmissionError):
            self.reserve()

    def test_initializer_grants_runtime_without_admin_privileges(self):
        role_name = "test_app_" + uuid.uuid4().hex[:12]
        with psycopg.connect(self.dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE").format(
                sql.Identifier(role_name)))
        try:
            initialize_app_store(self.dsn, app_role=role_name)
            with psycopg.connect(self.dsn, autocommit=True) as connection:
                connection.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role_name)))
                self.assertTrue(connection.execute(
                    "SELECT pg_has_role(current_user, 'traversal_reader', 'MEMBER')"
                ).fetchone()[0])
                connection.execute("SELECT id FROM traversal_app.runs LIMIT 0")
                connection.execute("UPDATE traversal_app.budgets SET reserved_calls = reserved_calls WHERE false")
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    connection.execute("CREATE TABLE traversal_app.must_not_create (id int)")
                connection.execute("SET ROLE traversal_reader")
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    connection.execute("SELECT * FROM traversal_app.runs LIMIT 0")
        finally:
            with psycopg.connect(self.dsn, autocommit=True) as connection:
                connection.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role_name)))
                connection.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role_name)))


if __name__ == "__main__":
    unittest.main()
