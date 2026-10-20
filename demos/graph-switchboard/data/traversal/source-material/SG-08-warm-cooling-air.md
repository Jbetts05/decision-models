# SG-08: Strong cabin airflow but no cooling

Version: 1.0. Fictional, non-expert-validated record review, not instructions
for refrigerant handling, dismantling, electrical testing or repair.
Use the current vehicle/job only. Missing checks remain next actions;
partial or conflicting supplied records require clarification.

## G8.0 Scope

Fictional 2023 Brand X Model E, petrol only.

## G8.1 Entry: Airflow is strong but the cabin vents remain warm on cooling demand

Use only when airflow is present at all fan settings and the complaint is
insufficient cooling with cooling requested. Missing fan speeds belong to the
airflow guide. Unclear airflow-versus-temperature symptoms require clarification.
Next: G8.2

## G8.2 Action: Review the current cooling-demand vent-temperature report

State: Airflow is present but cooling demand produces reportedly warm air.
Type: numeric
Unit: degC
Response: Review the workshop vent-temperature record under the stated cooling demand; warm air alone does not prove a refrigerant fault.

The fictional record-review cutoff is 12 degC. The report must declare degC,
current-job cooling demand and applicable workshop conditions. Exactly 12 degC
belongs to the at-most-12 degC branch. This is not a real vehicle reference limit.

| Outcome | Destination | Rule | Selection criteria |
| --- | --- | --- | --- |
| vent temperature above 12 degC | G8.3 | {"operator":"gt","threshold":12,"unit":"degC"} | Completed current cooling-demand record has applicable vent temperature above 12 degC. |
| vent temperature at most 12 degC | G8.5 | {"operator":"lte","threshold":12,"unit":"degC"} | Complete applicable record is at most 12 degC; do not invent a persistent warm-air fault. |

## G8.3 Action: Review the blend-door command and position record

State: The current applicable vent temperature exceeds the fictional cutoff.
Type: categorical
Response: Review whether the air-mixing door followed the cooling command before attributing the complaint to a cooling-system component.

The complete current report includes cold command, actual blend-door position,
and confirmation that the position-feedback and connection checks passed.

| Outcome | Destination | Rule | Selection criteria |
| --- | --- | --- | --- |
| door remains warm despite valid cold command | G8.4 | {"operator":"eq","value":"door remains warm despite valid cold command"} | Complete current command, position, feedback and connection records verify the door stays at its warm position under a valid cold command. |
| door reaches requested cold position | G8.5 | {"operator":"eq","value":"door reaches requested cold position"} | The complete current record verifies the requested cold position; refrigerant diagnosis lies outside this guide. |

## G8.4 Action: Review the blend-actuator-only comparison

State: The door remains in its warm position under a verified cold command.
Type: categorical
Response: Review the completed actuator-only comparison and return check; do not infer an actuator fault from one failed position record.

Same job and conditions: A original actuator leaves the door warm and vents
above 12 degC. B reference actuator reaches cold and vents are at most 12 degC.
A2 original actuator restores warm position and above-cutoff temperature.
Command, door mechanism, feedback, connections and the rest of the cooling
system are verified and unchanged. Only the actuator changes.

| Outcome | Destination | Rule | Selection criteria |
| --- | --- | --- | --- |
| repeatable actuator-only warm-air fault | G8.6 | {"operator":"eq","value":"repeatable actuator-only warm-air fault"} | All same-job original/reference/return position and temperature observations and controls above are complete. |
| complete actuator comparison does not localise | G8.5 | {"operator":"eq","value":"complete actuator comparison does not localise"} | A complete otherwise valid comparison fails the required repeatable pattern. |

## G8.5 Handoff: Refer unresolved cooling performance to the workshop

State: The records do not establish the published blend-actuator finding.
Type: observation
Response: These records do not isolate the blend actuator or establish a refrigerant cause. Provide the temperature and door-position findings to the technician.

## G8.6 RootCause: Blend-door actuator fault isolated by the controlled comparison

Requires the complete temperature, command/position and controlled actuator-only
comparison above. Neither warm vents nor temporary improvement is sufficient.
Response: The recorded comparison isolates the original blend-door actuator as the reason warm air continued to mix in despite a cooling request.
