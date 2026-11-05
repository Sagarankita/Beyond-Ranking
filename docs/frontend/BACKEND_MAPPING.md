# Frontend-to-backend mapping

## Governing boundary

The frontend consumes outputs; existing workflow modules own computation. No Streamlit
module implements
optimizer objectives, constraint repair, prediction, uncertainty generation, benchmark
metrics, robustness simulation, or target-cost search.

The existing evaluator authority is:

- `department_optimizer/allocation/problem.py` for the generic shared allocation
  problem;
- `department_optimizer/public_allocation/problem.py` for the VJTI public-calibrated
  allocation problem; and
- the workflow/reporting modules listed below for persistence and presentation schemas.

## Overview — implemented

Backend/reporting sources:

- `department_optimizer/reporting/runner.py`
- `department_optimizer/public_experiments/workflow.py`
- `department_optimizer/evidence_modeling/workflow.py`
- `department_optimizer/public_data/workflow.py`

Configuration sources:

- `configs/reporting/phase7_synthetic.json`
- `configs/public_experiments/vjti_experiments_v1.json`
- `configs/evidence_modeling/vjti_evidence_models_v1.json`
- `configs/data/vjti_public_plus_synthetic_v1.json`

Rendered artifacts are listed exactly in `DATA_CONTRACTS.md`. The Overview never invokes
the modules above; it reads their persisted outputs.

## Scenario Studio — Prompt 2 placeholder

Existing backend sources:

- `department_optimizer/data/scenario.py`
- `department_optimizer/allocation/problem.py`
- `department_optimizer/allocation/workflow.py`
- `department_optimizer/public_allocation/problem.py`
- `department_optimizer/public_allocation/workflow.py`

Relevant configurations:

- `configs/scenarios/baseline.synthetic.json`
- `configs/optimization/small_synthetic.json`
- `configs/public_allocation/vjti_four_family_v1.json`

The future UI may edit a typed scenario draft, but execution must be delegated to the
existing Python workflow. Results must be persisted with config, seed, evaluator
identity, and evidence metadata before visualization. Prompt 1 contains no execute
control.

## Algorithm Lab and Pareto Explorer — Prompt 3 placeholders

Existing backend sources:

- `department_optimizer/allocation/optimizers.py`
- `department_optimizer/allocation/advanced_optimizers.py`
- `department_optimizer/benchmark/runner.py`
- `department_optimizer/benchmark/metrics.py`

Relevant configurations and artifacts:

- `configs/benchmark/final_synthetic_25seeds.json`
- `results/benchmarks/phase6-final-synthetic-25seeds-v1/`
- `artifacts/public_experiments/vjti_v1/algorithm_metrics.csv`
- `artifacts/public_experiments/vjti_v1/algorithm_summary.csv`
- `artifacts/public_experiments/vjti_v1/pooled_reference_front.csv`

Future charts must use the benchmark package's matched candidate-evaluation budgets and
saved metric definitions. Plotly may render saved Pareto points, but cannot recompute
dominance, hypervolume, IGD, spacing, feasibility, or statistical tests in place of
`benchmark/metrics.py`.

## Robustness Lab — Prompt 4 placeholder

Existing backend sources:

- `department_optimizer/robustness/runner.py`
- `department_optimizer/public_experiments/workflow.py`

Relevant configurations and artifacts:

- `configs/robustness/phase6b_synthetic.json`
- `results/robustness/phase6b-synthetic-v1/`
- `results/reporting/phase7-synthetic-v1/assumption_sensitivity.csv`
- `results/reporting/phase7-synthetic-v1/scenario_robustness.csv`
- `artifacts/public_experiments/vjti_v1/strategy_uncertainty.csv`

The future UI will distinguish fixed-policy assessment from reoptimization and will not
label Monte Carlo feasibility as empirical evidence.

## Target-Cost Explorer — Prompt 4 placeholder

Existing backend sources:

- `department_optimizer/target_cost/optimizer.py`
- `department_optimizer/target_cost/runner.py`
- `department_optimizer/public_allocation/workflow.py`

Relevant configurations and artifacts:

- `configs/target_cost/synthetic_targets.json`
- `results/target_cost/optional-reverse-target-cost-synthetic-v1/`
- `artifacts/public_allocation/vjti_v1/target_cost_summary.csv`

Future target edits must call the existing reverse-optimization workflow. The browser
must not solve target cost or infer feasibility from chart geometry.

## Evidence & Audit — Prompt 5 placeholder

Existing backend sources:

- `department_optimizer/audit/completion.py`
- `department_optimizer/audit/public_completion.py`
- `department_optimizer/audit/public_reproduce.py`
- `department_optimizer/data/validation.py`

Relevant configurations and artifacts:

- `configs/audit/phase12.json`
- `configs/audit/vjti_public_completion_v1.json`
- `results/audit/phase12-completion-audit-v1/`
- `artifacts/public_audit/vjti_v1/`

The future page may expose manifests, independent checks, seeds, hashes, environment
details, and downloadable provenance bundles. Audit status must come from saved checks;
the browser cannot mark a run reproducible merely because files load.

## Legacy viewer

`sites/beyond-ranking-evidence-dashboard/dist/` remains the original static dashboard
and is served independently with `make legacy-dashboard`. The Streamlit sidebar points
users to that command and local URL. The deprecated React app remains only for temporary
rollback comparison.
