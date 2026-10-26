# Phase 6 repeated benchmark

The Phase 6 runner compares all six integrated optimizers with the same budget of 100 candidate evaluations per seed. The budget includes initialization and generated offspring for every method. For RION it also includes the initial evaluation of each inner swarm and every inner PSO iteration; its configuration therefore uses one outer generation. Cache hits, unique calls to the shared allocation evaluator, and final export calls remain separate diagnostics. A final indivisible batch may exceed the target, and `final_batch_overshoot` records that amount.

Bounds, snapping, and deterministic repair do not call the response model and therefore do not consume objective evaluations. Any candidate evaluated after repair counts in the batch that produced it; repeated repaired candidates can appear as cache hits, which is why unique model calls may be lower than the matched candidate budget.

The smoke configuration uses three seeds reserved for integration checking. The final configuration uses 25 different seeds. Pilot and tuning outputs from Phase 5 are excluded from both sets. On the current synthetic fixture, one complete smoke pass comprises 18 jobs and 1,800 candidate evaluations. The final pass comprises 150 jobs and 15,000 candidate evaluations. Runtime is machine-dependent, so the smoke result should be used to estimate wall-clock time before starting the final configuration.

Run or resume the smoke benchmark with:

```bash
python -m department_optimizer.benchmark.run --config configs/benchmark/smoke_synthetic.json
```

Run or resume the configured 25-seed benchmark with:

```bash
python -m department_optimizer.benchmark.run --config configs/benchmark/final_synthetic_25seeds.json
```

Each algorithm/seed pair has one stable directory and one atomic `status.json`. Completed jobs with the same configuration hash are skipped. Interrupted jobs are rerun in place and increment their attempt number. Failed jobs remain visible and are not silently discarded; use `--retry-failed` to retry them. Consolidated indexes are rewritten from those status files, so resuming cannot append duplicate observations.

## Frozen metrics

All objectives use minimization order `research, innovation, student, societal`. The fixed bounds `[-1, 0]` map each objective to `[0, 1]`; values outside those bounds are clipped for metrics only. The dominated hypervolume reference point is `[1.1, 1.1, 1.1, 1.1]`. These values are stored in each benchmark configuration and are frozen before execution.

The runner reports exact dominated hypervolume, inverted generational distance (IGD), nearest-neighbour spacing, feasible population rate, runtime, candidate evaluations, final-batch overshoot, and unique shared-evaluator calls. Hypervolume is larger-is-better. IGD and spacing are smaller-is-better. A one-point archive has spacing zero; an empty feasible archive has hypervolume zero and undefined IGD/spacing. Empty and failed runs stay in `per_seed_metrics.csv` with an explicit status.

The department problem has no known true Pareto front. IGD therefore uses a versioned, hashed nondominated union of all successful archives in that benchmark. This pooled reference is approximate, can favor algorithms included in the pool, and may improve when more runs are added. Analytic metric fixtures in the test suite use known fronts.

`summary_median_iqr.csv` contains medians and interquartile ranges. Paired two-sided Wilcoxon signed-rank tests, paired rank-biserial effects, and Holm-adjusted p-values are produced only when at least 10 matched successful seeds exist. The three-seed smoke run records comparisons as not performed. Statistical results describe this synthetic method fixture; three objective families are unsupported zero scores, so they do not establish a real four-objective ranking.

The manifest records config, allocation, model hashes, seeds, UTC timing, Python/platform/CPU information, and thread environment variables. Raw populations, archives, accounting, per-seed metrics, pooled front metadata, summaries, and statistical results remain together under the configured output root.

## Completed final synthetic run

The configured final benchmark completed on 26 October 2026: 150 of 150 jobs
finished, with zero failures and exactly 100 candidate evaluations per job (15,000
total; zero final-batch overshoot). Every algorithm has all 25 configured seeds.

MOPSO had the highest median hypervolume (`0.0006862869`) and lowest median IGD
(`0.0052269`), followed closely by MOEA/D (`0.0006844762` hypervolume and
`0.0070377` IGD). Holm-adjusted paired tests did not distinguish MOPSO from MOEA/D
at the 0.05 level. MOPSO was significantly better on these two paired metrics than
NSGA-II, NSGA-III, random search, and RION. These findings apply only to this frozen
synthetic fixture: innovation, student, and societal objectives are unsupported zero
scores, the pooled reference front is approximate, and the results do not identify a
best algorithm for real departmental allocation.

The completion audit independently recomputes hypervolume by rectangle-union
inclusion-exclusion and IGD by direct distance calculation for every final run. The
per-run comparisons are saved as
`results/audit/phase12-completion-audit-v1/final_benchmark_independent_metric_check.csv`.
