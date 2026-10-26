# Phase 6B synthetic robustness results

This is synthetic method-fixture evidence. Predicted changes are associations from the synthetic response model, not causal estimates.

The run completed 5 supported scenarios. 2 requested scenarios were retained as unsupported rather than simulated with invented variables.

## Fixed strategy versus reoptimization

| Scenario | Fixed nominal feasible | Reoptimized nominal feasible | Fixed Monte Carlo feasible | Reoptimized Monte Carlo feasible | Reoptimized papers mean | Reoptimized papers p10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| budget_lean_15m | False | True | 0.000 | 1.000 | 31.40 | 28.38 |
| budget_base_20m | True | True | 1.000 | 1.000 | 41.15 | 38.12 |
| budget_expanded_25m | True | True | 1.000 | 0.620 | 43.19 | 40.17 |
| faculty_capacity_minus_25pct | False | True | 0.000 | 1.000 | 40.47 | 37.44 |
| centre_unit_cost_plus_25pct | True | True | 1.000 | 1.000 | 41.19 | 38.16 |

The held-fixed base strategy is evaluated unchanged. Reoptimization is a separate adaptive response. A strategy close to a scenario budget can be nominally feasible while having a lower feasibility fraction after assumed unit-cost variation.

## Preference and evidence limits

All 20 policy selections are marked duplicate within their scenario because only the research family has modeled outcomes. Innovation-first and student-first labels therefore do not constitute innovation or student recommendations.

- `patent_cost_plus_25pct`: missing unit-cost decision variables: patent_ip_support.
- `compute_cost_plus_25pct`: missing unit-cost decision variables: compute_capacity_units.

Monte Carlo results use common random numbers and explicit normal/lognormal sensitivity assumptions. The low/base/high table changes prediction-width and unit-cost-variation assumptions; it does not provide calibrated causal probabilities.
