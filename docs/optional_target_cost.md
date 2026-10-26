# Optional reverse target-cost optimization

Run:

```bash
python -m department_optimizer.target_cost.run --config configs/target_cost/synthetic_targets.json
```

The reverse workflow minimizes total annual allocation cost subject to configured KPI or objective-benefit thresholds and every shared allocation constraint. It calls the same decoder, repair, response model, objective definitions, and constraint evaluator used by the multi-objective algorithms. Incremental cost is reported as optimized total cost minus the illustrative baseline total cost; negative values would represent modeled savings relative to that reference.

The seeded feasibility-first evolutionary search uses 20 candidates, nine generations, and at most 250 candidate evaluations per seed. A coordinate-polishing stage reduces monetary variables while preserving targets. Three seeds are run for each supported target set, and the least-cost feasible result is independently reevaluated. This is a bounded heuristic: its result is an upper bound on target-achieving cost and does not prove a global minimum.

The synthetic example includes moderate and ambitious research targets. It also includes requested innovation and student targets, which are rejected before search because those objective families lack outcome models. Unsupported targets consume zero evaluations and remain visible in the output.

Results include all seeds, the selected allocations, KPI prediction intervals, target residuals, feasibility, model-support flags, total and incremental costs, evaluation accounting, data/model/config hashes, and a concise report. They remain synthetic non-causal method evidence.
