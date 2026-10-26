# Evidence-aware DEA and KPI model report

This is a methodological scenario analysis. Synthetic efficiency and model results are not observed performance, empirical validation, or causal effects.

## Public evidence decision

Public DEA was not run: The public cohort has too few complete comparable institution profiles for DEA. Only 0 complete public DMUs were available against a minimum gate of 12.
A public response model and public test set were also rejected because only one CE&IT outcome period is public.

## Calibrated synthetic DEA

The separately named fixture contains 30 synthetic-calibrated DMUs. All 30 solver runs were optimal. The discrimination warning and peer/slack/target details are in the DEA artifacts.

## Calibrated synthetic KPI models

Mean, linear, and random-forest candidates were compared for 9 KPIs. Preprocessing was fitted inside the training pipeline; units are disjoint across splits and calibration/test periods follow training periods. Test metrics and interval coverage validate the generator, not real VJTI outcomes.

## Evidence labels

Every KPI is registered as public_validated, public_descriptive, synthetic_scenario, or unsupported. No KPI qualifies as public_validated in this package.
