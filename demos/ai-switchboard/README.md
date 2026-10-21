# The AI Switchboard

**Start here: the simplest demo in the Decision models collection.**

**[Open the live demo](https://ai-switchboard.example.invalid)**.
No installation or sign-in is needed. Choose an example and select
**Run comparison** to make four billable model requests; use fictional inputs only.

![An animated illustration of one ticket classified by Microsoft Decision One, GPT-6 Astra, GPT-6 Sol and GPT-6 Luna in parallel](docs/switchboard.svg)

What happens when a decision model and three language models tackle the same
classification task? Pick a case, run all four, and compare for yourself.

Eight editable, fictional examples cover **ticket routing**, **complaint
classification**, and **agent selection**. Each model's card shows its answer,
deployment, request latency, and API-reported input/output tokens. Expand
**Context / schema / output** to inspect the actual context, schema, and output - not internal
reasoning.

No scores, rankings, winners, or cost estimates. The UI shows the question and
possible labels, not an expected-answer key. The animation above is illustrative;
its timing is not a benchmark or a claim that any model is faster.

Cards are ordered **Decision One / Astra / Sol / Luna**. The GPT models follow
their positioning: frontier, general-purpose, then fast and cost-efficient.
This is not a parameter-size ranking.

## Try it

1. Choose an example and optionally edit its text.
2. Select **Run comparison** to make four parallel requests.
3. Compare the labels, latency, and tokens; open **Context / schema / output** to see what was sent and returned.

Submissions are not stored by this application. Text is sent to the configured
Foundry models for inference; use fictional or non-sensitive examples on this
public demo.

## What the numbers mean

| Metric | Meaning |
| --- | --- |
| Latency | Server-to-Foundry request time through receipt of the complete response; excludes the browser round trip and API cold start. |
| Input tokens | Usage reported by each model API, not a local estimate. GPT receives chat instructions and a strict JSON output schema; Decision One receives a native choice question, so counts need not match. |
| Output tokens | API-reported usage, including any reported GPT reasoning tokens. The GPT JSON wrapper also contributes tokens. Missing usage appears as a dash. |

Astra uses its lowest supported reasoning effort, `low`; Luna and Sol use `none`.
This is a hands-on comparison, not a controlled accuracy or performance benchmark:
the APIs, prompt representations, and output formats differ, and latency varies.

## How it works

```text
Browser: plain HTML, CSS and JavaScript
  |
  +-- Azure Static Web Apps managed Functions API (Node.js 22)
        |
        +-- Microsoft Decision One: native choice question
        +-- GPT-6 Astra: strict JSON output
        +-- GPT-6 Sol:   strict JSON output
        +-- GPT-6 Luna:  strict JSON output
```

No frontend framework, build step, database, or containers. Model credentials stay
server-side; the browser never receives the Foundry key. GitHub hosts the source;
Azure Static Web Apps hosts the page and API together.

## Deploy your own

Use an Azure Static Web App with a managed Node.js 22 Functions API and a Foundry
resource containing the four model deployments. Configure the GitHub repository
secret and encrypted Azure application settings below; never put their values in
source files or the browser.

| Setting | Value |
| --- | --- |
| `AI_SWITCHBOARD_DEPLOYMENT_TOKEN` | Central GitHub Actions repository secret for the Static Web App you intend to deploy |
| `FOUNDRY_ENDPOINT` | Azure application setting: your Foundry resource endpoint |
| `FOUNDRY_API_KEY` | Azure application setting: your Foundry API key |

Deployment names default to `Decision-1`, `gpt-6-astra`, `gpt-6-sol`, and
`gpt-6-luna`. Override them with the Azure application settings
`DECISION_DEPLOYMENT`, `ASTRA_DEPLOYMENT`, `SOL_DEPLOYMENT`, and `LUNA_DEPLOYMENT`
if needed. See the [API documentation](api/README.md) for request shapes and limits.

The [central GitHub Actions workflow](../../.github/workflows/ai-switchboard.yml)
runs the offline API checks on relevant changes. **It does not deploy on push.**
Deployment is an explicit manual action, using a dedicated
`AI_SWITCHBOARD_DEPLOYMENT_TOKEN` secret for your chosen Static Web App, not the
original repository's deployment token. Cloud deployment installs the Functions
runtime dependency in its isolated build environment.

Follow the **[deployment guide](docs/deployment.md)** for setup. The
[Bicep template](infra/main.bicep) creates only a Static Web App, not a Foundry
resource or model deployments. Its build paths point to this demo's subdirectory.
The original maintainer-specific provisioning script and parameter file are not
imported; no existing credentials, Azure settings or GitHub secrets are copied.

**Public inference is billable.** The deployed demo is anonymous, and visitors
consume the owner's Foundry quota. Its guard allows 16 concurrent requests and 96
starts per minute per API instance; restarts reset it, and scaled instances have
independent counters. This is not a global quota or spending cap. Each request has
a 40-second model timeout, and failures appear in the affected card.

## Source and deployment continuity

Imported from
[`Jbetts05/decision-model-demo` at `b153122`](https://github.com/Jbetts05/decision-model-demo/tree/b153122d5892428fcbdfd9b42e0658c14ae43615).
The original public repository and live deployment remain intact and independent.
The hosted link above still uses that deployment; importing the source here does
not move its hosting or change its release workflow.

The frontend, eight examples, four-model comparison and animated SVG are preserved.
This copy requires your own `FOUNDRY_ENDPOINT` rather than silently selecting the
maintainer's resource. Changes here do not automatically sync to the original.

## Tests

From `demos\ai-switchboard`, with Node.js 22:

```powershell
node --test
```

Tests use Node's built-in runner and do not require a dependency installation.
They do not make model calls. For the working UI use the hosted demo, or deploy
your own page and API together; opening `web/index.html` directly is not enough.
