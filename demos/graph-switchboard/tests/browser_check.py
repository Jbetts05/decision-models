"""Browser checks against the real service; --live makes paid model calls."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


METHODS = ("decision", "llm-cypher")
TRACES = ("entry", *METHODS)
CAPTURE_RUN_RESPONSE = r"""options => {
    const {pathname = "/api/run", method = "POST"} = options || {};
    if (window.runCaptureInstalled) throw new Error("Response capture already installed.");
    window.runCaptureInstalled = true;
    window.runResponseCapture = null;
    window.runResponseCaptureCount = 0;
    const originalFetch = window.fetch;
    window.fetch = async function(input, init) {
        const response = await originalFetch.apply(this, arguments);
        const url = new URL(typeof input === "string" || input instanceof URL ? input : input.url, location.href);
        const requestMethod = (init?.method || input?.method || "GET").toUpperCase();
        if (url.pathname === pathname && requestMethod === method.toUpperCase()) {
            window.runResponseCaptureCount += 1;
            if (!window.runResponseCapture) {
                window.runResponseCapture = response.clone().text().then(body => ({
                    body, status: response.status, url: response.url,
                }), error => ({error: String(error)}));
            }
        }
        return response;
    };
}"""


def assert_empty(page):
    for method in METHODS:
        assert page.locator(f"#{method}-graph .graph-node, #{method}-graph .edge").count() == 0
    for method in TRACES:
        assert page.locator(f"#{method}-steps button").count() == 0
        assert page.locator(f"#{method}-steps time[data-ms]").count() == 0
    assert page.locator("#expected pre").count() == 0
    assert page.locator("#download").is_disabled()


def assert_provenance(snapshots):
    """No graph node/edge may appear before its own lane receives actual AGE data."""
    nodes = {method: set() for method in METHODS}
    edges = {method: {} for method in METHODS}
    for frame in snapshots:
        event = frame["event"]
        if event["event"] == "graph_data":
            lanes = ("decision",) if event["method"] == "entry" else (event["method"],)
            for method in lanes:
                nodes[method].update(node["id"] for node in event["nodes"])
                edges[method].update({edge["id"]: edge for edge in event["edges"]})
        for method in METHODS:
            visible = frame["graphs"][method]
            assert set(visible["nodes"]) <= nodes[method], f"Unreturned node in {method}"
            eligible = {
                key for key, edge in edges[method].items()
                if edge["source"] in nodes[method] and edge["target"] in nodes[method]
            }
            assert set(visible["edges"]) <= eligible, f"Unreturned edge in {method}"
    return nodes, edges


def assert_timings(page, events):
    for method in TRACES:
        own = [event for event in events if event.get("method") == method and event["event"] != "heartbeat"]
        rows = page.locator(f"#{method}-steps button")
        assert rows.count() == len(own)
        for index, event in enumerate(own):
            response = None
            if event["event"] == "model_request":
                response = next((item for item in own[index + 1:] if item["event"] == "model_response"
                                 and item["call_index"] == event["call_index"]), None)
            elif event["event"] == "graph_query":
                response = next((item for item in own[index + 1:] if item["event"] == "graph_rows"
                                 and item["query_id"] == event["query_id"]), None)
            elif event["event"] == "cypher":
                response = next((item for item in own[index + 1:] if item["event"] == "graph_result"), None)
            elif event["event"] == "entry_start":
                response = next((item for item in own[index + 1:] if item["event"] == "entry_ready"), None)
            measured = response or event
            duration = next((measured[key] for key in ("latency_ms", "duration_ms", "query_ms")
                             if measured.get(key) is not None), None)
            if response and duration is None:
                duration = response.get("metrics", {}).get("elapsed_ms")
            row = rows.nth(index)
            assert row.locator("time").count() == 2
            total = row.locator(".step-total")
            assert float(total.get_attribute("data-ms")) == measured["elapsed_ms"]
            step = row.locator(".step-duration")
            if duration is None:
                assert step.text_content() == "--"
                assert step.get_attribute("data-ms") is None
            else:
                assert float(step.get_attribute("data-ms")) == duration
                assert abs(float(step.text_content().removesuffix("s")) * 1000 - duration) <= 5.1


def assert_live_samples(samples):
    running = {}
    completed = {}
    frozen_while_other_running = False
    for sample in samples:
        for row in sample["rows"]:
            key = row["key"]
            if row["state"] == "running":
                running.setdefault(key, []).append((float(row["duration"]), float(row["total"])))
            if row["state"] == "complete":
                values = (row["duration"], row["total"])
                if key in completed:
                    assert values == completed[key], f"Completed row kept ticking: {key}"
                    frozen_while_other_running |= sample["busy"] and sample["other_pending"]
                completed[key] = values
    ticking = [values for values in running.values() if len(values) > 1
               and values[-1][0] > values[0][0] and values[-1][1] > values[0][1]]
    assert ticking, "Did not observe a real pending operation ticking both fields."
    return frozen_while_other_running


def assert_readable_scope(page, method, result, returned_nodes):
    target = result["result"].get("target")
    if not target:
        return
    node = page.locator(f'#{method}-graph [data-node-id="{target}"]')
    assert node.count() == 1
    scope = page.evaluate("([method, id]) => findNode(method, id)?.procedure_id", [method, target])
    if not scope:
        return
    svg = page.locator(f"#{method}-graph svg")
    assert svg.get_attribute("data-procedure-scope") == scope
    assert svg.get_attribute("data-viewport-mode") == "auto"
    graph_box, node_box = page.locator(f"#{method}-graph").bounding_box(), node.bounding_box()
    assert node_box["width"] >= 120, f"{method} selected procedure compressed below readable scale."
    if svg.get_attribute("data-graph-context") == "route":
        route = result["result"]["path"]
        assert page.evaluate("""([method, route, target]) => {
            const data = graphData(method), expected = routeData(data, route, target);
            const ids = [...views[method].nodeElements.keys()];
            const graph = document.getElementById(`${method}-graph`).getBoundingClientRect();
            return ids.length === expected.nodes.length && expected.nodes.every(n => ids.includes(n.id))
                && [...views[method].nodeElements.values()].every(node => {
                    const rect = node.getBoundingClientRect();
                    return rect.top >= graph.top && rect.bottom <= graph.bottom
                        && rect.left >= graph.left && rect.right <= graph.right;
                }) && route.every(id => views[method].edgeElements.get(id)?.path.classList.contains("visited"));
        }""", [method, route, target]), "The final actual route is hidden, unreadable or not highlighted."
        assert "current" in node.get_attribute("class")
        return
    assert node_box["x"] + node_box["width"] > graph_box["x"]
    assert node_box["x"] < graph_box["x"] + graph_box["width"]
    assert node_box["y"] + node_box["height"] > graph_box["y"]
    assert node_box["y"] < graph_box["y"] + graph_box["height"]
    assert abs(node_box["x"] + node_box["width"] / 2 - graph_box["x"] - graph_box["width"] / 2) <= graph_box["width"] * .3
    assert abs(node_box["y"] + node_box["height"] / 2 - graph_box["y"] - graph_box["height"] / 2) <= graph_box["height"] * .3
    assert page.evaluate("""([method, target, scope]) => {
        const view = views[method], graph = document.getElementById(`${method}-graph`).getBoundingClientRect();
        const nearby = graphData(method).edges.flatMap(edge =>
            edge.target === target ? [edge.source] : edge.source === target ? [edge.target] : []);
        return nearby.filter(id => findNode(method, id)?.procedure_id === scope).some(id => {
            const rect = view.nodeElements.get(id)?.getBoundingClientRect();
            return rect && rect.left >= graph.left && rect.right <= graph.right
                && rect.top >= graph.top && rect.bottom <= graph.bottom;
        });
    }""", [method, target, scope]), f"{method} relevant scope context is offscreen."
    assert svg.get_attribute("data-graph-context") == "procedure"
    assert set(page.evaluate("m => graphData(m).nodes.map(n => n.id)", method)) == returned_nodes
    assert page.evaluate("""([method, scope]) => {
        const view = views[method];
        return [...view.nodeElements.keys()].every(id => id === scope || findNode(method, id).procedure_id === scope)
            && [...view.edgeElements.keys()].every(id => findEdge(method, id).type !== "APPLIES_TO");
    }""", [method, scope]), "Applicability context leaked into the diagnostic view."


def assert_fit(page, method):
    page.locator(f'.fit[data-method="{method}"]').click()
    assert page.locator(f"#{method}-graph svg").get_attribute("data-viewport-mode") == "overview"
    assert page.evaluate("""method => {
        const host = document.getElementById(`${method}-graph`).getBoundingClientRect();
        return [...document.querySelectorAll(`#${method}-graph .graph-node`)].every(node => {
            const rect = node.getBoundingClientRect();
            return rect.left >= host.left - 1 && rect.right <= host.right + 1
                && rect.top >= host.top - 1 && rect.bottom <= host.bottom + 1;
        });
    }""", method), "Fit must contain every node in the current view, not hidden retrieved branches."


def assert_context_toggle(page, method, returned_nodes, returned_edges):
    button = page.locator(f'.graph-context[data-method="{method}"]')
    if button.is_disabled():
        visible = page.locator(f"#{method}-graph [data-node-id]").evaluate_all(
            "nodes => nodes.map(n => n.dataset.nodeId)")
        assert set(visible) == returned_nodes, "All retrieved must be available when the route hides other branches."
        return
    selected_ids = page.locator(f"#{method}-graph [data-node-id]").evaluate_all(
        "nodes => nodes.map(n => n.dataset.nodeId)")
    inspector = page.locator(f"#{method}-inspector").inner_text()
    button.click()
    svg = page.locator(f"#{method}-graph svg")
    assert svg.get_attribute("data-graph-context") == "all"
    assert button.get_attribute("aria-pressed") == "true"
    assert set(page.locator(f"#{method}-graph [data-node-id]").evaluate_all(
        "nodes => nodes.map(n => n.dataset.nodeId)")) == returned_nodes
    eligible = {key for key, edge in returned_edges.items()
                if edge["source"] in returned_nodes and edge["target"] in returned_nodes}
    assert set(page.locator(f"#{method}-graph [data-edge-id]").evaluate_all(
        "edges => edges.map(e => e.dataset.edgeId)")) == eligible
    svg.focus()
    page.keyboard.press("+")
    manual = svg.get_attribute("viewBox")
    page.evaluate("() => window.dispatchEvent(new Event('resize'))")
    assert svg.get_attribute("viewBox") == manual
    page.locator(f'.fit[data-method="{method}"]').click()
    assert svg.get_attribute("data-graph-context") == "all"
    button.click()
    expected_context = "route" if page.evaluate("m => Boolean(views[m].answerRoute)", method) else "procedure"
    assert page.locator(f"#{method}-graph svg").get_attribute("data-graph-context") == expected_context
    assert page.locator(f"#{method}-graph svg").get_attribute("data-viewport-mode") == "auto"
    assert page.locator(f"#{method}-graph [data-node-id]").evaluate_all(
        "nodes => nodes.map(n => n.dataset.nodeId)") == selected_ids
    assert page.locator(f"#{method}-inspector").inner_text() == inspector

def assert_independent_lane_metrics(snapshots):
    frozen = {}
    overlap = False
    nodes = {method: {} for method in METHODS}
    for frame in snapshots:
        event = frame["event"]
        if event["event"] == "graph_data":
            method = "decision" if event["method"] == "entry" else event["method"]
            nodes[method].update({node["id"]: node for node in event["nodes"]})
        if event["event"] == "lane_ready":
            method = event["method"]
            metrics = frame["lanes"][method]["metrics"]
            assert frame["busy"] and frame["download_disabled"]
            target = nodes[method].get(event["result"].get("target"), {})
            state = {"error": "Failed", "root_cause": "Finding supported", "clarify": "Needs clarification",
                     "unsupported": "Out of scope", "next_action":
                     "Workshop review" if target.get("handoff") else "Recommendation ready"}[event["result"]["status"]]
            assert frame["lanes"][method]["state"] == state
            assert metrics["Elapsed"] == f'{event["elapsed_ms"] / 1000:.2f}s'
            assert metrics["Input tokens"] == f'{event["input_tokens"]:,}'
            assert metrics["Output tokens"] == f'{event["output_tokens"]:,}'
            assert metrics["Model calls"] == str(event["inference_calls"])
            assert metrics["Graph queries"] == str(event["graph_queries"])
            if event["estimated_cost_usd"] is not None:
                assert metrics["Est. cost"] == f'${event["estimated_cost_usd"]:.6f}'
            frozen[method] = metrics
            overlap |= len(frame["ready"]) == 1 and not frame["completed"]
        for method, metrics in frozen.items():
            assert frame["lanes"][method]["metrics"] == metrics, f"{method} finished metrics changed while its peer ran."
    assert set(frozen) == set(METHODS), "Both lanes must publish finished metrics before the comparison is saved."
    assert overlap, "No lane displayed its metrics before its peer finished."
    return overlap


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--case-id", help="Optional real catalog case, including a challenge case.")
    parser.add_argument("--url", "--base-url", dest="url", default="http://127.0.0.1:8766")
    parser.add_argument("--screenshots", default="results/local/browser")
    args = parser.parse_args()
    args.url = args.url.rstrip("/")
    output = Path(args.screenshots)
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as engine:
        browser = engine.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100}, device_scale_factor=1)
        errors, procedure_requests = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: procedure_requests.append(request.url)
                if "/api/procedure" in request.url else None)
        page.goto(args.url)
        page.wait_for_function("() => !document.getElementById('run').disabled")
        assert page.locator("#connection").inner_text() == "Apache AGE connected"
        catalog = page.request.get(args.url + "/api/catalog").json()
        for case in catalog["cases"]:
            assert not ({"start_node", "procedure_id", "actions", "expected", "expected_description"} & case.keys())
            assert all(set(item) == {"check", "observation"} for item in case["evidence"])
        demos = [case for case in catalog["cases"] if case.get("demo", True)]
        assert demos
        assert page.locator("#case-select option").count() == len(demos)
        assert not page.locator("#scenario-details").evaluate("(node) => node.open")
        assert not page.locator("#entry-stage").evaluate("(node) => node.open")
        assert page.get_by_role("combobox", name="Example problem", exact=True).is_visible()
        assert "Customer release" not in page.locator("#question").input_value()
        page.locator("#scenario-details > summary").click()
        assert page.locator("#case-select").bounding_box()["y"] < page.locator("#question").bounding_box()["y"]
        assert "not real service information" in page.locator(".synthetic-notice").inner_text()
        assert "Brand X" in page.locator("#vehicle-context").inner_text()
        assert page.locator("#timeline").count() == 0
        assert page.locator("#entry-stage").count() == 1
        assert page.locator('.shared-intake-step[data-method="llm-cypher"]').count() == 0
        assert_empty(page)
        page.locator("#show-adversarial").check()
        assert page.locator("#case-select option").count() == len(catalog["cases"])
        for case in catalog["cases"]:
            page.locator("#case-select").select_option(case["id"])
            assert_empty(page)
        selected_case = next((case for case in catalog["cases"] if case["id"] == args.case_id), demos[0])
        page.locator("#case-select").select_option(selected_case["id"])
        assert not procedure_requests
        initial_view = page.locator("#decision-graph svg").get_attribute("viewBox")
        page.locator("#decision-graph svg").focus()
        page.keyboard.press("+")
        assert page.locator("#decision-graph svg").get_attribute("viewBox") != initial_view
        page.get_by_role("button", name="Reset Decision-1 graph zoom").click()
        assert page.locator("#decision-graph svg").get_attribute("viewBox") == initial_view
        page.screenshot(path=str(output / "desktop-ready.png"), full_page=True)
        # Consume a clone of the same fetch response; CDP may evict streamed bodies.
        # Exercise the exact installation call in readiness checks as well as live runs.
        page.evaluate(CAPTURE_RUN_RESPONSE)
        assert page.evaluate("() => window.runCaptureInstalled && window.runResponseCaptureCount === 0")
        if args.live:
            # Observe real receive calls and DOM clocks; do not mock model or graph responses.
            page.evaluate("""() => {
                window.streamSnapshots = []; window.timingSamples = [];
                const original = window.receive;
                window.receive = event => {
                    original(event);
                    const graphs = {};
                    for (const method of ['decision', 'llm-cypher']) {
                        const host = document.getElementById(`${method}-graph`);
                        graphs[method] = {
                            nodes: [...host.querySelectorAll('[data-node-id]')].map(n => n.dataset.nodeId),
                            edges: [...host.querySelectorAll('[data-edge-id]')].map(n => n.dataset.edgeId),
                        };
                    }
                    const lanes = Object.fromEntries(['decision', 'llm-cypher'].map(method => [method, {
                        state: document.getElementById(`${method}-state`).textContent,
                        metrics: Object.fromEntries([...document.querySelectorAll(`#${method}-metrics > .metric`)]
                            .map(item => [item.querySelector('span').textContent, item.querySelector('strong').textContent])),
                    }]));
                    window.streamSnapshots.push({event, graphs, lanes, busy,
                        ready: Object.keys(readyResults), completed: Object.keys(completed),
                        download_disabled: document.getElementById('download').disabled});
                    window.sampleTiming();
                };
                window.sampleTiming = () => {
                    const rows = [];
                    for (const method of ['entry', 'decision', 'llm-cypher']) {
                        [...document.querySelectorAll(`#${method}-steps button`)].forEach((row, index) => {
                            const times = row.querySelector('.step-times');
                            rows.push({key: `${method}:${index}`, state: times.dataset.state,
                                duration: times.querySelector('.step-duration').dataset.ms,
                                total: times.querySelector('.step-total').dataset.ms});
                        });
                    }
                    timingSamples.push({rows, busy, other_pending: Object.keys(readyResults).length === 1});
                };
                window.sampleTimer = setInterval(window.sampleTiming, 60);
            }""")
            page.locator("#run").click()
            page.wait_for_function("""() => document.querySelector(
                '#llm-cypher-steps button[data-event="model_request"]') || !document.getElementById('run').disabled""",
                                   timeout=300000)
            first_request = page.locator('#llm-cypher-steps button[data-event="model_request"]').first
            assert first_request.count(), page.locator("#status").inner_text()
            first_request.click()
            assert "Exact API request body" in page.locator("#llm-cypher-inspector").inner_text()
            assert page.locator('.follow[data-method="llm-cypher"]').get_attribute("aria-pressed") == "false"
            assert page.locator('.follow[data-method="decision"]').get_attribute("aria-pressed") == "true"
            page.wait_for_function("() => !document.getElementById('run').disabled", timeout=300000)
            page.wait_for_timeout(180)
            page.evaluate("() => clearInterval(window.sampleTimer)")
            details = page.evaluate("""() => ({results: completed, events, hybrid_entry: entrySummary,
                snapshots: streamSnapshots, timing_samples: timingSamples})""")
            captured = page.evaluate("""async () => {
                if (!window.runResponseCapture) throw new Error("Actual run response was not captured.");
                return {...await window.runResponseCapture, count: window.runResponseCaptureCount};
            }""")
            assert "error" not in captured, captured
            assert captured["status"] == 200 and captured["count"] == 1, captured
            (output / "raw-stream.ndjson").write_bytes(captured["body"].encode("utf-8"))
            raw_events = [json.loads(line) for line in captured["body"].splitlines() if line.strip()]
            (output / "live-results.json").write_text(json.dumps(details, indent=2), encoding="utf-8")
            (output / "raw-stream.json").write_text(json.dumps(raw_events, indent=2), encoding="utf-8")
            page.screenshot(path=str(output / "desktop-pinned.png"), full_page=True)
            assert details["events"] == raw_events, "UI run log differs from actual NDJSON stream."
            assert [frame["event"] for frame in details["snapshots"]] == raw_events
            assert set(details["results"]) == set(METHODS), page.locator("#status").inner_text()
            entry = details["hybrid_entry"]
            assert entry is not None
            nodes, edges = assert_provenance(details["snapshots"])
            independent_metrics = assert_independent_lane_metrics(details["snapshots"])
            assert_timings(page, raw_events)
            observed_overlap = assert_live_samples(details["timing_samples"])
            assert observed_overlap, "No frozen completed timing was verified while the other lane ran."
            assert first_request.get_attribute("aria-current") == "step"
            assert "Exact API request body" in page.locator("#llm-cypher-inspector").inner_text()
            entry_calls = [event for event in raw_events if event.get("method") == "entry"
                           and event["event"] == "model_request"]
            assert len(entry_calls) == entry["metrics"]["inference_calls"]
            if entry_calls:
                assert all(event["deployment"] == catalog["decision_deployment"] for event in entry_calls)
                sol_request = next(event["request"] for event in raw_events
                                   if event.get("method") == "llm-cypher" and event["event"] == "model_request")
                sol_input = json.loads(sol_request["messages"][1]["content"])
                assert entry_calls[0]["request"]["state"] == sol_input
                page.locator("#entry-stage > summary").click()
                page.locator("#entry-details > summary").click()
                unchanged_inspector = page.locator("#decision-inspector").inner_text()
                page.locator('#entry-steps button[data-event="model_request"]').first.click()
                assert selected_case["question"] in page.locator("#entry-inspector").inner_text()
                assert "Exact API request body" in page.locator("#entry-inspector").inner_text()
                assert page.locator("#decision-inspector").inner_text() == unchanged_inspector
                page.locator("#entry-details > summary").click()
                page.locator("#entry-stage > summary").click()
            for method in METHODS:
                result = details["results"][method]
                own = [event for event in raw_events if event.get("method") == method]
                calls = sum(event["event"] == "model_request" for event in own)
                if method == "decision":
                    calls += len(entry_calls)
                    assert result["entry_metrics"] == entry["metrics"]
                else:
                    assert not result.get("entry_metrics"), "Sol-only was charged hybrid intake."
                    first_input = next(event for event in own if event["event"] == "model_request")
                    assert json.loads(first_input["request"]["messages"][1]["content"])["question"] == selected_case["question"]
                assert result["inference_calls"] == calls
                assert sum(result["model_calls_by_deployment"].values()) == calls
                assert "Call breakdown" in page.locator(f"#{method}-metrics").inner_text()
                page.locator(f"#{method}-metrics .call-breakdown > summary").click()
                if result.get("expected") and result.get("score"):
                    exact = all(result["result"].get(key) == result["expected"].get(key)
                                for key in ("status", "target", "path"))
                    assert result["score"]["exact"] == exact, "Score disagrees with actual output."
                    assert ("Exact" if exact else "Mismatch") in page.locator(f"#{method}-metrics").inner_text()
                if result["result"].get("target") and result["result"]["status"] not in ("error", "unsupported", "clarify"):
                    assert result["result"]["target"] in nodes[method]
                assert set(result["result"].get("path", [])) <= set(edges[method])
                page.locator(f'.all-events[data-method="{method}"]').click()
                assert page.locator(f"#{method}-steps button:visible").count() == len(own)
            prefix = page.locator('.shared-intake-step[data-method="decision"]')
            if entry_calls:
                prefix.click()
                assert selected_case["question"] in page.locator("#decision-inspector").inner_text()
            page.locator('.follow[data-method="llm-cypher"]').click()
            assert page.locator("#llm-cypher-steps button").last.get_attribute("aria-current") == "step"
            if page.locator('.follow[data-method="decision"]').get_attribute("aria-pressed") == "false":
                page.locator('.follow[data-method="decision"]').click()
            for method in METHODS:
                assert_readable_scope(page, method, details["results"][method], nodes[method])
                assert_context_toggle(page, method, nodes[method], edges[method])
                assert_readable_scope(page, method, details["results"][method], nodes[method])
            page.screenshot(path=str(output / "desktop-live.png"), full_page=True)
            with page.expect_download() as download:
                page.locator("#download").click()
            downloaded_path = output / "downloaded-run.json"
            download.value.save_as(downloaded_path)
            downloaded = json.loads(downloaded_path.read_text(encoding="utf-8"))
            assert downloaded["events"] == raw_events
            assert downloaded["results"] == details["results"]
            assert downloaded["md1_entry"] == entry
            assert downloaded["workflow"] == "md1-entry-v1"
            assert downloaded["input"]["vehicle"] == selected_case["vehicle"]
            assert downloaded["case_id"] == selected_case["id"]
            summary = {
                method: {
                    "result": {key: result["result"].get(key) for key in ("status", "target", "path")},
                    **{key: result.get(key) for key in (
                        "elapsed_ms", "inference_calls", "graph_queries", "input_tokens",
                        "output_tokens", "estimated_cost_usd", "model_calls_by_deployment", "score")},
                }
                for method, result in details["results"].items()
            }
            print(json.dumps({"workflows": summary,
                              "lane_metrics_visible_before_peer_ready": independent_metrics,
                              "completed_timing_frozen_during_overlap": observed_overlap}, indent=2))
        page.set_viewport_size({"width": 390, "height": 844})
        page.emulate_media(reduced_motion="reduce")
        page.wait_for_timeout(250)
        assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth"), "Mobile overflow."
        assert page.locator("#vehicle-context").is_visible(), "Vehicle context hidden on mobile."
        if args.live:
            for method in METHODS:
                assert_readable_scope(page, method, details["results"][method], nodes[method])
        page.screenshot(path=str(output / "mobile.png"), full_page=True)
        if args.live:
            for method in METHODS:
                svg = page.locator(f"#{method}-graph svg")
                assert_fit(page, method)
                expected_visible = page.evaluate("""m => {
                    const view = views[m], data = graphData(m);
                    return (view.answerRoute && !view.showContext
                        ? routeData(data, view.answerRoute.path, view.answerRoute.target)
                        : procedureData(data, view.layoutScope, view.showContext)).nodes.length;
                }""", method)
                assert page.locator(f"#{method}-graph .graph-node").count() == expected_visible
                svg.focus()
                page.keyboard.press("+")
                manual = svg.get_attribute("viewBox")
                assert svg.get_attribute("data-viewport-mode") == "manual"
                page.evaluate("() => window.dispatchEvent(new Event('resize'))")
                page.wait_for_timeout(150)
                assert svg.get_attribute("viewBox") == manual, "Manual viewport changed during rerender."
        response = page.request.post(args.url + "/api/run", headers={"Origin": "https://untrusted.example"},
                                     data={"case_id": selected_case["id"]})
        assert response.status == 403
        page.locator("#case-select").evaluate("(element) => element.dispatchEvent(new Event('change'))")
        assert_empty(page)
        for method in TRACES:
            assert page.locator(f'.follow[data-method="{method}"]').get_attribute("aria-pressed") == "true"
        page.locator("#question").fill("Edited diagnostic question")
        assert "unscored" in page.locator("#case-note").inner_text()
        assert not procedure_requests
        assert not errors, errors
        browser.close()
    print("Browser checks passed: natural scenarios, provenance, standalone lanes, timings, reset and mobile."
          if args.live else "Browser readiness checks passed: natural scenarios, empty graphs, reset and mobile.")


if __name__ == "__main__":
    main()
