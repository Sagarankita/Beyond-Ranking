# VJTI public-data readiness report

This package is scenario data, not evidence of causal departmental improvement.

## Evidence boundary

The search log contains 12 reproducible search attempts and the source register contains 7 immutable local snapshots. Institute totals remain institution-level records; none is copied into a department field without the derivation stated in `derivation`.

Public department evidence supports current programme capacity, a current faculty roster, and 2023-24 placement/higher-study counts. Departmental budgets, effort, research outputs, innovation outcomes, student-research participation, open-access outputs, outreach, and historical panel values remain synthetic-calibrated.

## Readiness by objective

| Objective | Status | Reason |
| --- | --- | --- |
| Research | synthetic_scenario | No department-period expenditure/output panel was public. |
| Innovation | synthetic_scenario | Public patent/project totals are institute-level only. |
| Student development | public_descriptive_plus_synthetic | 2023-24 CE/IT placement counts are public; the historical response panel is not. |
| Societal contribution | synthetic_scenario | No department-period outreach/open-access series was found. |

## Validation

All 12 realism/accounting checks pass: **True**. Re-running seed 14042 recreates identical generated values; alternate seed 14043 changes stochastic values while retaining the same formulas and bounds.

The public-only, synthetic-only, and merged views are separate. Every merged value carries one of `observed_public`, `derived_public`, `synthetic_calibrated`, or `unsupported`.
