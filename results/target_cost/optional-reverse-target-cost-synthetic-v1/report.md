# Optional reverse target-cost results

> Synthetic method fixture. The baseline is illustrative and predictions are not causal intervention estimates.

The objective minimizes total annual allocation cost. Incremental cost is the optimized total minus the illustrative baseline cost of INR 12,000,000; a negative value is reported as a modeled saving.

| Target set | Status | Total cost | Incremental cost | Papers | Citation percentile | Evaluations |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| research_moderate | target_feasible | INR 14,300,000 | INR 2,300,000 | 30.18 | 0.6229 | 211 |
| research_ambitious | target_feasible | INR 19,500,000 | INR 7,500,000 | 40.58 | 0.6306 | 212 |
| innovation_student_requested | unsupported_targets: objective family innovation; objective family student | — | — | — | — | 0 |

Each supported result was independently reevaluated through the shared allocation evaluator after search. Raw target residuals, KPI intervals, feasibility, support flags, allocation values, seeds, and evaluation counts are exported in CSV/JSON artifacts.

The requested innovation and student target set is unsupported because the current model contains no innovation or student outcome components. It is reported without optimization rather than replaced with invented scores.

The search is a bounded seeded heuristic and does not prove a global minimum. Multiple seeds and a cost-coordinate polishing stage improve the method fixture, while the minimum found remains an upper bound on the true target-achieving cost.
