# Development

Run commands from `demos\graph-switchboard`. The demo owns its Python environment,
Docker configuration, tests, data and deployment scripts; other demos should
not need these dependencies.

## Fast checks

After the setup in the [demo guide](../README.md):

```powershell
.\.venv\Scripts\python.exe -m traversal validate
.\.venv\Scripts\python.exe -m unittest discover -s tests
node --test tests\execution-timing.test.cjs
```

Node.js 20+ is needed only for the JavaScript tests. These commands do not invoke
Foundry. PostgreSQL integration checks are opt-in and skipped by default.
The repository's GitHub Actions workflow runs these offline checks for this demo.

## Real database integration

Start the local AGE database and load the graph first:

```powershell
.\.venv\Scripts\python.exe -m traversal db-up
.\.venv\Scripts\python.exe -m traversal load
$env:AGE_INTEGRATION = "1"
$env:CLOUD_BACKEND_INTEGRATION = "1"
.\.venv\Scripts\python.exe -m unittest discover -s tests
Remove-Item Env:AGE_INTEGRATION, Env:CLOUD_BACKEND_INTEGRATION
```

These checks use real PostgreSQL without model inference. Do not run database
migration/admission tests concurrently with an active comparison.

## Browser checks

Install development dependencies into this demo's virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

With the app running, use installed Microsoft Edge without downloading a browser:

```powershell
.\.venv\Scripts\python.exe tests\browser_check.py
```

To run actual paid comparisons, explicitly add `--live`:

```powershell
.\.venv\Scripts\python.exe tests\browser_recommendation_check.py --live `
  --output results\local\recommendation-check
```

Strict live assertions retain incorrect model outcomes as failures; do not
adjust inputs, the oracle or thresholds to manufacture agreement.

## Code map

| Directory | Responsibility |
| --- | --- |
| `traversal/` | Python CLI, AGE access, Foundry calls, independent traversal lanes and HTTP server. |
| `web/` | Browser UI, live graphs, execution timelines and recommendation evidence. |
| `data/traversal/` | Frozen graph, source guides, example inputs, manifest and scorer-only expected outputs. |
| `tests/` | Offline regressions and explicitly opt-in real database/model/browser checks. |
| `infra/` | Azure Bicep templates and PowerShell deployment entry point. |
| `docs/` | Current setup details and clearly labelled historical research. |

`python -m traversal --help` lists lower-level commands. `start` combines
`validate`, `db-up`, `load` and `serve`; it does not regenerate source data.
To serve an already prepared database without starting Docker, use `serve`.

## Dataset and research boundaries

Use `validate` to check the committed frozen corpus. `generate` is an authoring
tool, not a setup requirement: changing authored guidance requires a new dataset
version, preserved hashes and rerunning both architectures.
The root `.gitattributes` preserves the frozen inputs byte-for-byte, including
line endings, because the manifest records source and authoring-pack hashes.
Do not reformat those inputs as an unrelated cleanup.

The 143 research snapshots are correlated fictional inputs, not 143 independent
customer problems. Historical staged-release evaluators remain for research
reproducibility; they do not describe the public single-submission UI.
Historical exact-match results are not a held-out real-world accuracy estimate.

`results/`, `.azure/`, `.env`, `config.local.json` and `.venv/` are local-only.
Raw runs may contain prompts, inputs and model outputs. Preserve them locally
when needed, but do not publish them as repository content.

## Overview artwork

[`images/overview.svg`](images/overview.svg) is a self-contained animated SVG:
no scripts, external fonts, images or network requests. It has an accessible
title/description and honours reduced-motion preferences. Its resting state is
complete and readable when animation is disabled or unsupported.

The [Excalidraw source](images/overview.excalidraw) preserves the editable
architecture layout; SVG presentation and animation are authored separately.
The illustration is not a replay, speed comparison or model-performance claim.
