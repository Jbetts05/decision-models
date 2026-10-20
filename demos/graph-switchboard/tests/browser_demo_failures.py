"""Deterministic UI fault injection using historical events; no live inference or accuracy claim."""

import argparse
import copy
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def check(url, replay):
    original = json.loads((replay / "weak-washers-turn-0.json").read_text(encoding="utf-8"))
    with sync_playwright() as engine:
        browser = engine.chromium.launch(channel="msedge", headless=True)
        for mode in ("normal", "admission", "transport", "persistence", "model", "edited", "disagreement", "rejection"):
            page = browser.new_page()
            posts, releases, errors = [], [], []
            page.on("pageerror", lambda error: errors.append(str(error)))

            def run_request(route):
                posts.append(route.request.post_data_json)
                if mode == "transport":
                    route.abort("failed")
                    return
                if mode == "admission":
                    route.fulfill(status=429, json={"error": "Injected budget reservation refusal"})
                    return
                events = copy.deepcopy(original)
                if mode == "persistence":
                    events = [event for event in events if event["event"] != "complete"]
                if mode == "model":
                    for event in events:
                        if event["event"] in ("lane_ready", "complete") and event["method"] == "llm-cypher":
                            event["result"] = {"status": "error", "target": None, "path": [],
                                               "error": "Injected model path validation failure"}
                            event["score"] = {"exact": False}
                if mode in ("edited", "rejection"):
                    for event in events:
                        if event["event"] in ("lane_ready", "complete") and event["method"] != "entry":
                            event["score"] = None
                            event["expected"] = None
                if mode == "rejection":
                    position = next(i for i, event in enumerate(events)
                                    if event["event"] == "lane_ready" and event["method"] == "llm-cypher")
                    events.insert(position, {
                        "event": "answer_rejected", "method": "llm-cypher", "elapsed_ms": 1,
                        "error": "Injected structural validation failure",
                        "answer": {"kind": "answer", "status": "next_action",
                                   "target": "injected-node", "path": ["injected-edge"]},
                    })
                if mode == "disagreement":
                    for event in events:
                        if event["event"] in ("lane_ready", "complete") and event["method"] == "llm-cypher":
                            event["result"] = {"status": "clarify", "target": None, "path": [],
                                               "reason": "Injected lane disagreement: ask for clarification."}
                            event["score"] = {"exact": False}
                route.fulfill(status=200, content_type="application/x-ndjson",
                              body="".join(json.dumps(event) + "\n" for event in events))

            def release_request(route):
                releases.append(route.request.url)
                route.fulfill(status=503, json={"error": "Injected workshop record release failure"})

            page.route("**/api/run", run_request)
            page.route("**/api/release/*", release_request)
            page.goto(url)
            page.wait_for_function("() => !document.getElementById('run').disabled")
            if mode in ("edited", "disagreement", "rejection"):
                page.locator("#question").fill("The washer delivery is weak. What does the available guidance support?")
            page.locator("#run").click()
            page.wait_for_function("() => !busy && !document.getElementById('run').disabled")
            assert len(posts) == 1, "A failed or custom request was automatically retried."
            assert not releases
            assert "previous_run_id" not in posts[0]
            assert page.locator("#question").is_enabled()
            assert page.locator("#pause-example, #next-records, #manual-mode").count() == 0
            if mode in ("admission", "transport", "persistence", "model"):
                assert page.locator("#answer-summary").get_attribute("data-state") == "error"
                if mode == "persistence":
                    assert "Stream ended" in page.locator("#answer-body").inner_text()
                    assert "additional usage is unavailable" in page.locator("#answer-body").inner_text()
                    assert page.locator("#download").is_disabled()
                elif mode == "transport":
                    assert "Admission and usage could not be confirmed" in page.locator("#answer-body").inner_text()
                    assert "No inference was started" not in page.locator("#answer-body").inner_text()
                    assert page.locator("#download").is_disabled()
                else:
                    assert "Injected" in page.locator("#answer-body").inner_text()
                    if mode == "model":
                        assert "Sol-only" in page.locator("#answer-body").inner_text()
                        assert page.locator("#download").is_enabled()
            elif mode in ("edited", "rejection"):
                assert "Unscored" in page.locator("#decision-metrics").inner_text()
                assert "Recommended next step" in page.locator("#answer-title").inner_text()
                if mode == "rejection":
                    assert "1 rejected Sol answer" in page.locator("#answer-body").inner_text()
                    rejected = page.locator('#llm-cypher-steps button[data-event="answer_rejected"]')
                    assert rejected.is_visible()
                    rejected.click()
                    assert "Injected structural validation failure" in page.locator("#llm-cypher-inspector").inner_text()
                    assert page.locator('[data-edge-id="injected-edge"]').count() == 0
            elif mode == "disagreement":
                assert page.locator("#answer-title").inner_text() == "The models reached different recommendations"
                assert page.locator("#answer-body .answer-lane").count() == 2
            else:
                assert page.locator("#answer-title").inner_text() == "Recommended next step"
                assert page.locator("#download").is_enabled()
            assert not errors, errors
            page.close()
        browser.close()
    print("UI fault injection passed: errors, edited input, disagreement, visible rejected answer, no run retries.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8767")
    parser.add_argument("--replay", type=Path, required=True)
    args = parser.parse_args()
    check(args.url.rstrip("/"), args.replay)
