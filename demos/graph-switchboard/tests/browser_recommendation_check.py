"""Single-submission acceptance. --live is paid; --replay is historical-event UI regression only."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from browser_check import (
    CAPTURE_RUN_RESPONSE, METHODS, assert_context_toggle, assert_empty, assert_fit,
    assert_independent_lane_metrics, assert_provenance, assert_readable_scope,
)


def check(url, output, cases, replay=None):
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as engine:
        browser = engine.chromium.launch(channel="msedge", headless=True)
        for identifier in cases:
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            errors, posts, releases = [], [], []
            page.on("pageerror", lambda error: errors.append(str(error)))

            def submit(route):
                posts.append(route.request.post_data_json)
                if replay is None:
                    route.continue_()
                    return
                fixture_id = identifier.removesuffix("-records") + "-turn-3" if identifier.endswith("-records") else identifier
                events = json.loads((replay / f"{fixture_id}.json").read_text(encoding="utf-8"))
                route.fulfill(status=200, content_type="application/x-ndjson",
                              body="".join(json.dumps(event) + "\n" for event in events))

            def release(route):
                releases.append(route.request.url)
                route.fulfill(status=410, json={"error": "Staged releases are not supported."})

            page.route("**/api/run", submit)
            page.route("**/api/release/*", release)
            page.goto(url)
            page.wait_for_function("() => !document.getElementById('run').disabled")
            catalog = page.request.get(url + "/api/catalog").json()
            case = next(item for item in catalog["cases"] if item["id"] == identifier)
            assert catalog["input_policy"] == "single-problem-v1"
            assert not any({"turn", "turn_count", "next_case", "journey_id"} & item.keys() for item in catalog["cases"])
            if not case["demo"]:
                page.locator("#scenario-details > summary").click()
                page.locator("#show-adversarial").check()
            page.locator("#case-select").select_option(identifier)
            assert_empty(page)
            assert page.locator("#question").input_value() == case["question"]
            assert page.evaluate("() => currentEvidence()") == case["evidence"]
            assert page.locator("#run-label").inner_text() == "Get recommendation"
            assert page.locator("#next-records, #pause-example, #manual-mode, #journey-controls").count() == 0
            page.evaluate(CAPTURE_RUN_RESPONSE)
            page.evaluate("""() => {
                window.recommendationFrames = [];
                const original = window.receive;
                window.receive = event => {
                    original(event);
                    const graphs = Object.fromEntries(['decision', 'llm-cypher'].map(m => [m, {
                        nodes: [...document.querySelectorAll(`#${m}-graph [data-node-id]`)].map(n => n.dataset.nodeId),
                        edges: [...document.querySelectorAll(`#${m}-graph [data-edge-id]`)].map(n => n.dataset.edgeId),
                    }]));
                    const lanes = Object.fromEntries(['decision', 'llm-cypher'].map(m => [m, {
                        state: document.getElementById(`${m}-state`).textContent,
                        metrics: Object.fromEntries([...document.querySelectorAll(`#${m}-metrics > .metric`)]
                            .map(n => [n.querySelector('span').textContent, n.querySelector('strong').textContent])),
                    }]));
                    recommendationFrames.push({event, graphs, lanes, busy, ready: Object.keys(readyResults),
                        completed: Object.keys(completed), download_disabled: document.getElementById('download').disabled});
                };
            }""")
            page.locator("#run").click()
            page.wait_for_function("() => !busy && !document.getElementById('run').disabled", timeout=300000)
            captured = page.evaluate("async () => ({...await window.runResponseCapture, count: window.runResponseCaptureCount})")
            actual = page.evaluate("() => ({input: lastInput, events, results: completed, status: document.getElementById('status').textContent})")
            (output / f"{identifier}-attempt.json").write_text(json.dumps(actual), encoding="utf-8")
            (output / f"{identifier}-stream.ndjson").write_text(captured.get("body", ""), encoding="utf-8")
            page.screenshot(path=str(output / f"{identifier}-attempt.png"), full_page=True)
            assert len(posts) == 1 and not releases and captured["count"] == 1
            assert "previous_run_id" not in posts[0]
            assert posts[0]["question"] == case["question"] and posts[0]["evidence"] == case["evidence"]
            assert actual["input"] == posts[0]
            assert captured["status"] == 200
            assert [json.loads(line) for line in captured["body"].splitlines() if line.strip()] == actual["events"]
            assert len(actual["results"]) == 2, actual["status"]
            frames = page.evaluate("() => recommendationFrames")
            returned_nodes, returned_edges = assert_provenance(frames)
            assert_independent_lane_metrics(frames)
            assert page.locator("#answer-summary").is_visible()
            for method in METHODS:
                result = actual["results"][method]
                assert result["result"]["status"] != "error", result["result"]
                if replay is None:
                    assert result["score"]["exact"], result["score"]
                    assert result["graph_queries"] > 0
                assert_readable_scope(page, method, result, returned_nodes[method])
                assert_fit(page, method)
                if page.locator(f'.graph-context[data-method="{method}"]').is_disabled():
                    follow = page.locator(f'.follow[data-method="{method}"]')
                    if follow.get_attribute("aria-pressed") == "true":
                        follow.click()
                    follow.click()
                assert_context_toggle(page, method, returned_nodes[method], returned_edges[method])
                assert page.locator(f"#{method}-outcome").get_attribute("data-status") == result["result"]["status"]
                details = page.locator(f"#{method}-outcome > details")
                details.locator("summary").first.click()
                assert "Records supplied upfront" in details.inner_text()
                if result["result"].get("target"):
                    assert "Source reference" in details.inner_text()
                details.locator("summary").first.click()
            with page.expect_download() as download:
                page.locator("#download").click()
            artifact = output / f"{identifier}-download.json"
            download.value.save_as(artifact)
            downloaded = json.loads(artifact.read_text(encoding="utf-8"))
            assert downloaded["input"] == actual["input"]
            assert downloaded["events"] == actual["events"] and downloaded["results"] == actual["results"]
            assert downloaded["input_policy"] == "single-problem-v1" and "journey_releases" not in downloaded
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(300)
            for method in METHODS:
                assert_readable_scope(page, method, actual["results"][method], returned_nodes[method])
            assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(output / f"{identifier}-mobile.png"), full_page=True)
            page.locator("#question").fill("A different customer problem with no completed tests.")
            assert page.locator("#answer-summary").is_hidden()
            assert_empty(page)
            assert len(posts) == 1 and not errors, errors
            print(json.dumps({"case": identifier, "mode": "historical UI replay" if replay else "actual live",
                              "results": {method: {"status": row["result"]["status"],
                                                  "hops": row["hops"], "calls": row["inference_calls"]}
                                          for method, row in actual["results"].items()}}))
            page.close()
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8767")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", nargs="+", default=["weak-washers-turn-0", "weak-washers-records"])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--replay", type=Path)
    args = parser.parse_args()
    check(args.url.rstrip("/"), args.output, args.cases, args.replay)
