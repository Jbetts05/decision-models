# SG-02: Rough idle with a current lean-mixture finding

Version: 1.0, synthetic demonstration source material.

## G2.0 Applicability, provenance and limits

Applies only to the fictional 2021 Brand X Model A, petrol configuration.
This is AI-authored demonstration material, not manufacturer guidance or
expert-validated diagnostic advice. All reference bands and comparison
criteria below are invented for this dataset. Do not use them on a vehicle.
Actions mean reviewing supplied fictional workshop records, not performing
measurements, isolation, driving or repair.

This is a versioned source for the v4 demonstration graph. Published status
means approved for the fictional demo only, not approved vehicle guidance.
Source references use document ID, version and section. No fault frequencies,
diagnostic probabilities or optimal-test claims are supplied.

"Current" refers to the declared job and complaint episode. A measurement
must also match the profile requested by the action. An old or engine-off
measurement cannot substitute for a current running-idle record. Missing,
contradictory or inconclusive evidence does not establish a result.

## G2.1 Entry and distinction from other guidance

Use this procedure for rough idle accompanied by a current scan recording
the exact code P0171. The code establishes a reported lean-mixture finding,
not a fuel-pump fault or an air leak.

The driver may describe the same rough idle or warning light as in
[SG-01](SG-01-cylinder-misfire.md). Use current findings to distinguish them.
Historical codes must not determine current applicability.
If the current scan is absent, ask for it. If P0301 and P0171 are both current,
clarify which published procedure the workshop intends to pursue; these
guides supply no priority rule.

## G2.2 Review the current pressure record

The next action is to review the saved workshop pressure record for profile
RP-IDLE: the current complaint reproduced at running idle for the declared
job. A valid record identifies that profile, the job, the value and the unit.

For this fictional profile only, the reference band is 250 through 400 kPa,
including both boundaries. The documented unit conversion is 1 bar = 100 kPa;
therefore a correctly scoped 3.1 bar record means 310 kPa.
Do not invent a unit for "3.1" or apply an undocumented conversion.

| Recorded result | Permitted transition |
| --- | --- |
| A complete current RP-IDLE record is inside the inclusive band | Continue to the localisation-record review in G2.3 |
| A complete current RP-IDLE record is outside the band | Request workshop review of the out-of-band pressure finding; no component cause is established |
| No pressure record has been supplied or the check was not done | Stop with this pressure-record review as the next action |
| A supplied record lacks the unit or profile, or equally applicable records conflict | Clarify at this action |

An old low reading, a crossed-out value or a measurement taken in a different
operating profile does not override the applicable RP-IDLE record. Conversely,
do not discard two conflicting applicable records merely by choosing the
more convenient value. Ask the workshop to resolve the conflict.

Being inside the reference band does not prove that the vehicle has no fault.
It only permits the next published action in this guide.

## G2.3 Review the controlled localisation record

This action is available after the current pressure record is within band.
It reviews the workshop's controlled record for the designated intake joint J.
Joint J is a named location in this procedure, not a general component
taxonomy or a physical-topology subgraph.

A complete record identifies the same job, the same reproduced complaint
and profile RP-IDLE, no other diagnostic changes, and all four observations:

| Observation | Fictional criterion |
| --- | --- |
| A: original configuration | Recorded correction exceeds +15% |
| B: joint J isolated in the workshop comparison | Recorded correction is between -5% and +5%, inclusive |
| A2: original configuration restored | Recorded correction again exceeds +15% |
| C: comparison control at joint K, with J in its original configuration | Recorded correction exceeds +15% |

Here "correction" is the percentage field explicitly identified in the
workshop report. These invented bands define only this source's category.
Do not substitute a different percentage field, operating profile or job.

If all four criteria are met and pressure remains within its reference band
throughout the comparison, take the repeatable-localisation result to G2.4.
A separately signed pressure-stability statement for the comparison is
acceptable; pressure values need not be repeated in every row.

If the completed, otherwise valid record fails to reproduce the pattern,
take the non-localising result to the workshop-review action in G2.5.
If a required observation or control is missing, the supplied record is
incomplete: clarify at this action rather than treating it as non-localising.
If the record explicitly says the entire comparison was not done, leave this
review as the next action.

A single improvement in B is not enough. In particular, a low correction
that remains low after restoring A does not localise the fault to J.

## G2.4 Permitted terminal finding

The only terminal finding in this guide is an unmetered-air leak at intake
joint J established by the complete repeatable-localisation pattern in G2.3.
No component finding follows from P0171 or an in-band pressure value alone.
Do not infer a replacement, repair method or broader engine diagnosis.

## G2.5 Unresolved or out-of-band finding

Request qualified workshop review if pressure is out of band or the complete
localisation record does not reproduce the required pattern. These are
distinct referrals, not component diagnoses.
An out-of-band pressure value does not identify a fuel pump or regulator.
A non-localising comparison does not identify another air leak.
