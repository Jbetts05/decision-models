# SG-07: Temperature rises at idle

Version: 1.0. Fictional, non-expert-validated review of recorded workshop evidence.
No instructions to operate a hot engine, open a cooling system, bypass a relay,
perform electrical work or repair a vehicle are supplied.
Missing checks are next actions; incomplete or conflicting supplied checks
require clarification. Only the same current job and episode are applicable.

## G7.0 Scope

Fictional 2022 Brand X Model D, turbo-petrol only.

## G7.1 Entry: Reported engine temperature rises in stationary traffic

Use for a current temperature-rise complaint in traffic or at idle that
subsides while moving. Do not confuse engine temperature with cabin heating
or the temperature of air leaving cabin vents. No fault is proven by the complaint.
Next: G7.2

## G7.2 Action: Review the recorded cooling-fan command and response

State: A temperature-rise complaint occurs at idle or in traffic.
Type: categorical
Response: The technician needs the current fan-command and fan-response record before this complaint can be localised.

The complete record must describe both commanded state and actual fan operation
during the same reproduced temperature-rise episode.

| Outcome | Destination | Rule | Selection criteria |
| --- | --- | --- | --- |
| fan commanded on but stationary | G7.3 | {"operator":"eq","value":"fan commanded on but stationary"} | Complete current episode records show an on command but no fan rotation. |
| fan operates when commanded | G7.5 | {"operator":"eq","value":"fan operates when commanded"} | Current episode records explicitly show commanded fan operation; this guide does not infer another cooling-system cause. |

## G7.3 Action: Review the cooling-fan supply and motor assessment

State: The fan was stationary despite a current on command.
Type: categorical
Response: Review whether the workshop isolated the supply path or the motor; a stationary fan alone proves neither.

The completed assessment must include the demand, connection/ground checks and
independent motor assessment. This document provides no physical test method.

| Outcome | Destination | Rule | Selection criteria |
| --- | --- | --- | --- |
| relay output absent and motor independently passes | G7.4 | {"operator":"eq","value":"relay output absent and motor independently passes"} | The complete same-job report verifies demand and connections/ground, absent relay output and an independently passing motor assessment. |
| supplied motor affirmatively isolated as failed | G7.7 | {"operator":"eq","value":"supplied motor affirmatively isolated as failed"} | The complete same-job report verifies the required motor supply/ground and explicitly independently isolates failed motor operation under the recorded command. |
| complete assessment does not localise | G7.5 | {"operator":"eq","value":"complete assessment does not localise"} | All assessment fields are supplied but neither affirmative localisation criterion is met. |

## G7.4 Action: Review the relay-only cooling-fan comparison

State: Relay output is absent and the independent motor assessment passes.
Type: categorical
Response: Review the relay-only comparison, including the original relay's return result, before naming a relay fault.

Current job: A original relay gives no fan operation under a verified command.
B reference relay gives fan operation. A2 original relay gives no fan operation
again. Command, supply, motor, connections and ground pass and remain unchanged
throughout; only the relay changes. All prerequisites must be explicit.

| Outcome | Destination | Rule | Selection criteria |
| --- | --- | --- | --- |
| repeatable relay-only fan failure | G7.6 | {"operator":"eq","value":"repeatable relay-only fan failure"} | Complete same-job relay-only A-B-A2 and all unchanged-variable prerequisites above are supplied. |
| complete relay comparison does not localise | G7.5 | {"operator":"eq","value":"complete relay comparison does not localise"} | The complete valid comparison is supplied but the required pattern does not recur. |

## G7.5 Handoff: Refer the unresolved temperature rise for workshop investigation

State: The supplied records do not isolate a cause within this fan procedure.
Type: observation
Response: The current records do not establish a cooling-fan component fault. Return the documented findings to the technician for further investigation.

## G7.6 RootCause: Cooling-fan relay fault isolated by the controlled comparison

Requires the complete command/response, supply/motor assessment and relay-only
original/reference/return comparison above.
Response: The recorded checks isolate the cooling-fan relay as the cause of the missing commanded fan operation during the temperature-rise episode.

## G7.7 RootCause: Cooling-fan motor fault independently isolated

Requires the complete affirmative supplied-motor assessment in G7.3. A stationary
fan or an absent relay output alone never establishes this finding.
Response: The workshop's complete independent assessment isolates the cooling-fan motor, rather than the relay or a guessed cooling-system component.
