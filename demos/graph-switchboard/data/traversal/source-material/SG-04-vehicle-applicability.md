# SG-04: Fictional vehicle applicability and procedure variants

Version: 1.0, synthetic demonstration source material.

## G4.0 Provenance, applicability and precedence

This supplement extends SG-01, SG-02 and SG-03 to the ten configurations below.
It is authored fictional guidance, not manufacturer information or expert-
validated advice. All numbers, protocols and component findings are invented.
Review supplied workshop records only; do not perform vehicle work.

Each row is an exact applicability boundary, not a family-wide approval.
The original three guides remain unchanged for row a21. For the other rows,
use the base guide's evidence controls with this supplement's explicit
substitutions and ordering. Never transfer a pressure band, cylinder finding,
review order or fan-stage pattern from a neighbouring configuration.
No priorities between simultaneous current misfire and lean findings are given.

Model, year and configuration must be established. Missing identity requires
clarification even if the catalogue currently lists only one matching model.
An explicitly unsupported configuration is unsupported, not the nearest match.
If a selected vehicle and the report disagree, clarify the conflict rather than
silently choosing either one. A missing selection does not establish identity.
Vehicle/job/profile identifiers on workshop records must match the current case.
Historical or explicitly different-vehicle records cannot establish a transition.

## G4.1 Configuration schedule

All makes below are fictional Brand X. "petrol" and "turbo-petrol" are distinct
configuration identifiers. The cylinder is the current misfire cylinder; donor
is the comparison cylinder, not an instruction to move components. Pressure
limits are inclusive kPa for the current RP-IDLE record. Joint names are local
procedure locations, not a vehicle-topology ontology. CP-FAN remains the named
fictional record-review protocol; its required pattern is vehicle-specific.

| Key | Model | Year | Configuration | Cylinder | Donor | Ignition order | Pressure min | Pressure max | Joint | Missing stages | Working stages |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| a21 | Model A | 2021 | petrol | 1 | 2 | coil-first | 250 | 400 | J | 1-3 | 4 |
| b21 | Model B | 2021 | petrol | 1 | 2 | plug-first | 450 | 600 | L | 1-2 | 3-4 |
| c22 | Model C | 2022 | petrol | 2 | 3 | coil-first | 300 | 450 | M | 1-2 | 3-4 |
| d22 | Model D | 2022 | turbo-petrol | 3 | 4 | plug-first | 500 | 650 | N | 1-3 | 4 |
| e23 | Model E | 2023 | petrol | 1 | 3 | coil-first | 275 | 375 | P | 1-3 | 4 |
| f23 | Model F | 2023 | turbo-petrol | 2 | 4 | coil-first | 400 | 550 | Q | 1-2 | 3-4 |
| g24 | Model G | 2024 | petrol | 3 | 1 | coil-first | 350 | 500 | R | 1-2 | 3-4 |
| h24 | Model H | 2024 | turbo-petrol | 4 | 2 | plug-first | 550 | 700 | S | 1-3 | 4 |
| i20 | Model I | 2020 | petrol | 2 | 1 | plug-first | 225 | 325 | T | 1-3 | 4 |
| j20 | Model J | 2020 | turbo-petrol | 4 | 3 | plug-first | 475 | 625 | U | 1-2 | 3-4 |

## G4.2 Misfire variants

For each configuration the exact entry code is P030 followed by its cylinder
number. The donor code is P030 followed by its donor number. The base guide's
"cylinder one" references mean the scheduled cylinder instead. Exact code
matching still applies: an extra digit is not the same finding.

Coil-first rows use SG-01's order: coil review, then plug review only if the
complete coil comparison leaves the misfire on the original cylinder.
Plug-first rows instead use the review instructions in G4.3 and G4.4.
The first comparison following the component with a valid return establishes
that component finding. If it remains on the original cylinder, review the
second component. If both complete comparisons remain on that cylinder,
refer for unresolved misfire; do not invent another component conclusion.
Never reuse controls from one comparison as evidence that the other was done.

## G4.3 Plug-first entry review

Review the current job's recorded plug-only comparison for {baseline_code},
original cylinder {cylinder}, donor cylinder {donor}. This is the FIRST review;
no earlier coil comparison is required. An interpretable record reproduces
{baseline_code} at baseline, changes only the plugs between these cylinders,
identifies the resulting cylinder and records the return to original positions.
Coils and other diagnostic variables remain unchanged within this comparison.
If the result becomes {donor_code} and returning reproduces {baseline_code},
the original cylinder-{cylinder} plug fault is established. If the complete
comparison remains {baseline_code} during the exchange and after return,
continue to the coil review. If no comparison exists or it was not done,
leave this review as the next action. A supplied partial, conflicting or
inconclusive comparison requires clarification, not either result branch.

## G4.4 Coil review after a non-localising plug comparison

This review follows a complete plug-only comparison that remained on cylinder
{cylinder}. Review a separate coil-only comparison for the current job:
baseline {baseline_code}, donor cylinder {donor}, plugs restored and unchanged,
only coils changed, observed cylinder and a return comparison.
If the result becomes {donor_code} and returning reproduces {baseline_code},
the original cylinder-{cylinder} coil fault is established.
If the complete comparison remains {baseline_code} during the exchange and
after return, refer for unresolved misfire. No coil record or a statement
that the check was not done leaves this review as the next action.
Partial, conflicting or inconclusive supplied evidence requires clarification.

## G4.5 Lean-mixture variants

For every scheduled vehicle SG-02's entry remains rough idle with current
P0171 and no competing current P030 code for that configuration.
Use its scheduled pressure limits instead of 250-400 kPa, including both
boundaries. The only documented conversion remains 1 bar = 100 kPa.
A declared unit, current job and RP-IDLE profile are required.
Inside the vehicle's band permits its scheduled joint-localisation review;
outside requires pressure referral, never a pump diagnosis.
Missing units, conflicting applicable values or a supplied wrong-vehicle
record require clarification at pressure review. No supplied pressure record
leaves pressure review as the next action.

The controlled localisation record has the same complete A/B/A2/C criteria as
SG-02: A >+15%, B between -5% and +5%, A2 >+15%, C >+15%;
same job/profile, no other diagnostic changes and pressure within this
vehicle's band throughout. Replace joint J with the scheduled joint;
the control remains joint K. The complete repeatable pattern establishes only
an unmetered-air leak at the scheduled joint. A complete non-localising record
requires referral; partial controls require clarification.

## G4.6 Vehicle-specific fan-stage review

Review the current workshop record for all four commanded fan stages.
Customer language may establish an airflow complaint, not a completed check.
For this vehicle, airflow absent at stages {missing_stages} and present at
stages {working_stages} permits the CP-FAN control-unit comparison.
No airflow at any stage requires complete-loss referral. Airflow at every
stage with a temperature-only complaint is outside this diagnostic scope.
Any other complete pattern requires unhandled-pattern referral, not an
invented component finding. No workshop record leaves this review as the
next action. A partial or contradictory supplied record requires clarification.

## G4.7 Vehicle-specific control-unit comparison

Review the complete current-job CP-FAN record. Supply, ground and connection
checks must explicitly meet CP-FAN requirements throughout. The low-speed
control unit must be the only changed diagnostic variable.
A: original unit, no airflow at {missing_stages}, airflow at {working_stages}.
B: reference unit, airflow at all four stages.
A2: original restored, the same {missing_stages}/{working_stages} pattern recurs.
Only this complete controlled pattern establishes the original low-speed
fan control-unit fault. A complete otherwise valid non-localising comparison
requires referral. No comparison leaves this review as the next action.
Partial return records, missing prerequisites or conflicting unit identities
require clarification. A single improvement does not establish a cause.
