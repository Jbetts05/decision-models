"""Measure Decision-1.1 per-request image, question and resolution behaviour (live, billable)."""

import argparse
import base64
from datetime import datetime, timezone
import json
import sys
import time
import urllib.error
import urllib.request

from probe import EXPECTED, QUESTIONS, SCENES, access_token, foundry_endpoint, image_png, probability


CONTENTS = {
    "red-circle-left": {("red", "circle", "left"), ("blue", "square", "right")},
    "red-square-right": {("blue", "circle", "left"), ("red", "square", "right")},
    "blank": set(),
}
DISTINCT_CHECKS = [
    (color, shape, side)
    for color in ("red", "blue", "green", "yellow", "black")
    for shape in ("circle", "square")
    for side in ("left", "right")
]
IMAGE_COUNTS = (1, 4, 8, 16, 32, 64)
QUESTION_COUNTS = (20, 100, 200, 255, 256)
RESOLUTIONS = ((640, 360), (1280, 720), (1568, 882), (1569, 883))


def asset(image):
    return {"type": "image", "format": "png", "data_base64": base64.b64encode(image).decode("ascii")}


def matches(answer, question, expected):
    """Return whether a well-formed answer matches; malformed answers raise ValueError."""
    if not isinstance(answer, dict) or answer.get("type") != question["type"]:
        raise ValueError("Missing or mistyped answer.")
    if question["type"] == "noul":
        return (probability(answer.get("noul")) >= 0.5) == expected
    options = question["criteria"]
    distribution = answer.get("probabilities")
    if (not isinstance(distribution, dict) or set(distribution) != set(options)
            or answer.get("choice") not in options):
        raise ValueError("Invalid choice distribution.")
    return answer["choice"] == expected


def post(endpoint, token, body):
    request = urllib.request.Request(
        f"{endpoint}/providers/microsoft/v1/systemone",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload, status, detail = json.load(response), response.status, None
    except urllib.error.HTTPError as exc:
        payload, status = None, exc.code
        detail = exc.read(600).decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("Decision API connection failed or timed out; no retries made.") from exc
    return status, payload, detail, round((time.perf_counter() - started) * 1000, 1)


def score(payload, questions, expected):
    answers = payload.get("answers") if isinstance(payload, dict) else None
    if not isinstance(answers, dict):
        raise ValueError("Response has no answers object.")
    return [name for name, question in questions.items()
            if not matches(answers.get(name), question, expected[name])]


def run(endpoint, token, label, body, questions, expected):
    status, payload, detail, elapsed_ms = post(endpoint, token, body)
    record = {"test": label, "status": status, "elapsed_ms": elapsed_ms, "questions": len(questions)}
    if status == 200:
        mismatches = score(payload, questions, expected)
        correct = len(questions) - len(mismatches)
        record.update(correct=correct, mismatches=mismatches, usage=payload.get("usage"))
        print(f"{label}: HTTP 200, {elapsed_ms:.0f} ms, {correct}/{len(questions)} correct, "
              f"usage={payload.get('usage')}", file=sys.stderr)
    else:
        record["error"] = detail
        print(f"{label}: HTTP {status}, {elapsed_ms:.0f} ms", file=sys.stderr)
    return record


def image_count_test(endpoint, token, deployment, count):
    assets, questions, expected = {}, {}, {}
    for index in range(count):
        scene, name = SCENES[index % len(SCENES)], f"img{index}.png"
        assets[name] = asset(image_png(scene))
        for key, question in QUESTIONS.items():
            question = json.loads(json.dumps(question).replace("image:frame.png", f"image:{name}"))
            questions[f"img{index}_{key}"] = question
            expected[f"img{index}_{key}"] = EXPECTED[scene][key]
    # Image references in state count toward every question's limit, so only questions reference images.
    state = "Several photos are supplied. Each question names the one photo it is about."
    body = {"model": deployment, "state": state, "assets": assets, "questions": questions}
    return run(endpoint, token, f"images={count}", body, questions, expected)


def question_count_test(endpoint, token, deployment, count, image):
    questions, expected = {}, {}
    for index in range(count):
        color, shape, side = DISTINCT_CHECKS[index % len(DISTINCT_CHECKS)]
        questions[f"q{index:03d}"] = {
            "type": "noul",
            "instructions": f"Is there a {color} {shape} in the {side} half of image:frame.png?",
        }
        expected[f"q{index:03d}"] = (color, shape, side) in CONTENTS["red-circle-left"]
    body = {
        "model": deployment,
        "state": "Assess only the supplied image: image:frame.png",
        "assets": {"frame.png": asset(image)},
        "questions": questions,
    }
    return run(endpoint, token, f"questions={count}", body, questions, expected)


def resolution_test(endpoint, token, deployment, width, height):
    body = {
        "model": deployment,
        "state": "Assess only the supplied image: image:frame.png",
        "assets": {"frame.png": asset(image_png("red-circle-left", width, height))},
        "questions": QUESTIONS,
    }
    return run(endpoint, token, f"resolution={width}x{height}", body, QUESTIONS, EXPECTED["red-circle-left"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True, type=foundry_endpoint)
    parser.add_argument("--deployment", required=True)
    args = parser.parse_args(argv)
    token = access_token()
    records = {"images": [], "questions": [], "resolution": []}
    for count in IMAGE_COUNTS:
        records["images"].append(image_count_test(args.endpoint, token, args.deployment, count))
        if records["images"][-1]["status"] != 200:
            break
    image = image_png("red-circle-left")
    for count in QUESTION_COUNTS:
        records["questions"].append(question_count_test(args.endpoint, token, args.deployment, count, image))
        if records["questions"][-1]["status"] != 200:
            break
    for width, height in RESOLUTIONS:
        records["resolution"].append(resolution_test(args.endpoint, token, args.deployment, width, height))
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "deployment": args.deployment,
        "notes": [
            "Synthetic shape images; checks request limits and answer binding, not real-photo accuracy.",
            "Image tests ask three questions per image and reference each image only in its own questions.",
            "Each count runs once; stops at the first non-200 response. No retries.",
        ],
        "records": records,
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"Limits probe failed: {exc}", file=sys.stderr)
        sys.exit(1)
