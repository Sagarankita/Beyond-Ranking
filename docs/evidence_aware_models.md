# Evidence-aware DEA and KPI models

Prompt 15 consumes the audited Prompt 14 package and enforces an evidence gate before
running DEA or fitting response models:

```sh
make evidence-models
```

The public evidence does not provide enough complete comparable institutions for DEA,
or enough CE&IT department-period outcomes for empirical model validation. Therefore no
public efficiency scores, public response model, or public test metric is emitted.

The workflow instead creates two separately named methodological fixtures:

- `calibrated_indian_public_engineering_method_fixture_v1` for input-oriented VRS DEA;
- `calibrated_synthetic_response_models_v1` for generator validation of KPI models.

DEA outputs include solver status, scores, peer weights, slacks, targets, sensitivity,
discrimination warnings, and per-variable provenance. Every score is labeled
`synthetic_scenario`.

The response-model track compares mean, linear, and random-forest candidates. Median
imputation and scaling are inside each fitted pipeline. Units are disjoint across train,
validation, calibration, and test splits; calibration and test use later periods than
training. Outputs include MAE/RMSE, residual diagnostics, conformal interval coverage,
group/period metrics, training support, synthetic share, and version hashes. These
metrics validate recovery of the generator only and are not empirical or causal.

Every KPI appears in the evidence registry as `public_validated`,
`public_descriptive`, `synthetic_scenario`, or `unsupported`. No KPI currently qualifies
as `public_validated`.
