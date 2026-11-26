# Live vision capability probe

This is a small **live API probe**, not the webcam application. The
[design proposal](../../docs/proposals/live-vision.md) defines the intended demo.
No application hosting or UI is implemented here.

The probe generates three unlabeled 640 x 360 PNG cards in memory: a red circle
on the left with a blue square on the right, the same shapes with colors swapped,
and a blank white image. Each request asks the same three bounded questions about
the red object's presence, position, and shape. The scene names and expected
answers are never sent to the model.

These are synthetic **inputs to real inference**, not simulated results. They
check basic image grounding and the API response shape; they do not establish
real-world object recognition, localization accuracy, calibration, or webcam speed.

## Run

Prerequisites: Python 3.10+, Azure CLI signed in to the intended tenant, and
permission to invoke an existing Microsoft-Decision-1.1 Foundry deployment.
The script uses only the Python standard library; no package install is needed.
Model deployment is a separate operation and is never performed by this script.

From the repository root in PowerShell:

```powershell
az login
.\.venv\Scripts\python.exe demos\live-vision\probe.py `
  --endpoint https://YOUR-RESOURCE.cognitiveservices.azure.com `
  --deployment YOUR-DECISION-1.1-DEPLOYMENT
```

Use your own Python executable if you do not have a root `.venv`.
The default is nine **billable requests** (three images, three repetitions each),
with three questions per request. `--repeats 1` reduces this to three requests;
the maximum is five repetitions. Requests are sequential, with no automatic
retry. An HTTP or schema failure stops the probe. Any mismatched expected answer
produces a nonzero exit status, even if the API call succeeded.

JSON results go to stdout; progress goes to stderr. Output includes returned
decisions, usage, and observed request times, but no credentials or image payloads.
To preserve local results, redirect stdout to an ignored `*.local.json` file.

The API contract is documented in
[Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/use-foundry-models-microsoft-decision).
Images use `assets` with `type: image`, `format: png`, and `data_base64`; questions
reference `image:frame.png`. The documented answer types are `noul`, `choice`,
and `score`, not bounding boxes.

## Initial live result (2026-11-25)

Microsoft-Decision-1.1 version 1, Global Standard, deployed through a Sweden
Central resource: all 27 checks matched across nine real requests (three unique
images repeated three times). Median observed request latency was **463.1 ms**,
with a **415.7-822.9 ms** range; first request was 822.9 ms. The sequential run
completed **1.845 requests/s**, including local preparation overhead. Every
response reported 402 input tokens and 3 output tokens. No bounding boxes were
returned. This does not demonstrate the reference demo's four requests/s.

See the [proposal's evidence and remaining capability gate](../../docs/proposals/live-vision.md#verified-model-integration-and-initial-probe)
before interpreting this as readiness for real-world webcam object detection.

To check probe response validation without making paid requests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s demos\live-vision -p test_probe.py
```

## Request limits probe

`limits_probe.py` measures how many images and questions one request accepts,
and whether image resolution changes token usage. It runs from this directory
because it imports `probe.py`, and makes up to 15 **billable requests**, stopping
each series at the first rejection:

```powershell
Set-Location demos\live-vision
..\..\.venv\Scripts\python.exe limits_probe.py `
  --endpoint https://YOUR-RESOURCE.cognitiveservices.azure.com `
  --deployment YOUR-DECISION-1.1-DEPLOYMENT
```

Results on 2026-11-25, from the API's own error messages:

| Limit | Value |
|---|---|
| Image assets per request | 32 |
| Image references per question prompt, including the state and repeats | 8 |
| Questions per request | 255 |
| Image side length | 280 px minimum, 1568 px maximum |
| Input tokens per image | About 400 at 640x360, 1280x720 and 1568x882 |

32 images with three questions each completed in one request in 1.7 s with all
96 synthetic checks correct. Referencing every image in the `state` instead
counts toward each question's 8-reference limit, so reference each image only
from its own questions. These synthetic images test limits and answer binding,
not real-photo accuracy.

`multi_image_probe.py` (same arguments, three billable requests) puts two
questions in one request, each offering eight different images as its `choice`
options and asking for the single odd one out. On 2026-11-25 all six answers
were correct across three trials with the odd image in different positions
(16 images, 4,400 input tokens per request, 0.9-1.2 s).

`batching_probe.py` (same arguments) sends the same 32 photos, three questions
each, two ways: Microsoft's documented maximum of 8 images per call (four calls
in parallel) and the observed 32-image single call. It then sends two requests
past the observed limits. Results on 2026-11-25, three rounds:

| Strategy | Requests | Median wall time | Input tokens | Correct |
|---|---|---|---|---|
| Documented: 4 x 8 images, parallel | 4 | 757 ms | 12,940 | 96/96 every round |
| Observed: 1 x 32 images | 1 | 1,475 ms | 12,883 | 96/96 every round |

Both strategies agreed on all 96 decisions in every round. Cost is effectively
identical, and the parallel documented batches were faster, so the 32-image call
saves requests but not time or money. 33 images were rejected (HTTP 413, "at
most 32 image assets"); a question prompt with eight images in the state plus
one in the question was rejected (HTTP 400; the API reported 10 references).
The 32-image behaviour is undocumented and may change.
