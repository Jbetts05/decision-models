"""Live, billable: the same 32 photos sent as documented (4 calls x 8 images) and as one 32-image call."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import random
import statistics
import sys
import time

from limits_probe import asset, matches, post
from probe import EXPECTED, QUESTIONS, SCENES, access_token, foundry_endpoint, image_png

PHOTOS = 32
DOCUMENTED_BATCH = 8
STATE = "Several photos are supplied. Each question names the one photo it is about."


def photo_scenes(seed):
    rng = random.Random(seed)
    return [rng.choice(SCENES) for _ in range(PHOTOS)]


def questions_for(index):
    name = f"photo{index:02d}.png"
    return {
        f"photo{index:02d}_{key}": json.loads(json.dumps(question).replace("image:frame.png", f"image:{name}"))
        for key, question in QUESTIONS.items()
    }


def body_for(deployment, indexes, images, scenes):
    questions = {}
    for index in indexes:
        questions.update(questions_for(index))
    assets = {f"photo{index:02d}.png": images[scenes[index]] for index in indexes}
    return {"model": deployment, "state": STATE, "assets": assets, "questions": questions}


def expected_for(scenes):
    return {
        f"photo{index:02d}_{key}": EXPECTED[scene][key]
        for index, scene in enumerate(scenes) for key in QUESTIONS
    }


def call(endpoint, token, body):
    status, payload, detail, elapsed_ms = post(endpoint, token, body)
    if status != 200:
        raise RuntimeError(f"HTTP {status}: {detail}")
    return payload, elapsed_ms


def evaluate(answers, questions, expected):
    return sum(matches(answers[name], question, expected[name]) for name, question in questions.items())


def documented(endpoint, token, deployment, images, scenes):
    batches = [range(start, start + DOCUMENTED_BATCH) for start in range(0, PHOTOS, DOCUMENTED_BATCH)]
    bodies = [body_for(deployment, batch, images, scenes) for batch in batches]
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(bodies)) as pool:
        results = list(pool.map(lambda body: call(endpoint, token, body), bodies))
    wall_ms = (time.perf_counter() - started) * 1000
    answers, tokens = {}, 0
    for payload, _ in results:
        answers.update(payload["answers"])
        tokens += payload["usage"]["input_tokens"]
    return {"requests": len(bodies), "wall_ms": round(wall_ms, 1),
            "per_request_ms": [elapsed for _, elapsed in results], "input_tokens": tokens}, answers


def single(endpoint, token, deployment, images, scenes):
    body = body_for(deployment, range(PHOTOS), images, scenes)
    payload, elapsed_ms = call(endpoint, token, body)
    return {"requests": 1, "wall_ms": elapsed_ms, "per_request_ms": [elapsed_ms],
            "input_tokens": payload["usage"]["input_tokens"]}, payload["answers"]


def boundaries(endpoint, token, deployment, images):
    over_assets = body_for(deployment, range(PHOTOS), images, [SCENES[i % 3] for i in range(PHOTOS)])
    over_assets["assets"]["photo32.png"] = images[SCENES[0]]
    over_assets["questions"].update(questions_for(32))
    nine_refs = {
        "model": deployment,
        "state": "Photos: " + ", ".join(f"image:photo{i:02d}.png" for i in range(8)),
        "assets": {f"photo{i:02d}.png": images[SCENES[i % 3]] for i in range(9)},
        "questions": {"q": {"type": "noul", "instructions": "Is there a red shape in image:photo08.png?"}},
    }
    results = {}
    for label, body in (("33 images in one request", over_assets),
                        ("one question referencing 9 images", nine_refs)):
        status, _, detail, _ = post(endpoint, token, body)
        results[label] = {"status": status, "error": detail}
        print(f"  {label}: HTTP {status} {detail}", file=sys.stderr)
    return results


def agreement(first, second, questions):
    def decision(answer, question):
        return answer["noul"] >= 0.5 if question["type"] == "noul" else answer["choice"]
    return sum(decision(first[name], q) == decision(second[name], q) for name, q in questions.items())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True, type=foundry_endpoint)
    parser.add_argument("--deployment", required=True)
    parser.add_argument("--rounds", type=int, default=3, choices=range(1, 6))
    args = parser.parse_args(argv)
    token = access_token()
    images = {scene: asset(image_png(scene)) for scene in SCENES}
    scenes = photo_scenes(20261125)
    expected = expected_for(scenes)
    all_questions = {}
    for index in range(PHOTOS):
        all_questions.update(questions_for(index))

    rounds = []
    for number in range(1, args.rounds + 1):
        doc_stats, doc_answers = documented(args.endpoint, token, args.deployment, images, scenes)
        one_stats, one_answers = single(args.endpoint, token, args.deployment, images, scenes)
        doc_stats["correct"] = evaluate(doc_answers, all_questions, expected)
        one_stats["correct"] = evaluate(one_answers, all_questions, expected)
        same = agreement(doc_answers, one_answers, all_questions)
        rounds.append({"round": number, "documented": doc_stats, "single_call": one_stats, "agreement": same})
        print(f"round {number}: documented 4x8 {doc_stats['wall_ms']:.0f} ms wall, "
              f"{doc_stats['correct']}/{len(all_questions)} correct | "
              f"single 1x32 {one_stats['wall_ms']:.0f} ms, {one_stats['correct']}/{len(all_questions)} correct | "
              f"agreement {same}/{len(all_questions)}", file=sys.stderr)

    print("boundaries:", file=sys.stderr)
    limits = boundaries(args.endpoint, token, args.deployment, images)

    def summary(mode):
        walls = [r[mode]["wall_ms"] for r in rounds]
        return {"median_wall_ms": round(statistics.median(walls), 1),
                "requests_per_run": rounds[0][mode]["requests"],
                "input_tokens_per_run": rounds[0][mode]["input_tokens"],
                "correct_per_run": [r[mode]["correct"] for r in rounds]}

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "deployment": args.deployment,
        "photos": PHOTOS,
        "questions": len(all_questions),
        "documented_4x8_parallel": summary("documented"),
        "undocumented_1x32": summary("single_call"),
        "boundaries": limits,
        "notes": [
            "Microsoft's model card documents up to 8 images per call; 32 per call is observed, not supported.",
            "Synthetic shape photos: compares request strategies, not real-photo accuracy.",
            "Documented batches run concurrently; wall time is the slowest of the four calls.",
        ],
        "rounds": rounds,
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ValueError, OSError, KeyError) as exc:
        print(f"Batching probe failed: {exc}", file=sys.stderr)
        sys.exit(1)
