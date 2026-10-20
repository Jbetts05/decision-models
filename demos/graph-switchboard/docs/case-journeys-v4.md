# Three source-grounded case journeys

Status: implemented as a reproducible v4 graph and staged application journeys.
Fictional demonstration material, not expert-validated guidance.

Implementation update: v4.1.1 preserves these original journeys and adds
source-scheduled variants for ten vehicles. The `md1-entry-v1` workflow uses
selected vehicle fields for fixed AGE entry retrieval, then MD1 selects the
entry and subsequent branches. There is no Sol intake in that lane; Sol-only
independently generates Cypher from the same original input. This architecture
change does not alter the source rules or expected outcomes below.

V4.1.2 removes generated customer-release prefixes from cumulative model input.
The customer quotes and workshop records below are unchanged; stage labels
remain authoring/UI metadata, not injected customer speech. V4.1.1 model scores
remain historical results for that version's inputs.

## Purpose and scope

Build a focused demonstration of Microsoft-Decision-1 versus Sol-only:
both must locate relevant troubleshooting guidance and use imperfect human
records to advance only along source-supported diagnostic paths.
There is no additional retrieval-method comparison in this pack.

The three source guides are:

| Guide | Scope | Source |
| --- | --- | --- |
| SG-01 | Current cylinder-one misfire with rough running | [Guide](../data/traversal/source-material/SG-01-cylinder-misfire.md) |
| SG-02 | Current lean-mixture finding with rough idle | [Guide](../data/traversal/source-material/SG-02-lean-idle.md) |
| SG-03 | Missing cabin airflow or missing fan stages | [Guide](../data/traversal/source-material/SG-03-cabin-airflow.md) |

These are AI-authored, fictional source documents. They have not been
validated by an automotive expert and must not be represented as manufacturer
guidance. Numeric bands and controlled-comparison criteria are synthetic.
The actions describe reviewing workshop records, not performing vehicle work.

The application derives its v4 graph and evidence snapshots from these sources.
Published status is approval for this synthetic demo only. Deployment status is
documented separately in the README; model-performance claims require actual runs.

## Evidence and comparison contract

Each journey is a separate fictional job for the same supported model:
2021 Brand X Model A, petrol. The app supplies that visible job-card context;
it is not a hidden fixture hint. Jobs are not combined into one vehicle history.
"Current" means the declared job and complaint episode, not the date on which
someone happens to run the demo.

For each turn, the model-visible input is the shared job-card context, the
customer question and only the records released so far. Preserve original
wording, record labels and dates; do not prelabel observations with action
names, result categories, procedure IDs or expected diagnoses.

The **reviewer notes are not model input**. They state expected outcomes,
source references and the significance of each release. They are not
instructions to the runtime or a substitute for actual graph retrieval.

Both lanes receive the same frozen evidence at the same release point, but
run independently. Neither may see later turns, reuse the other lane's
selection or receive the expected path. An operator advances the evidence
release; a model's guessed route must not trigger a future record.
An unseen record is not a failed or passed test.

Sol-only may retrieve enough published graph context in one query to answer.
It must not be forced through one query or call per hop. The MD1 lane may
retrieve its currently valid candidates and use MD1 to select supported
results. Neither lane is required to use a model for every mandatory edge.
Both must stop when the next record is unavailable or a supplied one cannot
support a result.

Source guides define diagnostic rules, not model confidence scores.
Application session state holds records, their chronology and interpretations;
the graph holds versioned procedural paths with source references. Preserve
the five original entity and relationship types. Do not invent fault
probabilities, repairs, physical topology or a new ontology to make a case
harder.

### Derivation notes, reviewer only

The source guides deliberately contain no graph-type annotations or expected
case answers. Their ordinary procedure text is the material to be extracted.
These notes belong to the review pack, not to ingestion input.

Each guide becomes a versioned Procedure, linked by APPLIES_TO to the one
VehicleModel and by ENTRY_POINT to its supported starting Condition.
Record reviews become Actions. Observed outcomes belong on RESULT edges;
intermediate Conditions lead through NEXT_ACTION to the next review.
Retain the complete source criteria on each relevant result, not just a
"confirmed" label. Only source-supported component conclusions become
RootCause nodes. Referrals remain Actions. No INDICATES edge is required
unless a source actually supplies a direct condition-to-cause conclusion.

The intended flagship outcomes are deliberately not all diagnoses:

| Journey | Final outcome |
| --- | --- |
| 1 | A component finding supported by a controlled comparison |
| 2 | A complete but non-localising record requiring workshop referral |
| 3 | A component finding after resolving customer terminology and incomplete evidence |

## Journey 1: "The light came back"

### Visible job-card context

Job DEMO-01, opened 12 October 2026.
Vehicle: 2021 Brand X Model A, petrol.

### Turn 0: Customer report and old paperwork

Customer:

> The engine light is back and it shakes when I stop at a junction. There is
> old paperwork saying it was running lean. Is this the same thing again?

Attachment, job OLD-77, 2 July 2026:

> P0171 recorded. Further investigation recommended. No completed follow-up
> record attached.

**Reviewer only:** Neither SG-01 nor SG-02 is uniquely established. The
historical finding must not select today's procedure or establish a cause.
Ask for the current scan result. Expected outcome: `clarify`, without a
claimed entry or diagnosis. Sources: G1.1, G2.1.

### Turn 1: Current scan, different finding

Workshop attachment, DEMO-01, 12 October, 09:10:

> Complaint reproduced at idle. Active fault list: P0301.
> P0171 is not on this scan. No component conclusion recorded.

Customer:

> That's today's printout. What should we look at next?

**Reviewer only:** Select SG-01, not the historical lean-mixture route.
The current P0301 Condition supports reviewing the recorded coil comparison.
No coil-comparison record exists yet. Expected outcome: `next_action` at
that review, not a component diagnosis. Sources: G1.1-G1.2.

### Turn 2: "No change" with enough context to interpret it

Workshop note, DEMO-01, 12 October, 09:35:

> P0301 reproduced first. Coil from 1 compared in 2, with the other coil
> exchanged; plugs untouched. Still P0301, no P0302. Original coils back in
> place: P0301 again. No other changes during the comparison.
> Plug comparison not done yet.

Customer:

> So does "no change" mean the coil is the problem?

**Reviewer only:** It does not. The complete coil-only comparison leaves the
misfire on cylinder one. Advance to the published plug-record review and
stop there because the note explicitly says it was not done.
Expected outcome: `next_action`, with no established component cause.
Sources: G1.2-G1.3.

### Turn 3: The conclusion must come from the pattern

Workshop addendum, DEMO-01, 12 October, 10:05:

> Coils in original positions throughout. Baseline: P0301.
> Only the plugs from 1 and 2 exchanged for the comparison: P0302, no P0301.
> Original plug positions restored: P0301, no P0302.
> Same complaint conditions; no other diagnostic changes.

Customer:

> What do these results actually establish?

**Reviewer only:** The fault follows the original cylinder-one plug and
returns with the original configuration. Expected outcome: `root_cause`,
cylinder-one spark-plug fault, supported by G1.3-G1.4.
Do not infer a cracked plug, an injector fault or a repair recommendation.
The input deliberately does not say "plug fault confirmed".

### Contrast: Both current codes

Replace only the active fault list at Turn 1 with:

> Active fault list: P0301 and P0171. No procedure priority recorded.

Both later comparisons remain unreleased. Expected outcome: `clarify` about
procedure priority, not a confident SG-01 or SG-02 selection. The source
guides explicitly supply no priority between coexisting current findings.
Sources: G1.1, G2.1.

**Business point:** Prevent an old diagnosis or a misunderstood workshop
phrase from driving the current case; support a conclusion only when the
recorded evidence actually localises it.

## Journey 2: "It smooths out when the revs come up"

### Visible job-card context

Job DEMO-02, opened 13 October 2026.
Vehicle: 2021 Brand X Model A, petrol.

### Turn 0: Relevant case, incomplete measurement

Customer:

> It shakes at idle but seems smoother when the revs come up. The garage
> wondered about the fuel pump. Do these notes tell us where to go next?

Attachment, DEMO-02, 13 October, 09:00:

> Current scan: P0171; no P0301.
> RP-IDLE pressure: 3.1 [unit cropped from photograph].

Separate worksheet, job OLD-81, 15 July:

> Key-on pressure: 2.2 bar. Engine not running.

**Reviewer only:** SG-02 is relevant, but "3.1" lacks its unit. The old
key-on value is not a replacement RP-IDLE measurement.
Expected outcome: `clarify` at the pressure-record review. Ask for the
uncropped unit rather than guessing bar, diagnosing a pump or rejecting the
case solely because one historical value is lower. Sources: G2.1-G2.2.

### Turn 1: Unit and operating context become available

Uncropped attachment, DEMO-02, 13 October, 09:00:

> RP-IDLE, complaint reproduced. Pressure 3.1 bar.
> This is the current running-idle record, not the July key-on worksheet.

Customer:

> That's the full picture. Is the fuel-pump suggestion supported?

**Reviewer only:** Under the explicitly documented conversion, this is
310 kPa and inside the inclusive fictional reference band. It supports
continuing to the localisation-record review, not naming a pump or declaring
the car fault-free. No localisation record is supplied yet.
Expected outcome: `next_action`. Sources: G2.2-G2.3.

### Turn 2: An improvement is not yet a diagnosis

Workshop comparison sheet, DEMO-02, 13 October, 09:40:

> RP-IDLE. Same complaint. Pressure remained inside the reference band.
> Correction field, %:
> A, original arrangement: +24.
> B, joint J isolated: +3.
> No other diagnostic change. Return and control observations still pending.

Customer:

> That looks much better. Have they found it?

**Reviewer only:** Not yet. A2 and C are explicitly pending. A-B alone does
not establish the published repeatable-localisation result.
Expected outcome: `clarify` at the localisation review, identifying the two
missing observations rather than inventing them. Sources: G2.3-G2.4.

### Turn 3: The completed record does not support the promising diagnosis

Completed sheet, DEMO-02, 13 October, 10:00:

> Continuation of the same RP-IDLE comparison; no other diagnostic changes.
> A2, original arrangement restored: +4%.
> C, joint K comparison with J left original: +22%.
> Pressure remained inside the reference band for the complete comparison.

Customer:

> How does this change the conclusion?

**Reviewer only:** The required observations are now present, but the
original high correction does not recur in A2. The record is complete and
non-localising, not simply missing a measurement.
Expected outcome: `next_action` at the unresolved-localisation workshop
referral, with no RootCause. Do not keep asking for an already supplied A2,
name a fuel pump, or infer a repair from the persistent improvement.
Sources: G2.3, G2.5.

### Contrast: The original finding returns

At Turn 3, change A2 from +4% to +23%; leave the other facts unchanged.
All four criteria now meet the source rule. Expected outcome: `root_cause`,
unmetered-air leak at intake joint J. Do not ignore the changed observation
and repeat the main journey's referral answer. Sources: G2.3-G2.4.

**Business point:** Distinguish an applicable measurement from historical
paperwork, interpret a stated unit correctly, and recognise when even a
completed investigation does not support a component diagnosis.

## Journey 3: "The air-con only works flat out"

### Visible job-card context

Job DEMO-03, opened 14 October 2026.
Vehicle: 2021 Brand X Model A, petrol.

### Turn 0: Customer vocabulary is not the procedure title

Customer:

> My air-con is dead unless I turn the knob right up. It blows hard at the
> top setting, but one, two and three are silent and nothing comes out.
> Last year's invoice says "resistor advised". Is that what has gone?

Attachment, job OLD-64, 7 December 2025:

> Resistor advised. No controlled comparison record attached.

**Reviewer only:** This is a missing-airflow/fan-stage complaint, not enough
evidence for an air-temperature diagnosis or a failed part. Select SG-03
and request the current workshop fan-stage record.
Expected outcome: `next_action`. The old recommendation establishes no
current result. Sources: G3.0-G3.2.

### Turn 1: Current pattern, still no component conclusion

Workshop note, DEMO-03, 14 October, 11:10:

> Airflow at vents, commanded stages:
> 1: none. 2: none. 3: none. 4: present.
> Air temperature not assessed. No control-unit comparison record yet.

Customer:

> They've reproduced it. Can we name the part now?

**Reviewer only:** Advance through the low-speed pattern Condition to the
control-comparison review. A successful stage 4 is not a component-isolation
test. Expected outcome: `next_action`, not `root_cause`.
Sources: G3.2-G3.3.

### Turn 2: A reference unit improves the result

Workshop note, DEMO-03, 14 October, 11:40:

> CP-FAN supply, ground and connection-integrity checks passed and remained
> satisfied during the comparison. Only the low-speed control unit changed.
> A, original: no airflow at 1/2/3; airflow at 4.
> B, reference unit: airflow at 1/2/3/4.
> Original-unit return comparison not recorded yet.

Customer:

> It works with the other one. Is that conclusive?

**Reviewer only:** The supplied record is incomplete: A2 is missing.
Expected outcome: `clarify` at the comparison review, not a diagnosis
copied from the old invoice. Sources: G3.3-G3.4.

### Turn 3: Original pattern recurs

Workshop addendum, DEMO-03, 14 October, 12:00:

> Same CP-FAN comparison. Original low-speed control unit restored:
> no airflow at 1/2/3; airflow at 4 again.
> No other changes. Protocol prerequisites remained satisfied throughout.

Customer:

> What finding can the completed record support?

**Reviewer only:** The complete A-B-A2 comparison supports the original
low-speed control-unit fault under this fictional source. Expected outcome:
`root_cause`. Do not broaden it to a motor, wiring or cooling-system
diagnosis, or turn the finding into repair instructions.
Sources: G3.3-G3.4.

### Contrast: "Air-con failed" means temperature, not missing airflow

Replace the initial customer report with:

> Air comes out strongly on every setting. It just stays warm when I ask
> for cooling. Is the old resistor advice relevant?

SG-03 does not cover the established temperature-only complaint.
Expected outcome: `unsupported` for diagnostic coverage by this source pack,
not a blower RootCause. If a workshop stage record is later supplied and the
procedure's temperature referral is reached, represent it as a referral
Action with `next_action`, never as a RootCause. Sources: G3.1-G3.2.

**Business point:** Translate the customer's vocabulary into the correct
procedural scope, avoid anchoring on an old parts suggestion, and distinguish
an incomplete improvement from a supported terminal finding.

## Review and later integration boundaries

These are three flagship journeys, each with one small contrast, not a claim
of broad automotive coverage or a statistically representative benchmark.
Reviewer expectations are authored directly from source sections. Neither
model's output establishes ground truth.

Before implementation, review guide rules and journey records together.
Then derive the graph and independent expected paths with source references.
Keep the old live corpus separate until the new graph, staged session support
and UI are actually implemented and verified.

The later comparison should report entry selection, source-supported
continuation, correct clarification/referral, unsupported root-cause claims,
and whole-journey model usage, cost and time. Count actual calls once; do not
claim MD1 benefits on turns where it was not invoked. Render only graph data
actually retrieved during each lane's execution.

The source pack was authored independently of the entry architecture.
The later bounded MD1 entry-selection interface must serve these frozen cases,
not determine or rewrite their expected answers.
