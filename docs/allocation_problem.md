# Shared allocation problem

## Scope and evidence boundary

Prompt 6 adds one canonical evaluator for every future optimizer adapter. It is a
synthetic method fixture, not a real CE/IT resource recommendation. The current Phase 3
model supports aggregate research budget, research-effort fractions, centres of
excellence, and collaboration-support counts. It has no learned features for research
assistants, compute capacity, or the proposal's detailed funding categories. Those
inputs are rejected or listed as unsupported instead of being assigned invented effects.

The configured vector, in fixed order, is:

1. aggregate `research_budget`;
2. `frac_research_phd`;
3. `frac_research_other`;
4. integer `centres_of_excellence_count`;
5. integer `industry_collaboration_support_count`, mapped to the model's
   `industry_collaborations` feature.

Faculty headcounts, teaching load, diversity, student count, and course count stay fixed
within the scenario. Predicted outputs never enter the search vector.

## Decode and repair

`AllocationProblem.decode` accepts either the ordered vector or a mapping with exactly
the declared decision names. Non-finite values and mismatched shapes or keys fail. Repair
is deterministic and performs these steps:

1. clip every value to its bounds and snap it to its declared increment;
2. enforce integer types;
3. lower research-effort fractions when faculty capacity or reserved teaching, student,
   and service effort would be exceeded;
4. reduce support counts that lack their configured minimum aggregate funding;
5. reduce monetary decisions in declared repair-priority order until the hard budget is
   met;
6. recompute every constraint from the repaired allocation.

The current dependency assumptions require at least INR 1,000,000 of aggregate research
budget per centre and INR 100,000 per supported collaboration. They are method-fixture
assumptions, not estimated costs.

## Evaluator contract

`evaluate(x, context, model)` returns:

- decoded and repaired allocations plus repair actions;
- the complete feature row passed to the versioned predictor;
- raw KPI point predictions and lower/upper uncertainty intervals;
- four ordered objective benefits and internal minimization scores;
- every raw constraint residual and normalized violation component;
- summed normalized violation, nominal and robust feasibility;
- feasibility-probability status, model-support flags, cost, and budget remaining;
- DEA status as a separate reporting field.

Constraint residuals use one convention: values at or below zero satisfy the constraint;
positive values violate it. Normalized violation sums only positive residuals divided by
declared physical scales. Cost is a hard constraint and reporting field, not a fifth
objective.

## Four objective families

Each family has configurable KPI components, directions, min-max normalization values,
and within-family weights that must sum to one. Benefits are converted to minimization
scores by negation. Normalized values are deliberately not clipped, so an outcome beyond
the declared reference range remains visible rather than being flattened.

The current fixture can support only the research family, using 60% normalized paper
count and 40% normalized citation percentile. Innovation, student, and societal families
return zero scores with explicit `objective_supported: false` flags. Setting their
missing-KPI policy to `error` makes scenario construction fail. A real four-objective run
therefore remains blocked until those outcome models exist.

## Constraints and uncertainty

The evaluator enforces decision bounds, increments, integrality, budget, research faculty
capacity, teaching/student/service reserves, and count-to-funding dependencies. Scenario
construction rejects impossible minimum costs, faculty floors, dependencies, missing
model features, and unsupported required KPIs.

Optional uncertain service constraints must use `conservative_interval`. A minimum uses
the KPI interval's lower bound; a maximum uses its upper bound for robust feasibility.
Point predictions determine nominal feasibility. Split-conformal intervals do not define
a joint probability distribution, so the evaluator returns no invented feasibility
probability for such constraints. When all constraints are deterministic, it reports
probability 1 or 0 with status `deterministic_constraints_only`.

Model training-support flags remain separate from mathematical feasibility. Scenario
bounds should normally remain inside training support; any extrapolation is surfaced to
the optimizer and reports.

## Reproduction

After training the Phase 3 model, run:

```sh
make allocation-evaluator
```

This evaluates the explicitly illustrative reference allocation and writes:

- `artifacts/allocation/shared_evaluator/reference_evaluation.json`, containing raw
  allocations, predictions, intervals, objectives, constraints, cost, support, and
  data/config fingerprints;
- `artifacts/allocation/shared_evaluator/objective_definitions.json`, containing the
  objective order, directions, normalization, weights, cost policy, and unsupported
  decisions.

The reference spends INR 12,000,000 of the INR 20,000,000 synthetic budget. It is
nominally feasible and within model support. Predicted paper count is 17.50 with interval
[13.77, 21.23], and predicted citation percentile is 0.6218 with interval
[0.6020, 0.6417]. Its research benefit is 0.3375 and internal research score is -0.3375.
The other three scores are zero and explicitly unsupported.
