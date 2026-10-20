# SG-03: Missing cabin airflow or missing fan speeds

Version: 1.0, synthetic demonstration source material.

## G3.0 Applicability, provenance and limits

Applies only to the fictional 2021 Brand X Model A, petrol configuration.
This is AI-authored demonstration material, not manufacturer guidance or
expert-validated diagnostic advice. It describes reviewing fictional records,
not instructions for electrical testing, substitution, disassembly or repair.

This is a versioned source for the v4 demonstration graph. Published status
means approved for the fictional demo only, not approved vehicle guidance.
Source references use document ID, version and section. There are no
probabilities or claims that the most common failure is the correct one.

Use records for the declared job and complaint episode. An old invoice,
parts suggestion or another vehicle's result is not current diagnostic
evidence. Missing and inconclusive observations are not passed checks.

## G3.1 Entry and scope distinction

Use this guide when the complaint concerns air not leaving the cabin vents,
or airflow missing at one or more fan stages. A customer may call this
"the air-con has stopped", "the heater is dead" or "it only works flat out".
Those phrases do not establish a component fault.

If it is unclear whether the complaint is missing airflow or the temperature
of air that is flowing normally, ask that question before claiming an entry.
This guide does not diagnose refrigerant, heating or cooling performance.

## G3.2 Review the fan-stage record

The first action is to review the current workshop record of airflow at the
four commanded fan stages. The customer complaint can identify the relevant
guide, but it does not substitute for this workshop observation.

| Current workshop record | Permitted transition |
| --- | --- |
| No airflow at stages 1, 2 and 3; airflow present at stage 4 | Continue to the low-speed control comparison in G3.3 |
| No airflow at any stage | Request workshop review of complete airflow loss; no component cause is established |
| Airflow is present at every stage and the remaining complaint is air temperature | Refer outside this airflow procedure; no component diagnosis is established |
| Another complete speed pattern | Request workshop review of a pattern not covered by this guide |
| No workshop stage record exists or the check was not done | Stop with the fan-stage record review as the next action |
| A supplied stage record is partial or internally contradictory | Clarify at this action |

A successful stage 4 is not proof that the low-speed controller has failed.
An all-stages airflow record is not proof that the customer's temperature
complaint has no cause.

## G3.3 Review the low-speed control comparison

The next action is to review the workshop's completed controlled comparison.
For the fictional reference procedure CP-FAN, an interpretable record states:

- It concerns the same current job and reproduced fan-stage pattern.
- The workshop's supply, ground and connection-integrity checks met CP-FAN
  requirements throughout the comparison.
- The low-speed control unit was the only changed diagnostic variable.
- A: with the original unit, stages 1-3 have no airflow and stage 4 has airflow.
- B: with the reference unit, airflow is present at all four stages.
- A2: with the original unit restored, the original 1-3/4 pattern recurs.

CP-FAN is a fictional record-review protocol, not an electrical procedure.
This document supplies no real test limits or physical test instructions.
A report can state that its protocol checks passed; a model must not invent
that statement or infer it solely from the fan-stage pattern.

| Recorded result | Permitted transition |
| --- | --- |
| The complete comparison meets all criteria above | Terminal finding in G3.4 |
| A complete, otherwise valid comparison does not reproduce the A-B-A2 pattern | Request workshop review of unresolved low-speed airflow loss |
| The comparison was not done or no comparison record has been supplied | Leave this comparison-record review as the next action |
| A comparison is supplied but the return check, protocol prerequisites or another required observation is missing | Clarify at this action |
| Observations or the identity of the changed unit conflict | Clarify at this action |

Do not name a failed unit from B alone. The return comparison prevents a
single coincidental improvement from becoming the terminal conclusion.

## G3.4 Permitted terminal finding

The supported terminal finding is a fault in the original low-speed fan control unit,
established by the complete comparison in G3.3.
Do not broaden this to a failed fan motor, switch, wiring harness or cooling
system, and do not prescribe a replacement.
