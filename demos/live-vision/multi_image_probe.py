"""Live, billable: two questions in one request, each referencing eight different images."""

import argparse
import json
import random
import sys

from limits_probe import asset, post
from probe import access_token, foundry_endpoint, image_png, probability

GROUPS = (
    {"base": "red-circle-left", "odd": "red-square-right",
     "instructions": "Which one of these photos shows a red square?"},
    {"base": "red-square-right", "odd": "blank",
     "instructions": "Which one of these photos contains no coloured shapes at all?"},
)


def build(deployment, odd_positions):
    images = {scene: asset(image_png(scene)) for scene in ("red-circle-left", "red-square-right", "blank")}
    assets, questions, expected = {}, {}, {}
    for group_index, (group, odd) in enumerate(zip(GROUPS, odd_positions)):
        criteria = {}
        for slot in range(8):
            name = f"g{group_index}_photo{slot}.png"
            assets[name] = images[group["odd"] if slot == odd else group["base"]]
            criteria[f"photo_{slot}"] = f"image:{name}"
        key = f"question_{group_index + 1}"
        questions[key] = {"type": "choice", "instructions": group["instructions"], "criteria": criteria}
        expected[key] = f"photo_{odd}"
    body = {
        "model": deployment,
        "state": "Each question offers eight photos as its answer options.",
        "assets": assets,
        "questions": questions,
    }
    return body, expected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True, type=foundry_endpoint)
    parser.add_argument("--deployment", required=True)
    parser.add_argument("--trials", type=int, default=3, choices=range(1, 6))
    args = parser.parse_args(argv)
    token = access_token()
    rng = random.Random(20261125)
    results = []
    for trial in range(args.trials):
        odd_positions = [rng.randrange(8) for _ in GROUPS]
        body, expected = build(args.deployment, odd_positions)
        status, payload, detail, elapsed_ms = post(args.endpoint, token, body)
        record = {"trial": trial + 1, "status": status, "elapsed_ms": elapsed_ms,
                  "images": len(body["assets"]), "expected": expected}
        if status == 200:
            answers = payload["answers"]
            record["answers"] = {
                key: {"choice": answers[key]["choice"],
                      "probability": round(probability(answers[key]["probabilities"][answers[key]["choice"]]), 4)}
                for key in expected
            }
            record["usage"] = payload.get("usage")
            correct = sum(answers[key]["choice"] == value for key, value in expected.items())
            print(f"trial {trial + 1}: HTTP 200, {elapsed_ms:.0f} ms, {correct}/2 correct, "
                  f"expected={expected}, got={record['answers']}", file=sys.stderr)
        else:
            record["error"] = detail
            print(f"trial {trial + 1}: HTTP {status}: {detail}", file=sys.stderr)
        results.append(record)
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ValueError, OSError, KeyError) as exc:
        print(f"Multi-image probe failed: {exc}", file=sys.stderr)
        sys.exit(1)
