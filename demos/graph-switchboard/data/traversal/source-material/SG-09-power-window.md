# SG-09: One power window does not move

Version: 1.0. Fictional, non-expert-validated record review only, not physical
window, door, electrical or repair instructions. Use current-job evidence;
missing checks are next actions and incomplete/conflicting supplied checks
require clarification. Never turn a disabled feature into a component fault.

## G9.0 Scope

Fictional 2023 Brand X Model F, turbo-petrol only.

## G9.1 Entry: One door window fails to move when requested

Use for a single electrically operated door window that does not move under
its switch request. Other windows may work. This guide does not cover a noisy
but moving window, a broken glass pane or all vehicle electrics being dead.
Next: G9.2

## G9.2 Action: Review the window permission and inhibition record

State: One electrically operated door window does not move under a request.
Type: boolean
Response: Confirm the workshop record shows window operation was permitted, rather than intentionally inhibited, before diagnosing a part.

| Outcome | Destination | Rule | Selection criteria |
| --- | --- | --- | --- |
| window movement permitted | G9.3 | {"operator":"eq","value":true} | Current-job report explicitly verifies valid operation permission with the window-lock/inhibition feature inactive. |
| window movement intentionally inhibited | G9.6 | {"operator":"eq","value":false} | Completed current-job record verifies an active operation-inhibition feature; no component cause is established. |

## G9.3 Action: Review local-switch and master-switch command records

State: Operation is permitted but the affected window does not move as expected.
Type: categorical
Response: Compare the recorded local and master switch requests to determine the next supported check.

Both command paths and their observed movement results must be reported for
the same affected window and job, with connection checks recorded as passed.

| Outcome | Destination | Rule | Selection criteria |
| --- | --- | --- | --- |
| local command absent but master command moves window | G9.4 | {"operator":"eq","value":"local command absent but master command moves window"} | Complete current records show no valid local command, a valid master command and normal movement from master, with connection checks passed. |
| both commands valid but window stationary | G9.5 | {"operator":"eq","value":"both commands valid but window stationary"} | Both current command paths are valid yet the same window remains stationary; no motor fault is implied without the next assessment. |
| complete command records show another pattern | G9.6 | {"operator":"eq","value":"complete command records show another pattern"} | Complete applicable command and movement records show neither supported pattern. |

## G9.4 Action: Review the local-switch-only comparison

State: The master request moves the window but the local switch produces no command.
Type: categorical
Response: Review the complete local-switch comparison before concluding the customer's door switch has failed.

Same job: A original local switch gives no command or movement. B reference
local switch gives a valid command and movement. A2 original switch restores
no command and no movement. Master operation, permission, connections, motor
and mechanism are verified unchanged; only the local switch changes.

| Outcome | Destination | Rule | Selection criteria |
| --- | --- | --- | --- |
| repeatable local-switch-only failure | G9.7 | {"operator":"eq","value":"repeatable local-switch-only failure"} | All current A-B-A2 command/movement observations and unchanged-variable controls above are supplied. |
| complete switch comparison does not localise | G9.6 | {"operator":"eq","value":"complete switch comparison does not localise"} | All controls and observations are complete but the required pattern does not recur. |

## G9.5 Action: Review the independent window motor and mechanism assessment

State: Both switch command paths are valid but the window remains stationary.
Type: categorical
Response: Review the independent motor and mechanism report; valid switch commands alone do not establish a motor fault.

| Outcome | Destination | Rule | Selection criteria |
| --- | --- | --- | --- |
| supplied motor affirmatively isolated with mechanism free | G9.8 | {"operator":"eq","value":"supplied motor affirmatively isolated with mechanism free"} | Complete current independent report verifies supply/ground, valid commands, a free mechanism and an affirmatively isolated failed motor assessment. |
| complete motor assessment does not localise | G9.6 | {"operator":"eq","value":"complete motor assessment does not localise"} | All independent assessment fields are present but a motor fault is not isolated. |

## G9.6 Handoff: Refer the window records for workshop review

State: No supported window component finding is established from these records.
Type: observation
Response: No window component fault is established. Give the technician the permission, command and movement records, including any active inhibition.

## G9.7 RootCause: Local window switch fault isolated by the controlled comparison

Requires valid permission, master-only movement and the complete local-switch-only
comparison in G9.4.
Response: The current records isolate the affected door's local window switch; the master control, motor and mechanism remained functional in the comparison.

## G9.8 RootCause: Window motor fault independently isolated

Requires the complete affirmative independent motor/permission/command/supply
and free-mechanism assessment, not just absent window movement.
Response: The workshop assessment isolates the affected window motor, with valid switch commands and a verified free mechanism.
