# Final VJTI public-plus-synthetic completion audit

Result: **20 passed, 0 failed, 3 explicit gaps.**

All required workflow gates pass. The project is complete as a **VJTI-calibrated methodological study**, not as an empirically validated or causal allocation study.

## Audit checks

| Check | Category | Status | Evidence | Detail |
|---|---|---|---|---|
| public_source_and_generated_hash_chain | provenance | pass | public manifest + source register |  |
| generator_model_hash_chain | provenance | pass | Prompt 14 -> Prompt 15 manifests and model files |  |
| split_isolation_and_leakage | model | pass | leakage_checks.json + model_splits.csv |  |
| model_validation_and_coverage | model | pass | model_metrics.csv + model_manifest.json |  |
| dea_formulation_and_evidence | dea | pass | dea_summary.json + dea_variable_provenance.csv |  |
| allocation_chain_units_feasibility | allocation | pass | allocation manifest + checks |  |
| objective_direction_and_evidence | allocation | pass | independent baseline evaluation |  |
| experiment_and_report_hash_chain | experiments | pass | experiment_manifest.json |  |
| matched_budgets_seed_and_algorithm_counts | experiments | pass | 18/18 run records |  |
| scenario_and_fixed_reoptimized_coverage | experiments | pass | experiment config + strategy_allocations.csv |  |
| strategy_rules_feasibility_and_duplicates | reporting | pass | strategy artifacts |  |
| report_artifact_only_reproduction | reporting | pass | report.md regenerated from saved artifacts |  |
| final_benchmark_statistical_tests | statistics | pass | 25-seed completion + paired tests + Holm correction |  |
| advanced_extension_evidence_gates | scope | pass | results/extensions/optional-network-dea-multiperiod-assessment-v1/assessment.json |  |
| clean_small_reproduction | reproduction | pass | C:\Users\adnan\Desktop\Beyond-Ranking\artifacts\public_audit\vjti_v1\clean_reproduction |  |
| selected_prediction_recomputed | reproduction | pass | independent_prediction_check.csv |  |
| constraint_residuals_recomputed | reproduction | pass | independent_constraint_check.csv |  |
| pareto_status_recomputed | reproduction | pass | clean_reproduction/runs/*/archive.csv |  |
| hypervolume_igd_recomputed | reproduction | pass | independent_reproduction_metrics.csv |  |
| full_python_test_suite | tests | pass | test_evidence.txt |  |
| network_dea_public_evidence | gap | gap | results/extensions/optional-network-dea-multiperiod-assessment-v1/assessment.json | deferred: no observed comparable stage links |
| multi_period_public_evidence | gap | gap | results/extensions/optional-network-dea-multiperiod-assessment-v1/assessment.json | deferred: no observed longitudinal department decisions/outcomes |
| causal_empirical_validation | gap | gap | public_evidence_assessment.json | unsupported: descriptive public fields and synthetic response models cannot identify causal effects |

## Implementation and evidence matrix

| Work item | Implementation | Evidence | Boundary |
|---|---|---|---|
| Public-source acquisition and immutable snapshots | implemented | publicly_validated | Official source identities and file hashes verified; values remain descriptive. |
| CE&IT capacity, faculty roster, placement and higher-study facts | implemented | public_descriptive | Observed/derived public fields only; no causal interpretation. |
| Calibrated missing-field generator | implemented | synthetic_scenario | Fixed seeds and versioned assumptions; not observed VJTI data. |
| Resource-to-KPI models and intervals | implemented | synthetic_scenario | Generator validation only; no public test set. |
| VRS DEA peer fixture | implemented | synthetic_scenario | Calibrated synthetic peers; not public institutional efficiency. |
| Four-family allocation evaluator | implemented | synthetic_scenario | Mixed public context and synthetic response functions. |
| Repeated algorithm and robustness experiments | implemented | synthetic_scenario | 18/18 VJTI-calibrated runs plus legacy 25-seed software benchmark. |
| Public-only placement sensitivity | implemented | public_descriptive | Rates only; no allocation effect. |
| Network DEA | evidence_gate_applied | deferred | No observed comparable stage links. |
| Multi-period allocation | evidence_gate_applied | deferred | No repeated observed department-period decisions and lags. |
| Gaussian-process extension | not_run | optional | Optional and not needed for required completion. |
| Saved-artifact dashboard | not_run | optional | Optional; static report remains reproducible. |
| Causal allocation effects | not_claimed | unsupported | No intervention design or causal identification. |
| Empirically validated VJTI optimization | not_claimed | unsupported | Department allocations and most outcomes are not publicly observed longitudinally. |

## Reproduction

The clean reproduction copied source code, the frozen allocation configuration, and the versioned model bundle into a temporary workspace without prior result artifacts. It ran NSGA-II and random search with seed 18001 and eight matched candidate evaluations each. Saved outputs are under `clean_reproduction/`.

Independent calculations are in `independent_prediction_check.csv`, `independent_constraint_check.csv`, and `independent_reproduction_metrics.csv`.

## Remaining gaps

Network DEA and multi-period planning remain deferred at their evidence gates. The optional Gaussian-process comparison and dashboard were not undertaken. Causal effects and empirical VJTI optimization remain unsupported. None is represented as completed empirical work.

## Reproduction commands

```bash
python -m department_optimizer.public_data.run --config configs/data/vjti_public_plus_synthetic_v1.json
python -m department_optimizer.evidence_modeling.run --config configs/evidence_modeling/vjti_evidence_models_v1.json
python -m department_optimizer.public_allocation.run --config configs/public_allocation/vjti_four_family_v1.json
python -m department_optimizer.public_experiments.run --config configs/public_experiments/vjti_experiments_v1.json
python -m department_optimizer.audit.public_run --config configs/audit/vjti_public_completion_v1.json
```
