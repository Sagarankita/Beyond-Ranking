# End-to-end allocation workflow

## Command and scope

Run the documented small workflow after installing dependencies and training the Phase 3
models:

```sh
make train-models
make allocation-small
```

The second command is equivalent to:

```sh
python main.py allocation --config configs/optimization/small_synthetic.json
```

Every invocation creates a unique UTC-stamped directory under
`results/allocation_runs/`. The original command remains available as
`python main.py --seed ...`; the `allocation` subcommand selects the new workflow.

This is a synthetic methodological example. Its reference allocation is explicitly
`illustrative_not_observed`, and its predictions are not causal resource-effect claims.

## Algorithm separation

`CanonicalNSGA2Adapter` implements a standalone NSGA-II loop with binary tournament
selection, simulated binary crossover, polynomial mutation, feasibility-first dominance,
non-dominated sorting, and crowding survival. It does not use RION's PSO mutation.

`RionAllocationAdapter` calls the repaired legacy hybrid with Prompt 6 repair and
constraint callbacks. Its PSO mutation remains part of RION only. Both adapters request
the same four objective vector and normalized constraint violation from one
`AllocationProblem`; neither contains KPI, cost, or scientific constraint formulas.

Candidate decoding and repair occur before prediction. Feasible candidates dominate
infeasible candidates. Among infeasible candidates, lower normalized violation wins;
among feasible candidates, ordinary Pareto dominance applies.

## Evaluation accounting

Each adapter records requested evaluations, unique shared-evaluator calls, cache hits,
and calls by phase. NSGA-II records zero inner-PSO evaluations. RION records both
inner-PSO requests and unique candidates first evaluated inside PSO. This distinction is
needed because RION's sorting and scalarization can request the same candidate many
times; cached requests do not trigger another model prediction.

The configured small run uses seed 42, population 20, and four generations for each
algorithm. RION also uses two PSO iterations. These settings demonstrate integration and
are not an algorithm-quality benchmark.

## Run artifacts

The run root contains exact workflow/allocation configuration snapshots, the illustrative
reference evaluation, a long-form reference comparison, a readable report, and
`run_metadata.json`. Metadata records seed, timestamps, duration, data/model/config
hashes, model identity, Git state, platform, and dependency versions.

Each algorithm directory contains:

- `population.csv`: the complete final population with decisions, raw KPIs, intervals,
  objective benefits/scores, raw and normalized constraint values, cost, feasibility,
  rank, crowding, seed, and algorithm;
- `pareto_archive.csv`: distinct feasible rank-zero recommendations;
- `feasibility_check.csv`: a fresh evaluator pass confirming unchanged repair and zero
  normalized violation for every archived row;
- `evaluation_accounting.json`: requested and unique calls by phase.

The workflow fails rather than exporting recommendations if the archive is empty or any
archived row fails the independent recheck.

## Current small result

The first completed run produced 20 feasible final candidates for each algorithm and one
independently checked recommendation in each archive. The illustrative reference spends
INR 12 million and uses 50.0 research FTE, with predicted papers 17.50 and citation
percentile 0.6218.

The NSGA-II recommendation spends the full INR 20 million budget and uses 77.2 modeled
research FTE. It predicts 41.43 papers with interval [37.71, 45.16] and citation
percentile 0.6318 with interval [0.6120, 0.6517].

The RION recommendation also spends INR 20 million and uses 67.6 modeled research FTE.
It predicts 41.06 papers with interval [37.33, 44.79] and citation percentile 0.6312 with
interval [0.6114, 0.6510].

Both recommendations reduce configured centre and collaboration-support counts to zero.
That result reflects the learned synthetic predictor and aggregate-budget formulation;
it is not a recommendation to remove real programs. Cost is a hard ceiling rather than
an objective, and only the research family is supported, so the fixture naturally pushes
toward its full budget. Innovation, student, and societal scores remain explicit
unsupported zeros. A single seed and one supported family cannot establish comparative
algorithm performance or a real multi-objective policy trade-off.
