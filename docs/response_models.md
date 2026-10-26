# Synthetic resource-to-KPI response models

## Evidence boundary

Phase 3 cannot produce an empirical intervention model from the repository's current
data. The only complete table is a single-period, hand-generated synthetic fixture. The
implemented track is therefore named `legacy-synthetic-response-model-v1` and is useful
for validating training, persistence, prediction, uncertainty, and optimizer integration.
Its predictions are not causal estimates and must not be presented as expected effects
for CE/IT or another institution.

The fixture supports two targets: `papers_t1` and `citation_percentile_avg`. Patent,
technology-transfer, student, placement, higher-studies, open-access, and societal/SDG
outcomes are recorded as unsupported because no matching labels exist. `overall_rank`
is excluded from both targets and features. The other generated outcomes are also barred
from the feature set, preventing outcome leakage and derived-target proxy leakage.

## Features and models

The model uses the available allocation and known-context columns: faculty counts,
research fractions, research budget, centres of excellence, teaching load, diversity,
industry collaborations, student count, and course count. These columns describe the
synthetic generator and do not establish real-world intervention levers.

Each target starts with three candidates:

- a training-fold mean baseline;
- a median-imputed, standardized linear regression;
- a median-imputed Random Forest with a fixed model-training seed.

Imputation and scaling live inside scikit-learn pipelines and are fitted on training rows
only. The Random Forest seed is recorded separately from future optimizer seeds. Boosting
is deferred because the current synthetic comparison does not justify another model
family.

## Splitting and uncertainty

The deterministic split assigns 60% of rows to training, 15% to validation, 15% to
calibration, and 10% to the final test set. Validation RMSE selects the model, with MAE
and model name as deterministic tie-breakers. The test set has no role in fitting,
selection, or interval calibration.

Meaningful time-aware splitting is impossible because all rows belong to one synthetic
period. Group-aware generalization is also unavailable because each institution-like ID
appears once. Both limitations are stored in the manifest. When observed repeated
department-period data arrive, the random fixture split must be replaced by forward-time
and held-department evaluation.

Prediction intervals use the absolute residual quantile from the calibration split. The
finite-sample split-conformal quantile targets 90% marginal coverage. Final test coverage
is reported without using test outcomes to change the interval. This coverage applies to
the synthetic exchangeable fixture; it does not quantify intervention or distribution-shift
uncertainty.

## Reproducibility and prediction contract

Run:

```sh
make train-models
```

The command writes `artifacts/models/legacy_synthetic_response_v1/`, including:

- `manifest.json`: interface version, data/config hashes, feature and target schemas,
  selected models, dependency versions, interval radii, training support, and limitations;
- `models/*.joblib`: fitted preprocessing and estimator pipelines;
- `splits.csv`: row IDs and fixed split membership;
- `metrics.csv`: per-target validation and test MAE/RMSE for every candidate plus selected
  model coverage and interval width;
- `residual_diagnostics.csv` and `test_predictions.csv`;
- `unsupported_outcomes.json` and an exact configuration snapshot.

Load the versioned optimizer-facing interface with:

```python
from department_optimizer.modeling import load_prediction_bundle

bundle = load_prediction_bundle("artifacts/models/legacy_synthetic_response_v1")
result = bundle.predict(candidate_rows)
```

The result includes bounded point predictions, lower/upper intervals, an
`out_of_support` flag, and the feature names outside training minima/maxima. Missing
features and infinite values fail explicitly. Missing individual feature values can be
imputed by the persisted training-fold pipeline, but are marked out of support.

## Current synthetic-fixture result

The committed 521-row run selected linear regression for `papers_t1` and Random Forest
for `citation_percentile_avg`. On 53 untouched test rows, paper prediction produced MAE
1.611 and RMSE 1.949, compared with mean-baseline MAE 307.378 and RMSE 477.937. Citation
prediction produced MAE 0.0111 and RMSE 0.0132, compared with mean-baseline MAE 0.0485
and RMSE 0.0590.

The nominal 90% intervals covered 94.3% of paper observations and 84.9% of citation
observations. The citation shortfall is reported in `manifest.json` with
`coverage_below_nominal: true`. It is evidence that this small held-out sample does not
confirm nominal citation coverage, and no test-driven widening or retuning was applied.
