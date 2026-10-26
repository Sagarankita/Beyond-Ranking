# Phase 7 strategy portfolio and report

The Phase 7 command reads the saved Phase 6 benchmark and Phase 6B robustness artifacts. It does not call the allocation evaluator, retrain a model, or optimize a second time. Source paths and hashes are stored in the report manifest.

Run:

```bash
python -m department_optimizer.reporting.run --config configs/reporting/phase7_synthetic.json
```

The portfolio applies six declared rules to the base INR 20m scenario. Conservative selection requires at least 95% sampled feasibility and maximizes the tenth-percentile research benefit. Balanced, research-first, innovation-first, and student-first use the saved post-optimization preference selections. Compromise selection minimizes normalized distance to the supported-objective ideal. A knee requires at least two varying supported objectives; otherwise the output records that it is unavailable.

Every strategy row includes its allocation group. Identical allocations retain their policy labels but are flagged as duplicates. Missing policies, failure to meet the robustness threshold, and absent feasible choices produce explicit statuses rather than fallback claims.

The report exports current-versus-recommended allocations, raw KPI predictions and intervals, Monte Carlo downside outcomes, budget and research-FTE utilization, every constraint residual, concrete departmental actions, smoke-benchmark tables, scenario robustness, assumption sensitivity, and proposal traceability. SVG figures visualize the saved feasible candidate set, algorithm hypervolume medians, and scenario feasibility.

The current fixture yields one unique allocation because research is the only modeled objective family. Innovation-first and student-first each place 90% of their preference weight on unsupported outcomes. Those labels are retained to demonstrate the reporting contract, but they are not evidence-backed innovation or student recommendations. The current allocation is illustrative, all predictions are synthetic, and no reported difference is a causal effect.
