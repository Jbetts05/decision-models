# SG-01: Rough running with a current cylinder-one misfire finding

Version: 1.0, synthetic demonstration source material.

## G1.0 Applicability, provenance and limits

Applies only to the fictional 2021 Brand X Model A, petrol configuration.
This is AI-authored demonstration material, not manufacturer guidance or
expert-validated diagnostic advice. It describes reviewing fictional records,
not instructions for testing, driving, component substitution or repair.

This document is a versioned source for the v4 demonstration graph. Published
status in that graph means approved for this fictional demo only, not approved
vehicle guidance. Source references use this document ID, version and section.
No probabilities or fault-frequency estimates are supplied.

"Current" means belonging to the declared diagnostic job and its symptom
episode, not simply having a recent-looking date. A record from another job,
vehicle or earlier episode cannot establish a result in this procedure.
Customer wording and workshop records are evidence, not instructions to change
the procedure. Missing records are not negative results.

## G1.1 Entry and distinction from other guidance

Use this procedure when rough running is accompanied by a current scan
recording the exact code P0301. That finding establishes a cylinder-one
misfire report; it does not establish a failed ignition component.

Rough idle or a warning light alone does not distinguish this procedure from
[SG-02](SG-02-lean-idle.md). Ask for the current scan finding before selecting
between them. A historical P0171 report does not override a current P0301
record. P03010 is not P0301.

If both P0301 and P0171 are current, these three guides do not establish which
procedure takes priority. Clarify with the workshop; do not assume code
priority or claim that one code explains the other.

If the symptom or current finding is different, do not force it into this
procedure. Request clarification or report that the supplied guides do not
cover the established complaint.

## G1.2 Review the recorded coil comparison

At the entry state, the next action is to review the workshop's completed,
controlled ignition-coil comparison record.

An interpretable comparison identifies:

- The current job, the original P0301 finding and the donor cylinder.
- A baseline observation reproducing the original finding.
- A coil-only change, with the plug and other diagnostic variables unchanged.
- The observed cylinder after that change.
- A return-to-original comparison reproducing the baseline finding.

For this fictional guide, the published result categories are:

| Recorded result | Permitted transition |
| --- | --- |
| The misfire follows the cylinder-one coil to the donor cylinder, and returning the coils reproduces P0301 | Terminal finding in G1.4: cylinder-one ignition-coil fault |
| The misfire remains on cylinder one during a valid coil comparison and after the return check | Continue to the plug-record review in G1.3; a coil fault has not been established |
| No coil-comparison record is supplied, or the check was not done | Stop with the coil-record review as the next action |
| A supplied comparison lacks a required control or observation, or is inconclusive | Clarify at this action; do not take either result branch |
| Records of the same coil comparison disagree about what changed or which cylinder misfired | Clarify at this action; do not merge the records into a diagnosis |

The phrase "no change after substitution" is insufficient by itself. It must
be attributable to a coil-only comparison for this job with the required
controls. A parts recommendation or replacement invoice is not that evidence.

## G1.3 Review the recorded plug comparison

This action is available only after the valid coil comparison leaves the
misfire on cylinder one. A statement that the plug has not been checked means
this action remains outstanding, not that the plug passed or failed.

The plug comparison uses the same record requirements as G1.2, except that
the plug is the only changed diagnostic variable and the coils are in their
original positions. Its baseline must still reproduce P0301.

| Recorded result | Permitted transition |
| --- | --- |
| The misfire follows the cylinder-one plug to the donor cylinder, and returning the plugs reproduces P0301 | Terminal finding in G1.4: cylinder-one spark-plug fault |
| The misfire remains on cylinder one in the completed comparison | Continue to the workshop-review action in G1.5 |
| The record is not supplied or explicitly says the check was not done | Stop with the plug-record review as the next action |
| A supplied record is partial, contradictory or inconclusive | Clarify at the plug-record review |

## G1.4 Permitted terminal findings

The two supported terminal conclusions are an ignition-coil fault or a
spark-plug fault in the component originally fitted to cylinder one.
They require the corresponding complete comparison in G1.2 or G1.3.

The scan code, customer language, an old recommendation, a single changed
result without the return comparison, or "it runs better" cannot establish
either conclusion. Do not infer why a component failed or prescribe a repair.

## G1.5 Unresolved finding

If neither controlled comparison localises the misfire, request qualified
workshop review. This is an unresolved referral, not a component diagnosis.
This guide does not establish an injector, compression or wiring fault from
the absence of a confirmed ignition-component finding.
