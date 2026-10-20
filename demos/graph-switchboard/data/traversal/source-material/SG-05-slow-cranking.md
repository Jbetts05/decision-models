# SG-05: Slow engine cranking

Version: 1.0. Fictional record-review guidance, not manufacturer or expert-validated
advice. No physical testing, electrical work, substitution or repair is instructed.
Only review the supplied workshop records for the current vehicle and job.
Missing records leave a next action; partial, conflicting or wrong-job records
require clarification. Never interpret an incomplete comparison as a negative.

## G5.0 Scope

Fictional 2021 Brand X Model B, petrol only.

## G5.1 Entry: The engine turns unusually slowly before starting

Use for slow starter-driven engine rotation before the engine starts. This is
not uneven running after starting, a no-rotation condition or overnight discharge.
A customer complaint establishes this entry but no component cause.
Next: G5.2

## G5.2 Action: Review the current battery load-voltage record

State: The current complaint concerns slow engine cranking.
Type: numeric
Unit: V
Response: Review the current workshop battery load-voltage report first; slow cranking alone does not identify a failed battery.

The fictional load protocol requires a current-job voltage with a declared V unit.
Exactly 9.5 V is in the adequate-voltage branch. Resting voltage is not load voltage.

| Outcome | Destination | Rule | Selection criteria |
| --- | --- | --- | --- |
| load voltage below 9.5 V | G5.3 | {"operator":"lt","threshold":9.5,"unit":"V"} | Current-job battery LOAD voltage is below 9.5 V, unit declared and protocol completed. |
| load voltage at least 9.5 V | G5.4 | {"operator":"gte","threshold":9.5,"unit":"V"} | Current-job battery LOAD voltage is at least 9.5 V; this does not establish battery failure. |

## G5.3 Action: Review the controlled battery comparison

State: A valid current load-voltage record is below the fictional limit.
Type: categorical
Response: Review the complete battery-only comparison, including the return check; an improvement alone is not a confirmed cause.

The same-job record must confirm unchanged starter, cables, temperature and
test conditions. A: original battery gives slow rotation. B: reference battery
gives normal rotation. A2: original battery restores slow rotation. Only the
battery changes. Missing A2 or control information requires clarification.

| Outcome | Destination | Rule | Selection criteria |
| --- | --- | --- | --- |
| repeatable battery-only improvement | G5.7 | {"operator":"eq","value":"repeatable battery-only improvement"} | All original/reference/return observations and unchanged-condition controls above are explicitly recorded. |
| complete battery comparison does not localise | G5.6 | {"operator":"eq","value":"complete battery comparison does not localise"} | All prerequisites and A-B-A2 observations are supplied but the required repeatable pattern fails. |

## G5.4 Action: Review the current starter return-path voltage-drop record

State: Battery load voltage is at least 9.5 V but cranking remains slow.
Type: numeric
Unit: V
Response: Review the workshop return-path voltage-drop report; the adequate battery reading does not identify a starter fault.

Only the declared current-job cranking return-path drop is applicable.
Exactly 0.3 V belongs to the at-most-0.3 V branch.

| Outcome | Destination | Rule | Selection criteria |
| --- | --- | --- | --- |
| return-path drop exceeds 0.3 V | G5.5 | {"operator":"gt","threshold":0.3,"unit":"V"} | Completed same-job cranking return-path voltage drop exceeds 0.3 V. |
| return-path drop at most 0.3 V | G5.6 | {"operator":"lte","threshold":0.3,"unit":"V"} | Completed same-job cranking return-path voltage drop is 0.3 V or lower; no component is isolated. |

## G5.5 Action: Review the return-connection localisation report

State: The current return-path voltage drop exceeds the fictional limit.
Type: categorical
Response: Review the workshop's connection-localisation evidence before naming a return-path connection fault.

Affirmative localisation requires the same connection, slow cranking reproduced,
an independently recorded high drop across that connection, and normal drops
across the other return-path sections. No repair is prescribed.

| Outcome | Destination | Rule | Selection criteria |
| --- | --- | --- | --- |
| one return connection affirmatively isolated | G5.8 | {"operator":"eq","value":"one return connection affirmatively isolated"} | All independent localisation observations above explicitly identify the same connection in the current job. |
| complete return-path survey does not localise | G5.6 | {"operator":"eq","value":"complete return-path survey does not localise"} | Complete same-job survey is supplied but does not isolate one connection. |

## G5.6 Handoff: Request workshop review of unresolved slow cranking

State: The completed records do not isolate a supported component cause.
Type: observation
Response: The available checks do not establish a component fault. Pass the recorded results to the technician for further slow-cranking investigation.

## G5.7 RootCause: Original battery fault isolated by the controlled comparison

The terminal cause requires the complete low-load-voltage and battery-only
original/reference/return evidence in G5.2 and G5.3.
Response: The recorded comparison isolates the original battery as the cause of the slow cranking. This is a diagnostic finding, not a replacement instruction.

## G5.8 RootCause: Starter return-path connection fault independently localised

The terminal cause requires adequate load voltage, excessive current return-path
drop and the affirmative independent connection survey in G5.5.
Response: The workshop records isolate one starter return-path connection, rather than the battery or starter motor.
