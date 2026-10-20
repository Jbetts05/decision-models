# Demo brief-gap review and acceptance register

Requested 2026-10-19. This register distinguishes observed defects from the
acceptance evidence needed to close them. The earlier deployed v2 benchmark
does not demonstrate realistic automotive entry retrieval.

## Current correction: one submission, one recommendation

The user explicitly rejected the unagreed evidence-release experience.
The B16 staged solution and related stage controls below are historical,
superseded decisions, not the current acceptance contract.

The corrected contract is **user problem in -> graph traversal ->
recommendation out with clear live traversal and evidence**.
One click sends exactly the visible problem, vehicle and optional records,
starts both lanes fresh and never adds a later fixture observation.
The public release endpoint is removed; continuation submissions are rejected.
Ten plain problem examples remain, alongside ten explicitly grouped cases with
all authored workshop records already visible upfront. The graph/source/oracle
research files are not rewritten to force a diagnosis.

Next-action recommendations are useful results, not failed diagnoses.
Every nonempty validated path, including a recommendation ending at an Action,
is shown as its lane's actual route immediately on lane completion.
Source references, submitted records and selected published conditions are
inspectable under each recommendation. Provider errors, structural rejection,
disagreement and unknown stream usage remain explicit.

Acceptance uses `tests\browser_recommendation_check.py` for one-request/no-release
behavior, empty initial graphs, actual returned-node/edge provenance, source
evidence, independent finished metrics, readable route geometry, exact
single-run downloads and mobile. `--replay` is explicitly historical UI
regression, not a new inference/accuracy claim; `--live` invokes the real service.
`tests\browser_demo_failures.py` covers operational failures, edits,
disagreement and visible rejected Sol answers without auto-retries.

Released as revision `--0000018`. All 161 integrated Python tests, seventeen
JavaScript tests, fifteen final historical-event UI cases and eight failure
modes passed. Actual final HTTPS complaint-only and upfront-record washer
comparisons passed one-submit/no-release behavior, exact recommendation paths,
source evidence, independent metrics, Fit/context, raw downloads and mobile.
The separate actual cooling check passed live clock/overlap, pin/follow/zoom,
applicability, reset and all strict browser assertions.
Evidence: `results/cloud/single-input-final-live` and
`results/cloud/single-input-strict-final`.

An additional real lean-records comparison produced an MD1 clarification
instead of the expected handoff; Sol reached that handoff. The strict accuracy
failure is retained in `results/cloud/single-input-live`. Its exact events
passed separate disagreement/UI regression without another inference attempt.
No facts, source guidance, oracle, threshold or model answer was changed to
manufacture agreement. The application contract is verified; universal model
accuracy is not claimed.

## Observed defects

| ID | Priority | Defect and evidence | Required correction and acceptance |
| --- | --- | --- | --- |
| B01 | Critical | `traversal/synthetic.py` generates bench fixtures, repeated operating profiles and an arbitrary retained-warning-latch conclusion. | Replace the graph with coherent, explicitly fictional automotive troubleshooting procedures. A warning or all-passed checks must not manufacture a root cause. Validate authored paths and terminal semantics. |
| B02 | Critical | `Service` in `traversal/server.py` inserts the known fixture procedure title and canonical current state into the user's question. | Send the original customer/technician report and visible vehicle context without oracle-derived routing hints. Inspect the actual first requests in both lanes. |
| B03 | Critical | Sol-only is forced to reuse the hybrid's Sol entry selection and conversation. | Start Sol-only independently from the same original input/schema. Permit a first query to retrieve enough information for an answer; do not force intake or a model call per hop. |
| B04 | High | The primary case list exposes evaluation labels such as operating profile, complete, wrong_unit and injection. | Use recognizable problem titles and natural reports in the demo; separate adversarial evaluation cases without removing them. Verify the deployed catalog and browser. |
| B05 | Critical | Completed observations are supplied upfront, but the demo can be mistaken for diagnosing an initial complaint. | A symptom-only report must return the next published diagnostic action or clarification, never invent test results. Distinguish a static supplied-evidence run from an interactive technician session. |
| B06 | High | Shared entry failures currently stop both lanes and shared costs are included in both totals. | Isolate hybrid intake failure from independent Sol-only execution. Meter every physical request exactly once and present each lane's actual complete workflow cost/time. |
| B07 | High | Well-specified fixture/profile selection hides ambiguity and unsupported vehicle handling. | Exercise overlapping symptoms, missing identity, conflicting identity, unsupported applicability and unpublished procedures without fixture fallback. |
| B08 | Medium | A timeline timestamp alone does not show how long an operation took. | Show measured step duration and cumulative elapsed time, update pending operations live, freeze completed rows, and leave unmeasured event-marker durations unavailable. |
| B09 | High | Thousands of templated variants can look like thousands of independent diagnostic problems; historical known-start accuracy is not new-workflow evidence. | Report actual corpus composition and limitations; retain historical measurements only as explicitly obsolete/non-comparable records. Preserve real exact/non-exact outcomes. |
| B10 | High | Existing acceptance checks assume the first fixture is an exact seven-hop terminal diagnosis. | Cover raw symptom-only queries, next actions, multi-hop observed cases, legitimate model errors, independent baseline entry and one-query baseline answers. |
| B11 | High | Public stream fields were filtered, but the original provider response could still enter durable call records. | Apply the same public response whitelist before persistence and streaming; test that provider-private fields and credentials are absent from both. |
| B12 | High | Merely returning a Condition or Action does not establish that it is a permitted procedure starting point. | Verify the chosen initial state against actual published ENTRY_POINT relationships and applicability; reject unsupported arbitrary jumps. |
| B13 | High | Real execution exposed `VehicleModel.year` in the prompt although AGE stores `model_year`. | Describe the actual AGE schema in both prompts and rerun real generated-query execution. |
| B14 | High | Readable graph inspection exposed generic Action and intermediate Condition descriptions despite specific instructions and result rules. | Use domain-specific action descriptions and states describing already established findings; preserve IDs, topology, rules and terminal semantics. |
| B15 | Medium | Broad multi-procedure reads spread related nodes across layers and made the selected procedure unreadable or offscreen. | Prioritize the actual selected scope in layout and viewport; retain all retrieved nodes, manual controls and full-overview fit. |

## Release gate

No defect is closed by a label change alone. Closure requires deterministic
schema/oracle/accounting/timing checks and actual model/database/browser
execution against the rewritten corpus. Graphs must remain empty until real
successful query results arrive. Requests, responses, queries, candidates,
failures and selected routes must remain inspectable; credentials and
provider-private reasoning must not be exposed.

The application remains a demonstration with fictional guidance, not validated
vehicle service instructions. Ingestion, production safety approval, repairs
and autonomous physical technician activity remain outside this PoC.

## Independent adversarial review

A separate read-only reviewer examined the original input construction, graph,
runtime, persistence and timeline. It confirmed B01-B03 as blockers and raised
the following additional acceptance requirements:

- Cross-procedure ambiguity needs deliberate cases and visible handling, not
  just a prompt instructing the model to be careful.
- Query duration must use the measured `query_ms` where available.
- Competing outgoing actions must either have a real selection policy or be
  explicitly excluded and rejected by corpus validation.
- Vehicle identity must be clearly supplied by the user/visible context, never
  silently supplied as privileged fixture ground truth.
- Terminal handoff actions must be represented in the corpus and tested.
- Production path validation tests must exercise the real active validator,
  not only a superseded helper.

Two proposed checks were refined to avoid false guarantees: a naturally written
report may legitimately share words with a guide, so input-integrity checks
must prove original text is unchanged rather than banning all string overlap.
Likewise, a broad query returning multiple nodes does not by itself prove the
problem is ambiguous; only applicable entry candidates and the supplied
discriminating evidence are relevant.

The reviewer independently confirmed the working implementation removes
fixture-prefix injection, runs Sol-only independently, validates answers against
its own returned graph data and filters provider-private fields before
persistence. These findings are supplemented by the actual local checks below;
cloud release acceptance remains a separate gate.

## Rebuild evidence and remaining boundaries

The rewritten v3 corpus contains 102 nodes, 114 relationships and 67 deliberate
scenarios: 25 demonstrations and 42 evaluation cases, across eight published
procedures and one draft. Root-cause edges require authored confirmation
metadata; normal observations can lead to an actual handoff action. Historical
v2 accuracy measurements are explicitly not evidence for this application.

The frozen backend passed 109 Python tests with real AGE/PostgreSQL integrations,
plus ten deterministic JavaScript timing/viewport/title tests. Real local browser execution
verified original inputs, independent lanes, actual returned-data provenance,
exact downloads, live/frozen timing and mobile layout. All ten real end-to-end
scenario contracts passed on final graph
`traversal_87f7f3707ee2`. The rebuilt application is now deployed and verified
on healthy revision `--0000007`, with all ten cloud scenario contracts and the
real cloud browser acceptance passing.

Actual local inference covered a symptom-only report, an observed root-cause
route, editing an engine problem into a blower fixture, an ambiguous warning,
missing identity and conflicting identity. Both lanes clarified the ambiguous
and missing-identity cases. Hybrid clarified conflicting identity; Sol-only
reported unsupported. A Sol-only symptom run clarified rather than matching
the expected next action; that non-exact result was retained, not relabelled.
These are observed executions, not a statistical accuracy claim.

The first real browser run exposed an additional schema defect: the prompts
advertised `VehicleModel.year`, but AGE stores `VehicleModel.model_year`.
Both prompts now describe the actual graph field and distinguish it from the
public input's `vehicle.year`; the real checks used the corrected backend.

Final presentation review also removed diagnosis-spoiling lesson titles from
the main scenario list and added readable active-state framing after broad
retrieval. This changes neither model inputs nor which data was actually read;
all retrieved nodes remain inspectable.
The final Action renderer now prefers authored descriptions/instructions over
generic result-type labels. Sixty-three node descriptions were made
domain-specific without changing IDs, topology, result rules or expected paths.

The strict local adversarial runs safely clarified contradictory readings,
incompatible pressure units and an embedded worksheet command; both lanes
rejected unpublished infotainment guidance. Sol sometimes clarified during
hybrid intake, before Decision-1 ran. Those empty-path clarifications retain
their original non-exact target/path scores. They establish safe full-workflow
abstention in those runs, not adversarial Decision-1 routing coverage.
The earlier strict run's safe abstention and an actual transient provider
connection failure are retained in the local artifacts rather than overwritten.

### Local closure matrix

| Defects | Implemented correction and evidence |
| --- | --- |
| B01, B04, B09, B14 | New authored graph/scenarios, natural non-spoiler demo titles and specific node descriptions; 24 corpus/quality checks and embedded Linux-image validation. |
| B02, B03, B06, B10 | Unchanged original input, independent baseline, isolated failures and physical accounting; contract regressions plus real edited-input, symptom and observed-route execution. |
| B05, B07, B12 | Next-action/clarification stops, actual entry/publication/applicability validation and deliberate adversarial scenarios; real final-corpus acceptance with original scores retained. |
| B08, B15 | Measured Step/Total timers and actual selected-scope layout; ten deterministic UI checks plus real desktop/mobile, provenance, pin/follow and manual-control acceptance. |
| B11 | Shared provider-response whitelist before both persistence and streaming; durable-record and public-event regression coverage. |
| B13 | Actual `model_year` schema in both prompts; subsequent real generated queries passed against AGE. |

### Cloud release and routing-only coverage

All B01-B15 implementation corrections are released. The private bootstrap
succeeded, revision `--0000007` is healthy at 100 percent traffic, live roles
remain correctly scoped, and deployed JavaScript matches the verified source.
Proof is recorded in `.azure/deployment-plan.md`,
`results/cloud/entry-rebuild` and `results/cloud/browser-rebuild-final`.

To avoid mistaking Sol's early abstention for MD1 evidence, separate final-graph
known-start routing probes exercised actual Decision-1 on conflicting voltage,
wrong pressure units and embedded instructions. All three full known-start
routes clarified exactly; a separate mid-route pressure probe also clarified
but retains its non-exact full-route score. Six actual provider calls and
their inputs, outputs, usage, probabilities and AGE traces are retained in
`results/local/md1-routing-canonical`. These are routing-only checks, not
end-to-end entry retrieval or a model accuracy benchmark.

Cloud browser verification exposed a harness-only Chromium response-buffer
failure. The harness now asynchronously reads a clone of the same actual
stream rather than relying on CDP's retained body. It neither blocks live
delivery nor generates extra inference, and preserves exact raw-download
equality. The released production image did not change.

Two limits remain explicit rather than hidden by brittle code:

- Relevance, conflicting-language interpretation and ambiguity are model
  judgments, tested with deliberate scenarios. Broad retrieval is legitimate;
  multiple returned nodes do not automatically require clarification.
- Confirmation flags and evidence descriptions are assertions by the procedure
  author. Validation establishes structural/provenance consistency, not
  manufacturer-approved diagnostic truth. New procedures still require
  human domain review.

The demo cannot establish a general natural-language safety guarantee or the
economic superiority of either architecture. Supplied evidence is static;
the application does not perform or simulate physical workshop tests.

## Problem-to-answer adversarial review (2026-10-20)

A separate read-only adversarial reviewer examined the deployed experience and
the actual frontend/server execution. The user's washer example exposed a real
experience gap: truthful first-check semantics still did not provide a coherent
end-to-end demonstration. Merely renaming Complete was insufficient.

| ID | Priority | Observed problem | Implemented correction and evidence |
| --- | --- | --- | --- |
| B16 | Critical | A single Run stopped at the first missing test; reaching an answer required repeated manual release/run actions. | Find the answer chains the existing verified authored releases and actual independent comparisons. A new real slow-cranking run completed four stages from one click; all eight lane outcomes matched their expected status, target and path. |
| B17 | High | Early completion and durable-save bookkeeping rendered as duplicate terminal results. | Key execution displays one final result per lane. Early metrics remain immediate; All events/download retain the original events. JavaScript and browser regressions verify this distinction. |
| B18 | High | The final customer/technician answer was subordinate to metrics and a next-check action. | A prominent overall source-backed answer distinguishes agreement, disagreement, insufficient evidence and explicit model/operational failure. No answer-generating call or oracle-derived conclusion was added. |
| B19 | High | The ending view could obscure the actual final path and terminal finding. | Answer route fits all actual path nodes at readable scale, including cross-procedure paths, and highlights the returned cause/handoff. Every displayed node/edge is checked against actual returned graph events; wider context remains available. |
| B20 | Medium | An accidental alphabetical first case and evaluator controls made the demo harder to understand. | Explicit featured washer example, single main action, collapsed stage history and manual-mode control within the existing closed disclosure. No new explanatory wall or removal of inspection controls. |
| B21 | High | Automatic release could contaminate edited input, hide earlier failures or turn a handoff into a diagnosis. | Only unchanged curated journeys advance. Aggregate metrics retain all attempts/mismatches and unknown cost. Edited inputs, disagreements, pause/resume and a genuine unresolved lean handoff have separate deterministic UI coverage. |
| B22 | High | Failures during a chained example could look like success or trigger invisible repeated paid work. | Admission/release/model/save fault injection verifies visible stops, input unlocking and no automatic retry/release. Interrupted persistence disables download and marks incomplete accounting; rejected admission does not invent unknown usage. The overall error identifies the failed lane and its actual error. |
| B23 | High | Actual local and revision-15 washer runs stopped because Sol included a Procedure ENTRY_POINT edge in its diagnostic answer path. The validator correctly rejected it, but the answer error was not returned to Sol as query errors already were. | Feed structural validation errors and the untouched rejected answer back to Sol within its existing five-turn budget. Emit a visible rejection event, preserve call costs and accept only Sol's newly validated answer. Tests cover entry prefixes, invented edges/targets, exhausted budgets and provider failures. The controller does not silently trim paths or relax validation. |

Historical-event UI replay covers the seven additional main problem families,
complete source answers, actual final route geometry, cumulative independent
metrics, desktop/mobile and raw downloads. The warm-vents initial MD1 mismatch
is retained in the total and stage history. Lean handoff replay uses the earlier
independent-workflow recorded events and does not claim new inference.
The live slow-cranking proof is separate from those replays.

The first real one-click washer test stopped because Sol included ENTRY_POINT
in a path whose contract requires a published entry Condition as the start.
That actual model validation failure is retained in
`results/local/interactive/8e8c52b117f349bdb1a7ebe094909d23.json`.
It was not repaired by deleting an edge, changing the corpus, adding hidden
retries, borrowing MD1's answer or relabelling the model as successful.
The subsequent deployed revision-15 attempt reproduced the same contract
failure and is retained separately in `results/cloud/full-demo-washers`.
B23 addresses the missing validation-feedback step rather than repeatedly
rerunning the same failing workflow. It intentionally refines the Sol workflow;
historical costs/accuracy are not claimed to measure this refined policy.
This review improves the demo's orchestration and presentation; it does not
establish that either stochastic model always returns a valid or exact answer.

### Final release evidence

Revision 16 is healthy at 100% traffic. A new actual production washer run
completed from one click through four stages, with all eight lane outcomes exact,
both full eight-hop diagnostic paths ending at the highlighted pump RootCause,
the overall source-backed answer, stage history, retained raw events and
desktop/mobile geometry verified. Evidence:
`results/cloud/full-demo-washers-validated`. This run needed no validation
correction; correction behavior is established by deterministic invalid-prefix,
invented-edge/target, exhausted-budget, provider-failure and visible-rejection
tests, not a claim that real Sol self-corrected in this particular run.

A separate actual production browser check verified MD1 metrics before Sol
finished, frozen timers, independent inputs/costs, real AGE provenance and exact
raw downloads (`results/cloud/full-demo-strict-validated`). The final backend
passed 159 integrated Python tests and eighteen JavaScript tests; seven-family,
lean-handoff and pause/resume historical-event regressions passed separately.
B16-B23 are implemented and released without corpus, oracle, model, access or
budget changes. Operational failures still stop explicitly, while structural
Sol feedback uses only the existing bounded conversation.
