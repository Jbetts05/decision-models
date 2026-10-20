# SG-06: Intermittent charging warning

Version: 1.0. Fictional, non-expert-validated record-review guidance only.
Do not perform electrical, belt, substitution or repair work from this guide.
Use complete current-job records; missing checks are next actions, supplied
partial or conflicting checks require clarification, not a guessed result.

## G6.0 Scope

Fictional 2022 Brand X Model C, petrol only.

## G6.1 Entry: Charging warning appears while the engine is already running

Use for a battery/charging warning during otherwise normal engine running.
Slow rotation before starting and a battery discharged overnight are different
complaints. A warning lamp alone never establishes an alternator fault.
Next: G6.2

## G6.2 Action: Review the recorded charging-drive inspection

State: The charging warning appears during engine running.
Type: boolean
Response: Review the current workshop charging-drive inspection before interpreting the charging-voltage log.

| Outcome | Destination | Rule | Selection criteria |
| --- | --- | --- | --- |
| charging drive verified intact | G6.3 | {"operator":"eq","value":true} | The current-job workshop report explicitly verifies intact drive engagement throughout the reported warning episode. |
| charging drive not intact | G6.5 | {"operator":"eq","value":false} | A completed current-job inspection explicitly reports failed drive engagement; no alternator cause is established. |

## G6.3 Action: Review the warning-episode charging-voltage log

State: Drive engagement was verified during the charging warning.
Type: range
Unit: V
Response: Review charging voltage recorded during the warning, not an old resting battery reading.

The fictional applicable band is 13.6 through 14.8 V inclusive. The same-job
log must cover the warning episode and identify the measurement context.

| Outcome | Destination | Rule | Selection criteria |
| --- | --- | --- | --- |
| charging voltage outside 13.6-14.8 V | G6.4 | {"operator":"outside","minimum":13.6,"maximum":14.8,"unit":"V"} | Completed current warning-episode charging-voltage log has an applicable reading outside the inclusive band. |
| charging voltage inside 13.6-14.8 V | G6.5 | {"operator":"between_inclusive","minimum":13.6,"maximum":14.8,"unit":"V"} | Complete applicable log stays within the inclusive band; do not invent a persistent charging-unit fault. |

## G6.4 Action: Review the charging-unit-only comparison

State: A valid warning-episode log is outside the source band.
Type: categorical
Response: Review the completed charging-unit comparison and return check before providing a component conclusion.

Current-job controls must explicitly confirm unchanged wiring, battery, drive,
load and measurement context. A original unit: charging warning and out-of-band
voltage. B reference unit: no warning and in-band voltage. A2 original unit:
warning and out-of-band voltage recur. All three records are required.

| Outcome | Destination | Rule | Selection criteria |
| --- | --- | --- | --- |
| repeatable charging-unit fault | G6.6 | {"operator":"eq","value":"repeatable charging-unit fault"} | All A-B-A2 warning/voltage observations and unchanged-variable controls above are complete and current. |
| complete charging comparison does not localise | G6.5 | {"operator":"eq","value":"complete charging comparison does not localise"} | The complete controlled comparison is supplied but fails the required repeatable pattern. |

## G6.5 Handoff: Refer the unresolved charging warning to the workshop

State: The current records do not support the published charging-unit finding.
Type: observation
Response: These records do not isolate the charging unit. Give the technician the drive inspection and warning-episode log for further investigation.

## G6.6 RootCause: Original charging-unit fault isolated by the complete comparison

Requires intact drive, an applicable out-of-band voltage log and the complete
controlled charging-unit A-B-A2 pattern in G6.4.
Response: The current records isolate the original charging unit as the source of the warning and abnormal charging voltage.
