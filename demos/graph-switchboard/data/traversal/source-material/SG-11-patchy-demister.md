# SG-11: Rear-window demisting is patchy

Version: 1.0. Fictional, non-expert-validated review of existing workshop records.
This is not a heating-grid, electrical or glass repair procedure. Use current
records for the same glass and job. Missing checks are next actions; partial,
wrong-job or conflicting supplied records require clarification.

## G11.0 Scope

Fictional 2024 Brand X Model H, turbo-petrol only.

## G11.1 Entry: One rear-window strip stays misted while adjacent strips clear

Use for patchy rear-window demisting after a demist request. This is distinct
from cabin fan airflow, warm-air temperature or a front-windscreen washer issue.
A customer description of a stripe does not establish a broken conductor.
Next: G11.2

## G11.2 Action: Review the recorded rear-window heating pattern

State: Rear-window clearing is reportedly patchy.
Type: categorical
Response: Review the current workshop heating-pattern record to distinguish one cold strip from a whole-grid supply problem.

The report must identify the requested demist state, affected strip and
adjacent strips on the same current glass.

| Outcome | Destination | Rule | Selection criteria |
| --- | --- | --- | --- |
| one strip cold with adjacent strips heating | G11.3 | {"operator":"eq","value":"one strip cold with adjacent strips heating"} | Complete current heating map shows one consistently cold strip and both adjacent strips heating under the same request. |
| entire grid cold | G11.4 | {"operator":"eq","value":"entire grid cold"} | Complete current heating map shows the whole grid cold; no isolated strip fault is established. |
| complete map shows no repeatable cold strip | G11.4 | {"operator":"eq","value":"complete map shows no repeatable cold strip"} | Complete current map does not reproduce a localised cold strip. |

## G11.3 Action: Review the independent cold-strip continuity survey

State: The same current strip remains cold while adjacent strips heat.
Type: categorical
Response: Review the independent continuity survey for that exact strip; a visible mark alone does not establish an electrical break.

Affirmative isolation requires the current survey to identify an open
conductor at a specific point on the SAME cold strip, a matching visible gap,
continuity on both adjoining portions, intact supply contacts, and continuity
on adjacent working strips. All recorded checks must be explicit. This is a
record-review criterion, not instructions to make measurements or repair glass.

| Outcome | Destination | Rule | Selection criteria |
| --- | --- | --- | --- |
| same cold strip has independently isolated conductor break | G11.5 | {"operator":"eq","value":"same cold strip has independently isolated conductor break"} | Every current heating-map and independent continuity/gap/contact/adjacent-strip criterion above is explicitly satisfied on the same strip. |
| complete continuity survey does not localise | G11.4 | {"operator":"eq","value":"complete continuity survey does not localise"} | Complete current survey is supplied but does not affirmatively isolate the cold strip's conductor break. |

## G11.4 Handoff: Refer unresolved rear-window heating for workshop review

State: The records do not establish an isolated rear-window conductor break.
Type: observation
Response: No isolated strip fault is established. Give the technician the heating map and continuity findings, rather than attributing it to the cabin heater.

## G11.5 RootCause: Rear-window heating-strip conductor break independently isolated

Requires the complete current heating map and independent survey in G11.3:
the cold strip, open conductor, visible gap, adjoining continuity, intact
contacts and adjacent-strip controls must agree.
Response: The workshop records isolate a break in one rear-window heating-strip conductor, explaining why that strip stays misted while the neighbouring strips clear.
