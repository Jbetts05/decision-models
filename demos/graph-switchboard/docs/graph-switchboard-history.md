# Graph Switchboard development history

Historical implementation notes and evaluation records. Some sections describe
superseded workflows, local evidence paths and the original deployment.
Use the [current demo guide](../README.md) for setup and
the supported single-submission experience, not the commands in this archive.

## Graph Switchboard

A live comparison application for **Microsoft-Decision-1 versus Sol-only**,
using the same synthetic troubleshooting graph
in PostgreSQL / Apache AGE. This is a traversal experiment, not an ingestion
pipeline or a production vehicle diagnostic tool.

The v4.2.0 dataset contains **10 fictional vehicle configurations,
37 published procedures, 417 nodes and 423 relationships**. The main picker
contains ten distinct customer/technician problems and ten clearly grouped
versions with workshop records already available, including seven new
source-authored journeys: slow cranking, intermittent charging warnings,
temperature rising in traffic, strong but warm vent air, one dead power
window, weak washer delivery and patchy rear-window demisting.
The research corpus retains the [original three historical journeys](case-journeys-v4.md)
and all 72 vehicle-applicability cases. Ten fictional diagnostic guides and an explicit
[vehicle-variant source schedule](../data/traversal/source-material/SG-04-vehicle-applicability.md)
define the graph; expected case answers remain separate.

The current experience is **one problem -> real graph traversal -> recommendation**.
The deployed revision is `graph-switchboard-y2jdbl3udl54e--0000018`, using frozen
v4.2.0, workflow `md1-entry-v1` and input policy `single-problem-v1`.
The action is **Get recommendation**: exactly one comparison, using only the
problem, vehicle and optional records visible before submission. MD1 and Sol
start independently with fresh context. No record releases, scripted follow-up
comparisons or invented observations are added. A complaint can produce a useful
next check; a supported finding requires sufficient supplied evidence.
Each lane shows its actual recommendation route and source reference, with
finished metrics published independently. Wider retrieved context remains behind
**All retrieved**; it is not drawn as an observed route. The historical staged
revision 16 was technically verified but its interaction model was explicitly
rejected by the user; it is not the current product contract.

Model disagreement remains visible, including an observed MD1 clarification
where the supplied lean-running records support Sol's workshop handoff. A
finished comparison is not a guarantee that either model chose the right route.

**[Open the live Graph Switchboard](https://graph-switchboard.example.invalid)**.

The side-by-side UI follows the existing
[AI Switchboard demo](https://github.com/Jbetts05/decision-model-demo)
(`web/index.html`, reference commit `b153122d5892428fcbdfd9b42e0658c14ae43615`):
warm off-white surfaces, white panels, rose accent, Segoe UI typography and
compact monospace telemetry.

### Run on Windows

Requires Python 3.10+, Docker Desktop, Azure CLI signed in to the intended
subscription, and existing Foundry deployments for Decision-1 and Sol or Astra.
The local commands below do not provision Azure resources.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item config.example.json config.local.json
# Set the resource endpoint and actual deployment names in config.local.json.
az login
.\.venv\Scripts\python.exe -m traversal generate
.\.venv\Scripts\python.exe -m traversal db-up
.\.venv\Scripts\python.exe -m traversal load
.\.venv\Scripts\python.exe -m traversal serve
```

Open **http://127.0.0.1:8766**. Choose an **Example problem** and select
**Get recommendation**. The default washer-delivery example and nine other main
problems use only the facts already shown. A separate **Problems with workshop
records already available** group supplies all its authored records upfront;
these are optional input examples, not tests performed by either model.
Every click starts one fresh comparison. There are no automatic follow-up inputs.
The ten main problems are different complaints, not the same pressure report
repeated for different vehicles. Enable **Challenge cases**
in **Evidence & sources** to access diagnostic challenges and the
separate **Vehicle applicability comparisons** group. That disclosure contains editable records, source guides
and the challenge-case toggle; these details are collapsed by default.
**New problem** clears the report and records while retaining the deliberate
vehicle selection. Unknown fields stay unknown; changing the vehicle never
rewrites the report or observations.
Both workflows receive the original natural-language report and supplied
observations, without fixture-derived procedure names or starting-node hints.
Python uses fixed parameterised Cypher to retrieve all published entries for
the selected make/model/year/configuration. This is an applicability filter,
not semantic interpretation. MD1 receives the original input and complete
source entry criteria and selects one returned entry, clarification or
unsupported scope. Missing vehicle fields clarify without inference; no
applicable published vehicle stops as unsupported. Selected entries are
revalidated against actual AGE publication, applicability and ENTRY_POINT.
Decision-1 then chooses supported routes. Sol-only independently generates Cypher
and may answer from its first query's results or request additional reads.
If a Sol answer fails structural path validation after retrieval, its rejected
answer and validation error are returned to Sol within the existing five-turn
limit. Sol must supply any correction itself; the controller never edits the path
or supplies an expected answer. Rejections stay visible in Key execution/history,
and every additional call is charged to Sol. Provider/database failures and
unresolved final-turn validation errors remain explicit failures.
Both workflows execute against real AGE and Foundry; neither must wait for or
reuse the other workflow's entry selection.
Every submission clears the previous graph and starts fresh model contexts;
the browser does not send a previous-run identifier. Public continuation requests
are rejected before inference and the release endpoint is not exposed.
Metrics describe this comparison only; historical durable records and usage
remain intact. Editing an input clears stale recommendations rather than
leaving an old finding under a different problem.
Model errors and interrupted saves remain visible without automatic restarts
or substituted fallbacks. Interrupted streams explicitly disclose unavailable
additional usage. Model disagreement is shown as two recommendations,
not silently merged. A source-supported workshop handoff remains a handoff,
not an invented component diagnosis.
The backend uses Entra authentication through Azure CLI,
or an optional `AZURE_API_KEY` environment variable; credentials are never sent
to the browser. Set `subscription` in local config to avoid changing your
Azure CLI default.

`db-up` generates a random local database password in gitignored `.env` and
starts the pinned `apache/age:release_PG16_1.6.0` image on loopback port 55432.
The graph persists in a Docker volume. `DATABASE_URL` can override the local DSN.
`docker compose stop` stops this application's database without deleting data.

### What you can see

- Initially empty graphs that grow only from actual run-time AGE query results,
  with pan, zoom, fit and node inspection. The viewport follows the actual
  selected state. After entry selection, the default drawing contains only the
  selected procedure, not shared-vehicle applicability links or other entry
  candidates. **All retrieved** explicitly reveals that wider context;
  **Selected procedure** returns to the diagnostic view. As each lane finishes,
  **Answer route** shows its complete actual returned path and retrieved entry,
  ending at the highlighted recommended Action or supported RootCause.
  Unselected branches are not presented as observed outcomes. **Fit graph** fits the
  current view. All retrieved data remains in the lane's store and download.
  No procedure prefetch endpoint exists.
- The MD1 lane's entry input, exact requests/responses, fixed parameterised
  Cypher, returned candidates, option probabilities and verified starting state,
  under **Entry selection details**. The independent
  Sol-only lane shows its own first request/query and subsequent decisions.
  An unresolved MD1 entry does not prevent Sol-only from running.
- Decision-1's current node, available result edges, actual option probabilities,
  and the path it follows. Mandatory single outgoing procedure steps use code,
  not an unnecessary model call.
- Sol's actual generated Cypher, returned database rows, and final answer path.
  A query may read a whole procedure: **database reads are not graph hops**.
  Retrieved candidates are distinct from selected/validated routes; nodes and
  edges never come from oracle paths or a simulated traversal animation.
- Exact agreement with expected status, target and ordered path; end-to-end time;
  provider-reported input/output tokens; estimated token cost when rates are
  configured; returned path hops; model calls; and graph-query count.
  Each lane publishes its finished result and frozen metrics as soon as its own
  work ends, without waiting for its peer. Diagnostic badges distinguish
  **Recommendation ready**, **Needs clarification**, **Workshop review** and
  **Finding supported**; finishing a comparison does not imply a completed diagnosis.
  Downloads remain gated on the paired durable save.
  A save failure is reported, not presented as a completed comparison.
  The overall answer is above both lanes; each lane's source-backed result is
  above its graph. **Why this recommendation** shows the original submitted
  problem, upfront records, selected published conditions, instruction and source
  reference. These are returned guidance and supplied observations, not claims
  that the model performed physical tests.
- Separate execution timelines for Decision-1 and Sol, each with its own
  step duration, cumulative elapsed time and independent selection / follow controls. There
  is no merged timeline. Downloadable run JSON retains both method-labelled
  event streams. Events reflect actual application requests and responses, not
  model-internal reasoning or simulated animation.
- A visible execution timeline in each lane, with the current operation above the
  graph. Inspect any numbered step to see actual Decision-1 inputs, branch
  scores, controller-only transitions, Sol request messages, generated Cypher
  and returned AGE rows. Selecting a step pins its details and marks the
  relevant graph position without changing the live path; **Follow latest**
  resumes incoming events and centres the current step, including in branching
  procedures. Wider returned context remains available through **All retrieved**.
  By default, **Key execution** shows model
  calls with paired outputs, graph queries/results and validated answers.
  **All events** independently exposes each lane's complete recorded trace;
  downloads always retain every raw event. Step counts are distinct from hops
  and model calls. Early-result and durable-save bookkeeping no longer appear
  as two identical terminal results in Key execution. Downloads retain the
  exact frozen submission, both results and all raw events from that one run.
  The **controller is Python application code, not an LLM**.
  Both lanes also expose its fixed Cypher, exact bound parameters and a
  display-only query with those values substituted:
  Decision-1 selects branches; it does not generate the neighbour-fetch queries.
  Sol-only starts with its own original-input conversation and may retrieve a
  complete relevant procedure in one query; it is not artificially forced into
  an intake phase or one model call per hop.
  Visibility covers observable API/database inputs and outputs, never credentials
  or provider-internal reasoning.

The graph is not an embedded AGE Viewer. [Apache AGE Viewer](https://github.com/apache/age-viewer)
is a separate general-purpose graph browser; this application adds model-specific
instrumentation around AGE queries.

Editable questions, vehicle fields and observations use live inference, but disable expected-output
scoring and restart both model contexts when they differ from the original fixture.
Edited runs cannot release the next authored snapshot. Editing input does not create
new ground truth. Live inputs contain customer/technician reports and available
observations, not supplied graph IDs or the expected procedure title.
Each model independently resolves graph relevance from those inputs within its
architecture. Expected output is released for scoring
only after completion, never as graph-rendering input.
Do not enter real customer or vehicle data: inputs and model responses are sent
to your Foundry deployment and saved locally under `results/local/interactive/`.

### Corpus and evaluation contract

`data/traversal/` contains reproducible, versioned generated artifacts:

| Artifact | Contents |
| --- | --- |
| `graph.json` | v4.2.0: 417 nodes, 423 relationships; ten vehicles, thirty-seven procedures and fifty source-supported terminal findings |
| `queries.jsonl` | 143 snapshots: the historical 87 cases plus 28 staged releases and 28 contrast cases in seven additional families; internal start IDs are evaluation metadata only |
| `oracle.jsonl` | Hidden expected status, target and full edge path; scorer only |
| `manifest.json` | Content hashes, source-guide hashes, entity/relationship coverage and limitations |
| `source-material/` | Ten fictional problem guides and the vehicle-variant schedule, also readable in the application |
| `problem-journeys.json` | Separate authored customer reports, released workshop records and expected routes for the seven additional families; never served as model input |

The schema supports five entity types and five relationship types:
VehicleModel, Procedure, Condition, Action and RootCause; APPLIES_TO,
ENTRY_POINT, NEXT_ACTION, RESULT and INDICATES. RESULT rules express the
observations needed to select a published branch. NEXT_ACTION weights remain
unavailable/null; AGE omits null-valued properties, which is equivalent to an
unset weight, not equal likelihood. These guides do not require an
INDICATES edge, so the generator does not invent one.

The original journeys use a **2021 Brand X Model A, petrol**. The expanded
graph covers Brand X Models A-J, years 2020-2024, with petrol and turbo-petrol
configurations. Each vehicle has misfire, lean/rough-idle and missing-airflow
guidance. These are illustrative procedures, not real Brand X service
specifications. Confirmed root causes require an authored discriminating
finding; ordinary test passes lead to further investigation or handoff, not a
manufactured catch-all fault. The validator checks the consistency of authored
confirmation and provenance metadata, not the automotive truth of a procedure.
New guidance and root-cause edges still require human domain review.

The main journeys end in a confirmed plug fault, a complete but non-localising
workshop referral, and a confirmed fan-control-unit fault. The lean journey
deliberately does **not** invent a fuel-pump diagnosis. Records include old jobs,
cropped units, staged controls and return comparisons. Three contrast cases
exercise conflicting current codes, a single changed recurrence observation,
and a temperature-only complaint outside Model A's source scope.
Model E separately has explicit published cooling-temperature guidance; this
does not change the older Model A case.

The frozen research corpus retains four independently authored evidence
snapshots per new problem: a natural complaint, relevant workshop findings,
partial confirmation and completed confirmation. These are historical evaluation
inputs, not a public staged interaction. The live picker offers a complaint
or a separately grouped input with all completed records already supplied.
The graph supplies a next check or clarification before a supported finding;
it does not diagnose a part from the customer's complaint. Numeric limits,
Boolean permissions, command/response patterns, independent localisation and
non-localising branches exercise different routes. New successful terminal
paths have four, six or eight edges. All 49 new RESULT branches have a
separately authored positive or negative case, including exact numeric
boundaries and ten distinct supported terminal findings across the new branches.
The readable customer/technician response is authored in the selected source
node and displayed only after that node is actually returned from AGE.
It is not an extra Sol explanation or an oracle answer.

| New customer problem | Published route through workshop records | Supported final finding |
| --- | --- | --- |
| Engine turns over slowly | Load voltage, then controlled battery comparison | Original battery isolated; an alternate branch independently localises a return connection |
| Charging warning during running | Drive inspection, episode voltage, charging-unit comparison | Original charging unit isolated |
| Temperature rises in traffic | Fan command/response, supply/motor assessment, relay comparison | Relay isolated; an alternate branch independently isolates the motor |
| Strong airflow stays warm | Vent temperature, door command/position, actuator comparison | Blend-door actuator isolated |
| One window will not move | Permission, local/master commands, switch comparison | Local switch isolated; an alternate branch independently isolates the motor |
| Washers only dribble | Fluid supply, line/jet restriction, pressure, pump comparison | Original washer pump isolated |
| One rear-window stripe stays misted | Heating map, independent same-strip continuity survey | One heating-strip conductor break isolated |

Preflight paired Foundry/AGE runs over the seven new four-release journeys
produced 27/28 exact MD1 outcomes and 28/28 Sol-only outcomes. MD1 unnecessarily
requested entry clarification for the initial warm-vents complaint; that
failure remains in the run artifacts and was not used to rewrite the sources
or expected answer. Both lanes reached the supported final finding in all
seven journeys. This is a bounded authored-example run, not a held-out accuracy
estimate. Evidence: `results/local/problem-variety-staged/`. That preflight
graph is retained in manifest history: the final graph corrects a copied
vehicle name in safety metadata without changing sources, reports or expected
paths. Do not attribute the preflight measurements to the final graph hash.

The deployed final graph `1754a4eb0db8` was separately exercised over all 28
new staged snapshots: MD1 again matched 27/28, Sol-only 28/28, with the same
retained initial warm-vents clarification and no operational/model errors.
Both lanes reached all seven final findings. A production browser completed
the four-release washer journey and a metered rerun, with all ten lane
outcomes matching, real graph provenance, and the source-authored answer
visible at the selected returned node. A separate slow-cranking browser run
verified independently visible frozen MD1 metrics at 4.34s while Sol continued
to 8.51s. These are actual observations, not simulated routes or a held-out
accuracy claim. Evidence: `results/cloud/problem-variety-*`.

### Multi-vehicle comparison contract

The seventy-two new cases comprise twenty matched pressure cases (the same report
and 310 or 500 kPa record across ten selected vehicles), thirty complete
multi-step comparison cases (ignition, localisation and fan control for each
vehicle), ten clarification/unsupported/evidence-boundary challenges,
six matched ignition-order/fan-pattern cases, and six deeper partial,
unperformed or non-localising comparison cases.
All seventy-two remain available in the evaluation picker, not the main
problem list. Their public reports and expected paths are unchanged.

Choosing the wrong vehicle can change the result: 310 kPa permits localisation
for Model A but requires pressure referral for Model B. Five vehicles review
plugs before coils; the other five review coils first. Original misfire and
donor cylinders differ, pressure bands and localisation joints differ, and
some fan guides require stages 1-2 absent / 3-4 present rather than 1-3 absent /
4 present. These differences come from SG-04, not model-generated observations.
Every terminal finding still requires a complete source-supported comparison.

Both architectures receive the same selected vehicle, original question and
released records. Pair groups, reviewer paths, fixture start IDs and future
records are not model input. Missing vehicle fields carry no hidden resolved
vehicle ID. Vehicle conflicts require clarification; absent configurations
are unsupported rather than silently mapped to the closest published vehicle.
The catalogue exposes vehicle metadata for selection, not procedure topology.

This is a controlled applicability/branch-following experiment, not evidence
of thirty independent fault families, automotive diagnostic accuracy or
large-scale search performance. The original thirty procedures share three authored
families; the seven additional procedures have one explicitly applicable
vehicle each, rather than being cloned to inflate coverage. Several vehicle-variant oracle paths are assembled from the graph; independent
literal semantic assertions check vehicle bands and changed review order,
but this is not an independently adjudicated or held-out evaluation set.
The vehicle picker and MD1-led entry workflow are implemented; corpus size alone
is not evidence of entry-selection accuracy. Runs record the workflow identifier
alongside the frozen corpus manifest.
Do not compare v4.1.1 timings or exact-match rates directly with v4.0: the graph
and candidate population have changed. Fix the graph/source hashes for paired runs
and retain failures rather than changing the story or replacing model output.

Claude Opus 5.5 adversarially reviewed the historical v4.1.1 source pack, generation, fixtures
and comparison contract on 20 October 2026. Its verdict was conditionally fit,
with four blocking findings: stale variant rules, stale joint/example text,
answer-revealing unsupported IDs and insufficient matched order/pattern cases.
Those findings were corrected with explicit regression cases. This is a
review plus corrections, not an independent reviewer certification of model accuracy
and not an adversarial review of the seven new v4.2.0 families.
Post-correction checks passed 138 Python regressions (including the complete
expanded graph and authored paths against real AGE), ten JavaScript checks
and browser catalogue/source/journey checks. Nine actual Foundry comparison
cases produced eighteen matching lane outcomes, including terminal paths in
all three families. Sol-only made three rejected graph reads and recovered
within its normal recorded budgets; those failures remain in the traces.
These are bounded developer smoke runs, not a live-model pass over all 87
snapshots or a held-out accuracy estimate. Raw evidence is retained under
`results/local/vehicle-v411-reviewed-smoke/` and
`results/local/vehicle-v411-terminal-smoke/`.

### MD1-led entry experiment

The complete frozen v4.1.1 pass for `md1-entry-v1` exercised all 87 snapshots
with actual Foundry and AGE. Entry status/target agreed with the authored
expectation in all 87: **73 actual MD1 entry calls, eight reuses of this lane's
previous MD1 entry, and six deterministic missing/unsupported-vehicle stops**.
The MD1 lane made no Sol calls. This is not 87 independent MD1 classifications.

Final status, target and complete ordered path agreement:

| Authored group | Snapshots | MD1 exact | Sol-only exact |
| --- | ---: | ---: | ---: |
| Original staged journeys | 12 | 10 | 12 |
| Original contrasts | 3 | 3 | 3 |
| Matched pressure, 310 kPa | 10 | 10 | 10 |
| Matched pressure, 500 kPa | 10 | 10 | 10 |
| Controlled fan comparisons | 10 | 10 | 10 |
| Controlled ignition comparisons | 10 | 5 | 10 |
| Controlled localisation comparisons | 10 | 1 | 10 |
| Matched ignition order | 2 | 2 | 2 |
| Matched fan pattern, stages 1-2 | 2 | 2 | 2 |
| Matched fan pattern, stages 1-3 | 2 | 2 | 2 |
| Deeper negative paths | 6 | 5 | 6 |
| Vehicle-context boundaries | 7 | 7 | 7 |
| Competing entry conditions | 1 | 1 | 1 |
| Pressure-evidence boundaries | 2 | 1 | 2 |

The MD1 lane matched 69 final outcomes and Sol matched 87, but these correlated
authored snapshots are not a pooled real-world accuracy estimate. Five MD1
ignition paths selected an incorrect RESULT toward referral rather than the
expected terminal finding. Other misses included premature next-action stops,
misfire over-clarification and a wrong-vehicle-record handling error. Correct
entry selection did not imply correct diagnostic continuation.
There were no operational/model errors. Sol made nine rejected graph reads
and recovered within its normal budget; MD1 made none. These are retained,
not silently retried outside the budget.

Including entry, the MD1 lane made 194 calls with $0.022893066 estimated token
cost; Sol made 236 with $4.8718524. These costs include incorrect outcomes and
must not be interpreted as equal-quality savings. Per-group median latency,
median/total cost, calls, status/target/path scoring and raw events are in
`results/local/md1-entry-v1-full/{groups,summary,corpus,workflow}.json` and the
individual case files. The strict acceptance runner exited nonzero for the
18 retained MD1 mismatches. The corpus, source hashes and oracle were not
changed to fit those results.

The user-requested v4.1.2 presentation cleanup removes generated customer-release
prefixes from model input and shortens the record wrapper to **Job card**.
Customer wording, record contents, source rules, graph content and expected
paths are unchanged; release numbers remain UI/session metadata. The graph's
dataset-version field changes its hash and namespace. V4.1.1 hashes and results
are preserved, and the 69/87 versus 87/87 results above apply only to v4.1.1,
not to cleaned v4.1.2 inputs.

Freeze each dataset version, including current v4.2.0, by its source and artifact hashes in `manifest.json`; persisted
comparison records now include that complete manifest. Changes to evidence or
expected answers require a reproduced source contradiction, invalid expected
outcome or answer leak, with a cited source section. A model failure alone is
not grounds to rewrite a case. Any such correction requires a new version,
preserved prior hashes/results, and rerunning both lanes on the same cases.
Prompt and architecture experiments use the frozen corpus unchanged.
Report original journeys, matched pressure, matched order/pattern, terminal
comparisons and boundary/negative paths separately, with status/target/path
agreement and invalid graph reads; never claim accuracy from one pooled rate.

These are **not real technician sessions**. Operators release authored records,
never model-simulated observations. A complaint without completed diagnostic
evidence should lead to a published next action or clarification, not an invented
terminal diagnosis. Additional physical observations are not simulated.
The corpus is authored fictional guidance, not manufacturer service data or
independently expert-adjudicated evidence. Case counts are not independent
real-world diagnostic problems. Exact composition, hashes and limitations are
recorded in the versioned manifest.
The legacy offline evaluator starts at a known node and does not evaluate
the new application's end-to-end entry retrieval. Its results must not be used
as evidence for the interactive comparison.

The Decision-1 walker receives the current action, evidence and outgoing result
choices, including explicit clarification and missing-observation outcomes.
The baseline receives the same original query/evidence and graph schema,
then independently generates its own Cypher. It may inspect relevant guidance in one read or use
multiple queries. Both share publication, vehicle applicability, bounded
execution and final path-validity enforcement. Neither receives oracle paths.
This compares **two architectures**, not only two models.
Sol's relevance and ambiguity judgments remain model decisions: a broad read
may legitimately return several entries before a narrower query resolves the
starting point. Candidate counts are not a deterministic ambiguity detector.
Structural path/publication checks do not prove correct interpretation of every
natural-language report or observation; explicit challenge cases exercise that
boundary without implying a general diagnostic safety guarantee.
The interactive comparison is concurrent, not an isolated performance
benchmark: network conditions, provider load and reported cache hits can change
latency and cost. A first successful Cypher query can retrieve enough evidence
for Sol-only's subsequent answer without an extra intake phase. It does not mean
the model can know the database response before that query executes.

```powershell
.\.venv\Scripts\python.exe -m traversal validate
# With the app running: actual inference, manual-release lineage and own-lane reuse.
.\.venv\Scripts\python.exe tests\live_journey_check.py `
  --output results\local\journey-check
.\.venv\Scripts\python.exe tests\live_journey_check.py --contrasts `
  --output results\local\journey-contrasts
# Full applicability suite; actual Foundry charges apply, no simulated inference.
.\.venv\Scripts\python.exe tests\live_journey_check.py --vehicles `
  --output results\local\vehicle-check
# Seven additional four-release problem journeys, with actual Foundry charges.
.\.venv\Scripts\python.exe tests\live_journey_check.py --problems `
  --output results\local\new-problem-journeys
# All 143 snapshots, independent concurrent lanes, grouped metrics and raw failures.
.\.venv\Scripts\python.exe tests\live_journey_check.py --all `
  --output results\local\md1-entry-full
# A bounded matched pair; repeat --case to select explicit cases.
.\.venv\Scripts\python.exe tests\live_journey_check.py --vehicles `
  --case vehicle-a21-pressure-310 --case vehicle-b21-pressure-310 `
  --output results\local\vehicle-pair
```

The legacy offline evaluator alternates method order using a fixed random seed and samples
categories round-robin. It runs methods sequentially for paired measurements;
the interactive app runs them concurrently. Batch timing excludes initial token
acquisition; UI timing includes authentication/connection setup. Neither path
uses paid warm-ups or hidden HTTP retries. Failed or rejected LLM queries are
returned to the LLM within its recorded five-turn budget.
The interactive workflow allows at most one MD1 entry call; later own-entry
reuse has no entry inference call. The retained legacy Sol-entry resolver is
not used by the application. `live_journey_check.py` exercises the actual
concurrent application, preserves mismatches and operational failures, and
reports entry/status/target/path agreement, invalid reads, calls, cost and
latency by authored group. It does not assume either model always diagnoses
correctly and does not change inputs in response to a model failure.

Historical v2 benchmark records remain in `results/local/paired-sol-v2-52/`
for auditability. They used a different artificial graph, known starting nodes
and a different problem distribution. They are **not comparable to the rebuilt
demo** and are not current model-accuracy evidence.

The earlier v3 brief-gap and adversarial review remains available in
[the rebuild review](demo-rebuild-review.md).

V4 development runs are retained under `results/local/journey-v4-*`. They
exposed MD1 over-abstention on the multi-test misfire journey, including an
unperformed coil review and separate coil/plug records. These mismatches remain
visible; the runtime does not replace them with oracle answers or quietly ask
Sol to correct MD1. The pressure-unit, complete non-localising referral and
fan-control journeys exercise different boundaries, not a claim of universal
model accuracy. Prompt refinements and repeat developer runs are not held-out
evaluation. Historical failures are retained alongside later runs.

The default Decision-1 gate threshold is **0.0, explicitly untuned**: the model
can still choose abstention. Use development/validation data to choose a
threshold; do not tune on the held-out test sample. Option probability is not
root-cause likelihood or a calibrated safety guarantee.

### Metering, admission and read-only execution

Set `pricing.decision` and `pricing.baseline` in local config to applicable
USD-per-million input/output rates, with a dated source in `pricing.source`.
The Decision-1 published rate is $0.042/million input tokens and zero for output.
GPT-6 Sol Global Standard is configured at $2 input / $10 output per million
tokens, with $0.20 cached input, from the
[Azure pricing snapshot](https://www.azurespeed.com/AzureAiModelPricing/Models/openai-gpt-6-sol)
checked 2026-10-19. Rates remain deployment configuration. Missing prices display a dash rather
than an invented value. Provider usage, timings and individual call attempts
are preserved in the run record.

The UI admits one comparison globally. PostgreSQL-backed admission reserves
up to 24 calls (3 hybrid entry / 16 walker / 5 independent baseline) before a run and records every attempted
inference before sending it. The UTC-daily ceiling defaults to 1,000 calls,
configured by `SERVER_DAILY_MAX_CALLS`; restarting the app does not reset it.
Busy or exhausted admission returns HTTP 429 with Retry-After. Completed and
failed runs persist even if the browser disconnects. Interrupted reservations
fail closed and require explicit operator reconciliation; they are never
silently forgotten. Batch evaluation has its separate `max_calls` budget.

Hybrid totals include its own Sol entry and Decision-1 traversal. Sol-only totals
include only its independently executed calls and reads. No entry inference or
cost is reused across lanes. Run records retain phase-specific usage,
deployment call breakdowns and the actual physical call count. Bootstrap migrates existing call
constraints without deleting prior runs or attempts.

Local serving binds to loopback and enforces Host/Origin checks. The database
loader creates a content-addressed graph without dropping existing graphs.
Read connections load AGE, switch to a SELECT-only `traversal_reader` role and
execute in PostgreSQL READ ONLY transactions with a three-second statement
timeout. Model Cypher is further restricted to a bounded MATCH/RETURN dialect
and at most 200 returned rows. It never becomes SQL or a write query.
Local owner connections bootstrap AGE and switch roles for reads. Cloud
bootstrap runs separately; the live app uses a non-admin database login with
graph-reader membership and access to ordinary run-record tables only.

### Azure deployment

The approved architecture uses public HTTPS Azure Container Apps, a private
PostgreSQL 17 Flexible Server with AGE 1.7.0, Key Vault, ACR and managed
identities in Sweden Central. PostgreSQL is allocated in the first available
approved region (North Europe, West Europe, UK South) and reached over
cross-region Azure Private Link, never a public database firewall rule.
Key Vault also uses a private endpoint and private DNS.
The models reuse the existing Foundry account.
The deployed app is in Sweden Central and its database is in North Europe.
Graph data and run records survive container replacement. The one-shot
bootstrap job initializes the graph and grants the runtime login its narrower
permissions; administrative credentials are not supplied to the web app.
Repeat deployments retain the graph and run records and verify the runtime
role's privileges again.

The deployment workflow and evidence live in `.azure/deployment-plan.md`.
From PowerShell 7.2+, with Docker and Azure CLI available:

```powershell
.\infra\deploy.ps1 -ValidateOnly
# After validation and deployment approval:
.\infra\deploy.ps1
```

The script creates only its isolated resource group plus an account-scoped
Foundry role assignment. Bicep resources are provisioned in parallel where
dependencies permit. It then activates AGE preload, builds and pushes a
content-addressed image, runs private-network database bootstrap, publishes the
app and checks readiness. `-SkipFoundation` resumes from a completed
foundation deployment. Runtime and bootstrap identities have distinct access.

Linux dependency wheels are downloaded into `.venv\wheelhouse` by the host's
verified HTTPS connection and installed offline into `/opt/venv` in the image.
The image contains no Azure CLI session, `.env`, local config or results.
On Windows generated deployment credentials are persisted using current-user
DPAPI encryption in ignored `.azure\deployment-secrets.clixml`. Deployment
parameter files are removed after use. Keep the encrypted state for repeat
deployments; outside Windows supply stable `GRAPH_ADMIN_PASSWORD` and
`GRAPH_APP_PASSWORD` environment secrets.

The resulting URL and immutable image are saved in ignored
`.azure\release.local.json`. `/health/live` checks the process;
`/health/ready` checks actual database and graph availability without inference.
Inspect Container Apps job/application logs in Log Analytics for deployment or
runtime errors.

Run `python -m traversal inspect` from the deployed image on the private
network to verify the full graph and inspect recent durable runs, call usage
and daily reservations without invoking either model. It uses
`APP_DATABASE_URL` when present, otherwise `DATABASE_URL`, and reads ordinary
tables inside a read-only transaction.

If a worker has crashed, first confirm its container/revision has stopped.
Then an operator with database access can explicitly reconcile the exact run:

```python
import os
from traversal.server import AppStore

AppStore(os.environ["DATABASE_URL"]).finish(
    "EXACT_RUN_ID",
    error="Operator reconciled confirmed terminated worker.",
)
```

This marks the interrupted run as an error and releases only unused
reservations. Attempted calls and their usage records remain; repeated
reconciliation is idempotent. Never reconcile a worker that is still running.

Cloud configuration uses `DATABASE_URL`, `AGE_PRELOADED=1`,
`APP_STORE_INITIALIZE=0`, `FOUNDRY_ENDPOINT`, `DECISION_DEPLOYMENT`,
`LLM_DEPLOYMENT`, `FOUNDRY_AUTH_MODE=managed_identity`, `AZURE_CLIENT_ID`,
`PUBLIC_ORIGIN`, `HOST`, `PORT`, `SERVER_DAILY_MAX_CALLS` and
`FOUNDRY_PRICING_JSON`. Local JSON configuration remains supported.

### Checks

```powershell
$env:AGE_INTEGRATION = "1"
$env:CLOUD_BACKEND_INTEGRATION = "1"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
# Uses installed Microsoft Edge, without downloading a browser.
.\.venv\Scripts\python.exe tests\browser_check.py
# Also run a real comparison through the UI.
.\.venv\Scripts\python.exe tests\browser_check.py --live
# Verify the deployed HTTPS application:
.\.venv\Scripts\python.exe tests\browser_check.py --base-url "https://APP-FQDN" --live
```

Omit `AGE_INTEGRATION` to run offline checks only. Test doubles exist only in the
unit tests; the application has no mock-inference fallback.

## Separate live vision idea

[Live vision demo design](../../../docs/proposals/live-vision.md): an implementation brief for a simple,
anonymous-access webcam demo using a future image-capable Microsoft decision
model deployed in Microsoft Foundry. The application is not implemented yet.