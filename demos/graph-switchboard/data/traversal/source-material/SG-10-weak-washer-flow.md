# SG-10: Weak windscreen-washer flow

Version: 1.0. Fictional, non-expert-validated record review only. No fluid,
pressure, electrical, substitution, disassembly or repair work is instructed.
Use the same current job. Missing checks are next actions; partial/conflicting
supplied records require clarification. Do not diagnose from pump sound alone.

## G10.0 Scope

Fictional 2024 Brand X Model G, petrol only.

## G10.1 Entry: Windscreen-washer jets dribble despite a wash request

Use for weak windscreen-washer fluid delivery, even if a pump sound is reported.
This is not a wiper-motion or rain-sensor complaint. No component is proven by
the customer reporting a noise.
Next: G10.2

## G10.2 Action: Review the recorded washer-fluid supply check

State: Windscreen-washer fluid delivery is weak under a wash request.
Type: boolean
Response: Check the current workshop fluid-supply record before interpreting the pump or line tests.

| Outcome | Destination | Rule | Selection criteria |
| --- | --- | --- | --- |
| fluid supply verified adequate | G10.3 | {"operator":"eq","value":true} | Current completed report verifies adequate applicable fluid supply without a frozen or empty reservoir condition. |
| fluid supply not adequate | G10.6 | {"operator":"eq","value":false} | Current completed report explicitly identifies an inadequate or unavailable supply; no pump cause is established. |

## G10.3 Action: Review the washer line-and-jet restriction report

State: Fluid supply is adequate but washer delivery remains weak.
Type: categorical
Response: Review the line-and-jet restriction report before attributing the complaint to pump output.

| Outcome | Destination | Rule | Selection criteria |
| --- | --- | --- | --- |
| line and jet path verified unrestricted | G10.4 | {"operator":"eq","value":"line and jet path verified unrestricted"} | Complete current report explicitly verifies the delivery line and jets are unrestricted and connections intact. |
| delivery-path restriction recorded | G10.6 | {"operator":"eq","value":"delivery-path restriction recorded"} | Complete report records a delivery-path restriction; this guide does not infer pump failure. |

## G10.4 Action: Review the current washer-pump output-pressure report

State: Supply is adequate and the delivery path is independently unrestricted.
Type: numeric
Unit: bar
Response: Review the workshop's declared pump-output pressure; an audible pump is not proof of adequate output.

The fictional applicable cutoff is 0.8 bar inclusive on the adequate branch.
The completed current-job output-pressure record must declare bar and confirm
the documented supply and unrestricted-path prerequisites.

| Outcome | Destination | Rule | Selection criteria |
| --- | --- | --- | --- |
| pump output below 0.8 bar | G10.5 | {"operator":"lt","threshold":0.8,"unit":"bar"} | Completed applicable current pump-output pressure is below 0.8 bar with all prerequisites verified. |
| pump output at least 0.8 bar | G10.6 | {"operator":"gte","threshold":0.8,"unit":"bar"} | Completed applicable current pump-output pressure is at least 0.8 bar; no supported pump cause is established. |

## G10.5 Action: Review the washer-pump-only comparison

State: Pump-output pressure is below the source cutoff with valid supply and path.
Type: categorical
Response: Review the pump-only comparison and original-pump return result before providing a component answer.

Current job: A original pump gives weak delivery and output below 0.8 bar.
B reference pump gives normal delivery and output at least 0.8 bar.
A2 original pump restores weak delivery and below-cutoff output.
Fluid, delivery path, electrical supply/ground and request remain verified and
unchanged; only the pump changes. All conditions must be explicitly recorded.

| Outcome | Destination | Rule | Selection criteria |
| --- | --- | --- | --- |
| repeatable washer-pump-only weak output | G10.7 | {"operator":"eq","value":"repeatable washer-pump-only weak output"} | Complete current A-B-A2 delivery/pressure observations and all unchanged-variable controls above are supplied. |
| complete pump comparison does not localise | G10.6 | {"operator":"eq","value":"complete pump comparison does not localise"} | The complete valid comparison is supplied but the required pattern does not recur. |

## G10.6 Handoff: Refer unresolved washer delivery for workshop review

State: A supported washer-pump finding is not established.
Type: observation
Response: The records do not establish a washer-pump fault. Give the technician the supply, restriction and pressure findings for the next investigation.

## G10.7 RootCause: Washer-pump output fault isolated by the controlled comparison

Requires adequate fluid, an unrestricted delivery path, applicable low output
pressure and the complete controlled pump-only original/reference/return record.
Response: The recorded checks isolate weak output from the original washer pump, rather than an empty reservoir or blocked delivery path.
