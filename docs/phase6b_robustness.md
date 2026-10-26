# Phase 6B scenarios and robustness

The Phase 6B runner keeps policy preference separate from the four optimization objectives. Canonical NSGA-II first produces feasible nondominated candidates under each supported structural scenario using three seeds and 100 candidate evaluations per seed. Balanced, research-first, innovation-first, and student-first weights are then applied only as post-optimization selection rules.

The synthetic fixture supports three budget levels (INR 15m, 20m, and 25m), a 25% research-faculty-capacity reduction, and a 25% centre unit-cost increase. It does not contain patent-support or compute-capacity decision variables and has no innovation or student outcome models. The requested patent and compute shocks remain in `scenario_catalog.csv` with `unsupported` status. Innovation-first and student-first preferences retain their declared weights, while `unsupported_preference_weight` shows how much of each preference lacks outcome evidence. Duplicate selections are explicitly flagged.

Run or resume the analysis with:

```bash
python -m department_optimizer.robustness.run --config configs/robustness/phase6b_synthetic.json
```

The base 20m strategies are held unchanged and evaluated under every supported shock. Their values are not repaired to fit a new scenario, so infeasibility remains visible. Separately, each scenario is reoptimized and selected under the same four policies. `fixed_vs_reoptimized_comparison.csv` therefore separates resilience of an existing decision from adaptation through reoptimization.

The Monte Carlo analysis uses 1,000 reproducible common draws across every strategy and scenario. Each supported KPI is sampled from an assumed independent normal distribution centered on its prediction, with standard deviation inferred from the model's 90% conformal half-width. Values are clipped to the model target bounds. Unit costs use mean-one lognormal multipliers with an assumed 10% coefficient of variation. Direct monetary allocations are treated as fixed amounts. These distributions are sensitivity assumptions, not learned joint distributions or causal uncertainty.

Outputs report mean and tenth-percentile downside KPI/benefit outcomes, 90th-percentile cost, and the fraction of draws satisfying deterministic non-budget constraints and the sampled budget constraint. Common draws reduce Monte Carlo noise in strategy comparisons. The current allocation problem has no prediction-dependent service constraints, so predictive draws affect outcomes but not feasibility.

`assumption_sensitivity.csv` repeats the analysis under low uncertainty (half the predictive width and 5% unit-cost coefficient of variation), the configured base assumptions, and high uncertainty (1.5 times the predictive width and 20% unit-cost coefficient of variation). These cases test dependence on assumed uncertainty magnitudes; they are not confidence levels.

All results are synthetic method evidence. They do not show that allocations cause KPI changes, and unsupported outcome families cannot support innovation or student policy conclusions.
