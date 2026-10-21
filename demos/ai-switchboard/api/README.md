# Model comparison API

Node.js 22, Azure Functions v4 HTTP handlers for a managed Azure Static Web App.
No local package installation is needed for the pure-core tests:

```powershell
Set-Location api
node --test
```

## Endpoints

- `GET /api/catalog` is public and returns four model descriptors and eight fictional
  scenarios. Scenarios in each group share instructions and category definitions.
- `POST /api/run` is public, with no sign-in, cookies, or access codes required,
  and accepts only `{modelId, scenarioId, text}`. Text must be a nonblank
  string of 1–6000 characters. Requests require `application/json` and cannot exceed
  32 KiB, including when streamed without a content-length header.
- A successful run returns `{modelId, model, deployment, answer, latencyMs,
  inputTokens, outputTokens, details}`. Unknown usage counters are `null`, never
  estimates. Decision and GPT summary answers contain only the selected category.
  There are no costs or rankings.
- `details: {context, schema, output}` contains the actual successful request and
  provider result for an optional, initially closed inspector. Decision context is
  `{state}` and schema is `{questions}` with the typed classification criteria.
  GPT context is `{messages, reasoning_effort, max_completion_tokens}` and
  schema is the actual `response_format` object with the strict JSON schema.
  Output is `{model, answers, usage}` for Decision or `{model, choices, usage}` for
  GPT, copied from the provider; absent provider fields are omitted in JSON rather
  than invented. Decision confidence/probabilities belong only inside
  this inspector, not the summary. No internal reasoning or explanations are invented.
  Details never include credentials or request headers, and are absent on errors.
  Clients should render JSON using `pre.textContent = JSON.stringify(value, null, 2)`,
  not HTML, and clear details on a new run or input change.
- Errors return `{error}` with 400/413/415 for invalid input, 405 for unsupported
  methods, 429 for throttling, 502/503 for model-service failures, and 504 for timeouts.
  Upstream 401/403 errors return 503, not a login/session-expiry response.

## Server settings

| Setting | Purpose |
| --- | --- |
| `FOUNDRY_API_KEY` | Required existing Foundry credential; store only in encrypted Azure application settings. |
| `FOUNDRY_ENDPOINT` | Required HTTPS Foundry resource origin, for example `https://YOUR-RESOURCE.services.ai.azure.com`. No maintainer endpoint is assumed. |
| `DECISION_DEPLOYMENT` | Optional deployment override; defaults to `Decision-1`. |
| `ASTRA_DEPLOYMENT` | Optional deployment override; defaults to `gpt-6-astra`. |
| `LUNA_DEPLOYMENT` | Optional deployment override; defaults to `gpt-6-luna`. |
| `SOL_DEPLOYMENT` | Optional deployment override; defaults to `gpt-6-sol`. |

GPT requests use strict JSON-schema category output. Luna and Sol use
`reasoning_effort: none` with a 512-completion-token limit; Astra uses
`reasoning_effort: low` with a 1024-completion-token limit because it rejects `none`.
These are server-owned settings, not caller overrides, and the catalog remains
limited to model identity/name/deployment rather than presenting runtime modes.
Decision answers read only the confirmed `answers.classification.choice` field,
with real `usage.input_tokens` / `usage.output_tokens`.

Both Functions use `authLevel: anonymous`. The site's `staticwebapp.config.json`
must permit anonymous access to both `/api/run` and `/api/catalog`. The backend
does not authenticate callers or require a user allowlist. Caller-provided
`x-ms-client-principal`, cookies, and forwarded-IP headers do not authorize requests
or allocate separate budgets. Foundry credentials remain server-side.

Each inference makes exactly one upstream request, uses a 40-second abort signal,
blocks redirects, and measures from immediately before fetch to complete response-body
reading using a monotonic clock. There are no retries or fallback models. Logs contain
typed error codes/statuses only, never credentials, prompt text, or upstream bodies.

The process-local limiter permits 16 concurrent requests and 96 starts in a rolling
minute, shared by all callers on that instance. Invalid methods and inputs are
rejected before acquiring budget. Failed upstream attempts also count, and
concurrency is released on every completion. A local 429 explains the shared
limit and suggests retrying after requests finish or in one minute.
This is **not a distributed limiter or an Azure spend cap**: restarts reset counters
and scaled instances have independent counters, so total traffic can exceed this
per-instance budget. There is no durable storage or global budget. This publicly
accessible demo can consume the owner's existing Foundry quota; the limiter is only
a modest demo guard.

The tests inject fetch and clocks and never call live services. Runtime dependency
installation is performed by the deployment build, not the unit-test command.
