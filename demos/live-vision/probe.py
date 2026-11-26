"""Small live Decision-1.1 vision probe; no webcam, secrets, or image files."""

import argparse
import base64
from datetime import datetime, timezone
import json
import math
import shutil
import statistics
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib


WIDTH, HEIGHT = 640, 360
QUESTIONS = {
    "red_present": {
        "type": "noul",
        "instructions": "Is there a red colored shape visible in image:frame.png?",
    },
    "red_position": {
        "type": "choice",
        "instructions": "Where is the red colored shape in image:frame.png?",
        "criteria": {
            "left": "In the left half of the image",
            "right": "In the right half of the image",
            "absent": "No red colored shape is visible",
        },
    },
    "red_shape": {
        "type": "choice",
        "instructions": "What shape is the red colored object in image:frame.png?",
        "criteria": {
            "circle": "A filled circle",
            "square": "A filled square",
            "absent": "No red colored shape is visible",
        },
    },
}
SCENES = ("red-circle-left", "red-square-right", "blank")
EXPECTED = {
    "red-circle-left": {"red_present": True, "red_position": "left", "red_shape": "circle"},
    "red-square-right": {"red_present": True, "red_position": "right", "red_shape": "square"},
    "blank": {"red_present": False, "red_position": "absent", "red_shape": "absent"},
}


def image_png(scene, width=WIDTH, height=HEIGHT):
    """Create unlabeled counterfactual images; answers must come from pixels."""
    if scene not in SCENES:
        raise ValueError(f"Unknown scene: {scene}")
    cx, cy, radius = width // 4, height // 2, height * 7 // 36
    left, right = width * 41 // 64, width * 55 // 64
    top, bottom = height * 11 // 36, height * 25 // 36
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            circle = (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2
            square = left <= x < right and top <= y < bottom
            color = (255, 255, 255)
            if scene != "blank":
                if circle:
                    color = (230, 30, 30) if scene == SCENES[0] else (30, 60, 230)
                elif square:
                    color = (30, 60, 230) if scene == SCENES[0] else (230, 30, 30)
            rows.extend(color)

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(bytes(rows))) + chunk(b"IEND", b""))


def request_body(deployment, image):
    return {
        "model": deployment,
        "state": "Assess only the supplied image: image:frame.png",
        "assets": {
            "frame.png": {
                "type": "image",
                "format": "png",
                "data_base64": base64.b64encode(image).decode("ascii"),
            },
        },
        "questions": QUESTIONS,
    }


def probability(value):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not 0 <= value <= 1):
        raise ValueError("Invalid probability in model response.")
    return value


def inspect_answers(payload, scene):
    if not isinstance(payload, dict) or not isinstance(payload.get("answers"), dict):
        raise ValueError("Response must contain a typed answers object.")
    answers = payload["answers"]
    checks = {}
    for name, question in QUESTIONS.items():
        answer = answers.get(name)
        if not isinstance(answer, dict) or answer.get("type") != question["type"]:
            raise ValueError(f"Missing or invalid answer: {name}")
        if question["type"] == "noul":
            selected = probability(answer.get("noul")) >= 0.5
        else:
            selected = answer.get("choice")
            options = question["criteria"]
            distribution = answer.get("probabilities")
            if (not isinstance(distribution, dict) or set(distribution) != set(options)
                    or not isinstance(selected, str) or selected not in options):
                raise ValueError(f"Invalid choice distribution: {name}")
            if abs(sum(probability(p) for p in distribution.values()) - 1) > 0.02:
                raise ValueError(f"Probabilities do not sum to one: {name}")
        checks[name] = selected == EXPECTED[scene][name]
    return checks


def foundry_endpoint(value):
    parsed = urllib.parse.urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname
            or not parsed.hostname.endswith((".cognitiveservices.azure.com", ".services.ai.azure.com"))
            or parsed.username or parsed.password or parsed.port
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise argparse.ArgumentTypeError("Use a Foundry HTTPS resource endpoint without a path.")
    return value.rstrip("/")


def access_token():
    az = shutil.which("az")
    if not az:
        raise RuntimeError("Azure CLI is required. Sign in with az login before running.")
    try:
        token = subprocess.run(
            [az, "account", "get-access-token", "--resource", "https://cognitiveservices.azure.com",
             "--query", "accessToken", "--output", "tsv"],
            check=True, capture_output=True, text=True, timeout=60,
        ).stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Azure CLI token acquisition failed; check az login and access.") from exc
    if not token:
        raise RuntimeError("Azure CLI returned an empty access token.")
    return token


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True, type=foundry_endpoint)
    parser.add_argument("--deployment", required=True)
    parser.add_argument("--repeats", type=int, default=3, choices=range(1, 6))
    args = parser.parse_args(argv)
    token = access_token()
    records = []
    started = time.perf_counter()
    for scene in SCENES:
        body = json.dumps(request_body(args.deployment, image_png(scene))).encode("utf-8")
        for repeat in range(args.repeats):
            request = urllib.request.Request(
                f"{args.endpoint}/providers/microsoft/v1/systemone",
                data=body,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
                method="POST",
            )
            call_started = time.perf_counter()
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    payload = json.load(response)
            except urllib.error.HTTPError as exc:
                raise RuntimeError(f"Decision API returned HTTP {exc.code}; no retries made.") from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                raise RuntimeError("Decision API connection failed or timed out; no retries made.") from exc
            elapsed_ms = (time.perf_counter() - call_started) * 1000
            checks = inspect_answers(payload, scene)
            records.append({
                "scene": scene, "repeat": repeat + 1,
                "elapsed_ms": round(elapsed_ms, 1),
                "response_keys": sorted(payload),
                "model": payload.get("model"),
                "answers": payload["answers"],
                "usage": payload.get("usage"),
                "checks": checks,
            })
            print(f"{scene} {repeat + 1}/{args.repeats}: {elapsed_ms:.0f} ms; "
                  f"{sum(checks.values())}/{len(checks)} checks matched", file=sys.stderr)
    wall_seconds = time.perf_counter() - started
    latencies = [record["elapsed_ms"] for record in records]
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "deployment": args.deployment,
        "image_size": [WIDTH, HEIGHT],
        "request_count": len(records),
        "questions_per_request": len(QUESTIONS),
        "all_checks_matched": all(all(record["checks"].values()) for record in records),
        "latency_ms": {
            "first": latencies[0], "min": min(latencies),
            "median": round(statistics.median(latencies), 1), "max": max(latencies),
        },
        "sequential_completed_requests_per_second": round(len(records) / wall_seconds, 3),
        "limitations": [
            "Synthetic shape cards, not photos or a real-world object-detection benchmark.",
            "Fixed questions return probabilities and choices, not native object bounding boxes.",
            "Latency includes network and response reading; not isolated model inference time.",
            "Fresh HTTP connections, sequential requests, one deployment, very small sample.",
            "The 0.5 binary threshold is a probe check, not a validated application threshold.",
        ],
        "records": records,
    }
    print(json.dumps(report, indent=2))
    return 0 if report["all_checks_matched"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"Probe failed: {exc}", file=sys.stderr)
        sys.exit(1)
