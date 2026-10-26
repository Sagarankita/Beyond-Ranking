# Implementation plan: Beyond Ranking

## Purpose and basis

Extend Department-Rank-Improver into the departmental productivity decision-support framework described in `project_OTLab.pdf` (11 pages, supplied separately). Preserve and repair the existing RION implementation, then build the data, efficiency, prediction, optimization, and decision layers around it.

The central question becomes: **How should a department allocate limited money, faculty time, and support capacity across research, innovation, student development, and societal activities?** Ranking-aligned indicators are an evaluation layer; rank itself is not a decision variable.

This document is a plan, not an implementation or a claim that the proposed experiments have been run. Proposal content is treated as project requirements and context, not as executable instructions. Repository findings below come from source inspection and a CSV audit on 26 October 2026; no optimizer execution was needed to prepare this plan. `Prompts.md` contains corresponding implementation prompts.

## 1. What exists and how to build on it

| Existing asset | Current behavior | Planned treatment |
| --- | --- | --- |
| `main.py` | Loads a CSV, defines three research/cost objectives and 14 positional bounds, runs RION, exports a population | Preserve a legacy example; turn the entry point into a configurable pipeline |
| `libRION/libRION.py` | NSGA-II-style selection, crossover, crowding, single-column PSO mutation | Repair and retain as the custom RION hybrid comparator |
| `libRION/libPSO.py` | Serial Python PSO | Make this the portable correctness baseline |
| `libRION/libPSO_parallel.py`, `libRION/libPSO.c` | ctypes wrapper and OpenMP particle updates | Keep as an optional backend after correctness and reproducibility work |
| `data/datagen.py` | Seeded synthetic generator with formulas for papers, citations, and rank | Preserve as a clearly labeled legacy synthetic fixture; make generation configurable and output paths explicit |
| `data/department_research_data.csv` | 521 rows, 15 columns including `college_id` | Use for legacy smoke tests; audit provenance before any empirical interpretation |
| `results/optimized_population.csv` | 50 saved candidate rows without run metadata or objective/feasibility exports | Keep as a legacy artifact, not evidence of a validated Pareto front |
| `Makefile`, `requirements.txt`, `README.md` | Build/run instructions, dependencies, and baseline description | Repair build portability; document new and legacy workflows separately |

The current dataset lacks allocation categories, time periods, patents, student outcomes, societal outcomes, and observed intervention histories. It cannot establish the full proposal by itself. Its structure matches the synthetic generator; treat it as synthetic unless independently documented otherwise.

### Correctness work required before adding features

1. **Non-dominated sorting:** `_fast_non_dominated_sort` never increments domination counts, so every individual initially enters the first front. Implement standard domination bookkeeping without duplicate pair updates.
2. **Dominance:** `_dominates` currently requires strict improvement in every objective. Correct minimization dominance to “no worse in all, strictly better in at least one,” after constraint comparison.
3. **Selection bookkeeping:** ranks returned for the combined population are reused against a reordered survivor population. Recompute or carry aligned ranks and crowding distances; use both in tournaments. Handle exact front fills, empty fronts, odd offspring counts, and small populations explicitly.
4. **PSO evaluation context:** `_pso_mutation` evaluates every particle using `offspring.iloc[0]`. Evaluate each candidate in its own complete allocation context. A full decision-vector mutation is easier to reason about than sharing one scalar fitness landscape across unrelated rows.
5. **Feasibility and types:** positional box bounds do not enforce total spending, total effort, service requirements, or integer counts. Validate initial candidates and all variation results using a named schema and shared constraint evaluator.
6. **Outputs as decisions:** the current optimizer can mutate `papers_t1`, `citation_percentile_avg`, and `overall_rank` directly. In the new model, allocate controllable inputs and predict outcomes; keep observed outcomes and rank outside the search vector.
7. **Objective scaling:** the PSO scalar sum mixes large cost values with smaller research metrics. Use documented normalization and a deliberate scalarization for hybrid mutation, while preserving the full objective vector for Pareto selection. The cost objective's fixed `1e5` return for near-zero impact also needs an explicit policy, because it can make zero-impact cases appear cheaper than productive ones.
8. **Native backend:** the wrapper loads a relative `.so` at import time; the Makefile omits a shared-library linking flag. Add portable build configuration, lazy loading, clear errors, and serial fallback. Check allocations, dimensions, callback exceptions, resource lifetime, and finite values across the C boundary.
9. **Parallel reproducibility:** C random seeds depend on thread number and there is no user seed. Global-best updates can overlap other threads' reads after work sharing. Use a frozen global-best snapshot per iteration, a separate reduction/update stage, and particle/iteration-based random streams. Python callbacks reacquire the GIL, so measure actual speedup before claiming parallel performance.
10. **Data/domain mismatch:** observed `overall_rank` reaches 1097 while the configured upper bound is 200; teaching load reaches about 15.99 against an upper bound of 15. Distinguish historical validity from scenario feasibility rather than silently clipping observations.

## 2. Scope and delivery order

Deliver a vertical slice first: **validated data -> basic DEA -> simple predictive model -> feasible NSGA-II allocations -> comparison with a current allocation**. Then add NSGA-III, MOEA/D, MOPSO, the repaired RION comparator, and repeated robust experiments.

Required final scope from the proposal:

- Data dictionary and reproducible data preparation with explicit provenance.
- DEA efficiency scores and peer-frontier analysis; Network DEA only if stage-level data support it.
- Validated resource-to-KPI predictions with error and uncertainty estimates.
- Four objective families and shared realistic constraints.
- NSGA-II, NSGA-III, MOEA/D, and MOPSO comparisons; retain RION as an additional contribution.
- Repeated, matched-budget experiments and budget, policy, shock, and uncertainty scenarios.
- A portfolio of conservative, balanced, research-first, and innovation-first strategies; include student-first in policy experiments.
- Current-versus-optimized tables/charts, reproducible commands, and a technical report.

Optional extensions: Network DEA, Gaussian-process prediction, reverse target-cost optimization, a 2-3 year model, and an interactive dashboard. Do not let these delay the required end-to-end workflow. A report with comparison tables and plots can satisfy the comparison-output requirement before a dashboard exists.

## 3. Modeling contract

### Data and provenance

Use one department-period as the preferred observation unit. Keep institution-level peer records in a separate benchmark cohort; they are not department-level training labels. Record identifiers, period, currency/base year, units, source, access date, missingness, and provenance (`observed`, `derived`, `assumed`, or `synthetic`). Mark imputed values separately.

Organize variables into:

| Role | Examples | Treatment |
| --- | --- | --- |
| Controllable allocation | Research/conference/IP/industry/student/open-access/outreach funding; RA count; compute capacity; faculty effort | Search variables with bounds, costs, and permitted increments |
| Context and capacity | Department size, existing infrastructure, student demand, available faculty time | Fixed for a given scenario unless an explicit intervention changes them |
| Intermediate/output KPI | Papers, Q1 papers, citations, patents, projects, placements, outreach outcomes | Historical labels or model outputs; never freely mutated |
| Evaluation indicator | Efficiency, ranking-aligned aggregates, descriptive rank | Reported with scope and interpretation |

Acquire departmental records where available, public annual reports, and documented peer indicators. Optional bibliometric data require documented matching and coverage. Do not invent unavailable data or assume private database access. If adequate observations are unavailable, ship a separate synthetic scenario track and restrict conclusions accordingly.

### Decision vector and constraints

Define a single scenario-relative allocation `x`: funding categories, faculty effort by activity, integer RA/support counts, and compute units where meaningful. Configuration must specify whether values are totals or changes from a baseline.

Use one cost representation: either monetary allocations sum to the budget, or activity quantities have unit costs. Do not charge the same spending twice. Faculty effort must have a common unit such as annual FTE or person-hours.

Enforce:

- `total_cost(x) <= B` and `total_faculty_effort(x) <= T`.
- Named lower/upper bounds and integrality for selected variables.
- Minimum teaching/student/service commitments and any policy minimum allocations.
- Capacity and logical dependencies where justified by records or stakeholder assumptions.
- Model-support limits or explicit warnings for allocations far outside the training domain.

Return each constraint's residual, total normalized violation, and feasibility flag. Use feasibility-first comparison across optimizers: feasible beats infeasible; lower violation orders infeasible candidates; Pareto dominance orders feasible candidates. Repair operators must preserve integrality and recheck every constraint; infeasible scenarios must be reported explicitly.

### Objective families

Predict KPI values from allocation plus context, then construct four transparent scores:

1. Research impact: publications/Q1 papers, citations or normalized impact, collaboration.
2. Innovation: patents, industry projects, technology transfer.
3. Student development: research participation/projects, placements, higher studies.
4. Societal contribution: open access, SDG/outreach outcomes, visibility where measurable.

Declare units, direction, normalization, within-family weights, and missing-data policy in configuration. Store raw KPIs alongside aggregate scores. Internally minimize the negative of each maximization score. Keep cost as a hard constraint and report it separately; the legacy cost objective stays available for baseline comparisons.

For the proposal's “Societal / Efficiency” family, start with societal KPIs and report DEA efficiency separately. Only combine them after documenting the rationale and avoiding double counting. DEA supplies benchmarking and peer targets, not a causal resource-response function or an automatic multiplier on predictions.

## 4. Target structure

Keep `libRION/` and migrate incrementally; the following paths are proposed, not existing:

```text
main.py                         # thin CLI and workflow selection
libRION/                        # repaired legacy/hybrid engine and PSO backends
src/department_optimizer/
  data/                         # schemas, validation, provenance, preparation
  efficiency/                   # DEA and optional Network DEA
  prediction/                   # training, validation, intervals, support checks
  problem/                      # decisions, constraints, KPI/objective evaluation
  algorithms/                   # NSGA-II, NSGA-III, MOEA/D, MOPSO, RION adapters
  experiments/                  # budgets, seeds, metrics, scenarios, checkpoints
  decision/                     # strategy selection and robustness summaries
  reporting/                    # tables and figures
configs/                        # problem, model, algorithm, scenario settings
data/{raw,processed,synthetic}/  # separate provenance tracks
artifacts/                      # trained models and preprocessing metadata
results/<run_id>/               # immutable run outputs and manifest
tests/                          # correctness, mathematical fixtures, integration
docs/                           # data dictionary, assumptions, methodology, report
```

Shared evaluator contract: `evaluate(x, context, model) -> raw_kpis, objective_vector, constraint_residuals, feasibility, uncertainty, support_flags`. All algorithms call this interface and count its evaluations. Separate an adapter from the scientific problem definition. Use tested numerical/optimization libraries where appropriate; verify current APIs, mixed-variable support, constraints, and licenses when implementation begins rather than assuming a particular package supplies every algorithm.

## 5. Phased implementation and acceptance gates

### Phase 0 - Repair and capture the baseline

**Change:** `libRION/libRION.py`, both PSO wrappers, native C implementation, `Makefile`, dependency declarations, and baseline documentation. Add backend selection and seed propagation. Keep legacy formulas explicitly versioned so corrected behavior can be compared without silently changing the old problem.

**Verify:** hand-calculated dominance/front fixtures including ties, constraint ordering, correctly aligned survivor ranks, exact-size populations, integer validity, row-specific mutation context, and repeatability. Test a known PSO function against a known optimum with a tolerance. Validate native behavior separately when its toolchain is available; do not silently mark skipped native checks as passed.

**Exit:** one reproducible serial run exports objective values, all feasibility flags, and a genuinely non-dominated feasible subset. Native failures cannot prevent importing or running the serial path. Existing saved results remain untouched.

### Phase 1 - Formalize the problem and build the data layer

**Build:** schema, data dictionary, provenance manifest, baseline allocation format, validation/EDA, scenario configuration, and a refactored synthetic generator. Obtain available CE/IT records and comparable peer data. Record missing KPI families instead of generating unlabeled observations.

**Verify:** schema validation is independent of column order; counts and units are checked; duplicate department-periods and source conflicts are reported; preprocessing is reproducible. Historical observations outside policy bounds are flagged without being rewritten.

**Exit:** a dataset audit identifies which objectives are observed, learnable, scenario-only, or unsupported. Freeze an initial decision vector, outcome definitions, budget/effort units, and constraints before training.

### Phase 2 - Benchmark efficiency

**Build:** a documented input/output DEA formulation solved as linear programs. Start with an input-oriented variable-returns-to-scale model if the cohort supports that choice; document alternatives and sensitivity rather than treating the choice as established. Return efficiency, solver status, slacks/targets, and peer references.

**Verify:** small hand-solvable frontier cases; scale/unit behavior; infeasible/degenerate input handling; comparable cohort definition. Keep the input/output count modest relative to the peer sample and report discrimination limitations.

**Exit:** reproducible benchmark table and interpretable resource gaps. Network DEA is admitted only if intermediate stage data and linking assumptions are defensible.

### Phase 3 - Learn allocation-to-KPI relationships

**Build:** simple mean/linear baselines followed by Random Forest and, if justified, boosting alternatives. Fit preprocessing within training folds. Use grouped department/institution splits and time-aware splits where available; reserve an untouched test set when sample size permits. Do not use rank, future outcomes, or derived target proxies as predictors.

**Verify:** per-KPI MAE/RMSE, out-of-sample diagnostics, residual plots, uncertainty coverage, and comparison with simple baselines. Estimate uncertainty via an appropriate bootstrap/ensemble/residual method without consulting the test set. Record data/model versions and extrapolation rules.

**Exit:** a versioned predictor returns KPI estimates and uncertainty. If evidence is weak or a KPI is absent, use a separately labeled scenario response model or reduce scope explicitly. Observational predictions support scenarios, not causal guarantees about interventions.

### Phase 4 - Produce the first feasible optimization result

**Build:** shared evaluator, mixed-variable encoding, repair/constraints, and a canonical NSGA-II adapter. Wire the repaired RION adapter to the same problem. Preserve a legacy command while adding configuration-driven new runs.

**Verify:** every returned recommendation meets the shared constraints after decoding; outputs are predicted rather than searched directly; objective signs and normalization agree; hand-checked candidates yield the expected KPI and constraint vectors. Export the full population separately from the feasible non-dominated archive.

**Exit:** one complete run compares a documented current allocation with feasible alternatives and explains spending, effort, predicted KPI changes, and uncertainty. If no current allocation exists, mark an illustrative reference explicitly.

### Phase 5 - Add the proposal's algorithm comparison

**Build:** NSGA-III with documented reference directions, MOEA/D with decomposition/neighborhood settings, and MOPSO with a bounded external Pareto archive, diversity-aware leader selection, and mixed-variable constraint handling. Existing scalar PSO is not MOPSO; it remains RION's mutation component. Include random feasible search as a sanity baseline if practical.

**Verify:** adapter contract tests and mathematical multi-objective fixtures for fronts, archives, feasibility, and direction handling. Calibrate small pilot settings before the main runs, using a separate tuning budget.

**Exit:** NSGA-II, NSGA-III, MOEA/D, MOPSO, and RION can run on the same evaluator and emit the same result schema. Canonical NSGA-II remains separate from the hybrid for a fair ablation.

### Phase 6 - Run repeated experiments and robustness analysis

**Build:** seeded, resumable experiment runner. Pilot with a few seeds, then target 20-30 independent seeds per algorithm/configuration as proposed, subject to a recorded compute budget. Compare identical scenarios and objective-evaluation budgets, not merely generation counts. Count RION's inner PSO evaluations and initialization/repair-related evaluations consistently.

**Metrics:** hypervolume, IGD, a named diversity/spread measure, feasible-solution rate, and wall-clock runtime. Freeze common objective scaling and a dominated hypervolume reference point. Use a documented analytical reference front for test problems and a pooled non-dominated reference set for the real problem; disclose that IGD then measures distance to an approximation, not a known true front. Define behavior for empty feasible sets.

**Scenarios:** at least three budget levels; balanced/research/innovation/student priorities; budget and faculty-time shocks; patent/compute cost shocks; current-versus-optimized allocations; Monte Carlo model/cost uncertainty. Keep policy preference selection distinct from algorithm quality measurement. Use common uncertainty draws across compared strategies.

**Report:** median/IQR and per-seed results. Add paired/non-parametric tests with effect sizes and multiple-comparison handling if the design and sample size warrant them. Record hardware, thread count, model version, configuration, evaluation count, runtime boundaries, and failures. Evaluate held-fixed strategies under shocks as well as reoptimized scenarios so resilience is not confused with adaptation.

**Exit:** no “best algorithm” claim based on a single seed or visual front. Report robustness, feasibility probability, downside outcomes, and limitations alongside nominal gains.

### Phase 7 - Turn fronts into departmental strategies

**Build:** transparent selection rules for conservative, balanced, research-first, and innovation-first candidates; add student-first where useful. Use declared normalized preferences, compromise/knee rules, and robustness thresholds. Acknowledge when several labels select the same allocation or no candidate meets a policy.

**Outputs:** strategy allocations, differences from baseline, predicted KPIs with intervals, constraint utilization, downside/feasibility probabilities, trade-off plots, and algorithm-comparison tables. Explain which concrete departmental actions each allocation implies. An optional dashboard should consume saved results, not embed a second evaluator.

**Exit:** reproducible report and commands; at least three policy/budget scenarios; interpretable resource trade-offs; clear separation of observed evidence and synthetic assumptions. With inadequate empirical data, completion means a validated methodological prototype, not validated real-world productivity improvement.

## 6. Suggested working sequence

These are planning estimates, not deadlines; data access and repairs may change them.

| Window | Work | Gate |
| --- | --- | --- |
| Week 1 | Phase 0; start records requests and KPI definitions | Correct serial baseline |
| Week 2 | Phase 1; freeze schema and first scenario | Audited data and model contract |
| Week 3 | Phases 2-3 | DEA report and validated predictor or declared synthetic track |
| Week 4 | Phase 4 | End-to-end feasible allocation comparison |
| Week 5 | Phase 5 | All proposal algorithms plus RION integrated |
| Week 6 | Phase 6 | Repeated benchmark and robustness outputs |
| Week 7 | Phase 7, documentation and reproduction | Strategy portfolio and technical report |

Start data acquisition during baseline repair. DEA and prediction both depend on the audited data layer; the optimizer depends on the shared evaluator and a usable response model. Do not wait for optional Network DEA or a dashboard to deliver the first vertical slice.

## 7. Reproducibility and completion checklist

- [ ] Clean setup and serial execution work without OpenMP; optional native setup is documented separately.
- [ ] Corrected RION and canonical algorithms pass meaningful mathematical and integration checks.
- [ ] Data provenance, units, missingness, objective definitions, and assumptions are documented.
- [ ] Learned outputs are separated from controllable allocations, with no target leakage.
- [ ] DEA scores and predictive errors/uncertainty accompany recommendations.
- [ ] Every exported recommendation is decoded, checked, and feasible under its scenario.
- [ ] Four required algorithms and the RION comparator use identical evaluators and accounted budgets.
- [ ] Repeated metrics, at least three scenarios, and uncertainty/shock results are saved.
- [ ] Each run saves configuration, seed, data/model fingerprints, code revision, environment, and objective/constraint outputs.
- [ ] Strategy portfolio shows actual allocations and baseline differences, with empirical/synthetic limitations.
- [ ] A fresh user can reproduce the documented small run; full experiment commands and expected outputs are listed.

## 8. Proposal traceability and decisions to resolve

| Proposal section/pages | Plan coverage |
| --- | --- |
| Executive summary and reframing, pp. 2-4 | Resource decisions replace rank manipulation; legacy RION retained as comparator |
| Data, DEA, prediction, pp. 5-6 | Phases 1-3 with provenance and model validation |
| Decision vector, four objectives, constraints, pp. 6-7 | Modeling contract and Phase 4 |
| Algorithms and experiments, pp. 6 and 8 | Phases 5-6; matched evaluation budgets and repeated seeds |
| Feasibility, deliverables, success, pp. 8-9 | Separate synthetic track, acceptance gates, completion checklist |
| Implementation, risks, contribution, pp. 10-11 | Incremental phases, scope control, decision portfolio |

Resolve during Phase 1: access to CE/IT department-year records; available historical allocations and current baseline; KPI definitions and time lags; budget/effort units; peer cohort comparability; service thresholds; and whether four outcome families have sufficient data. These questions do not block baseline repairs or a labeled synthetic prototype.

The proposal's cited ranking methodology and external references have not been independently verified for this planning task. Validate sources, current methodology, and implementation-library APIs when those parts are implemented; do not hard-code proposal percentages as departmental optimization weights.

## 9. Remaining work after the completion audit

The first twelve implementation prompts and the reverse target-cost extension now
produce a reproducible synthetic methodological prototype. The Network DEA and
multi-period extension has also passed through its required evidence gate, but it was
deferred because the current data contain neither observed stage links nor repeated
department-period records. These results do not complete the proposal's empirical
claim.

The remaining work is divided into one immediately executable package and a public-
evidence-first sequence for VJTI's Department of Computer Engineering & Information
Technology. No private dataset is assumed to be available. Search official and credible
public sources thoroughly, then generate only fields that remain unavailable. Synthetic
fallbacks must be realistic, reproducible, minimally scoped, and visibly separated from
observed or derived evidence so that mixed results are never promoted to empirical findings.

### Phase 8 - Execute the configured final synthetic benchmark

**Build/run:** execute `configs/benchmark/final_synthetic_25seeds.json` for every
enabled algorithm using the existing resumable runner. Preserve the frozen objective
scaling, matched candidate-evaluation budget, seed list, and pooled-reference-front
version. Resume partial runs rather than overwriting valid outputs.

**Verify:** require all 25 seeds for every enabled algorithm, account for every
evaluation, retain failed-run records, independently recompute selected hypervolume
and IGD values, and run the complete test suite. Report median/IQR, paired comparisons,
effect sizes, multiplicity-adjusted results, runtime, feasibility rate, and diversity.

**Exit:** the final benchmark directory and manifest are complete and the completion
audit no longer reports `final_25_seed_benchmark` as a gap. Any algorithm comparison
remains a synthetic-method comparison, not evidence of departmental impact.

### Phase 9 - Acquire public VJTI evidence and build a controlled synthetic fallback

**Search first:** collect available VJTI and Computer Engineering & IT records from the
official VJTI site, NIRF submissions, annual/convocation/accreditation reports, government
open-data sources, scholarly indexes with documented coverage, and official peer-
institution publications. Search for stable unit and period identifiers, current and
historical allocations, currency/base year, faculty effort/capacity, staffing, research,
innovation, student and societal outcomes, peer inputs/outputs, stage links, and outcome
timing. Record every query, URL, access date, document period, retrieval result, and
reason a candidate source was accepted or rejected.

**Build:** add a public-evidence ingestion profile without replacing the legacy synthetic
fixture. Produce a data dictionary, source/search register, unit conversions, missingness
and duplicate reports, conflict-resolution log, and immutable source fingerprints. Mark
every cell or generated series as `observed_public`, `derived_public`,
`synthetic_calibrated`, or `unsupported`. Keep institution-level values distinct from
department-level values.

**Synthetic fallback:** after documented search attempts fail, generate only the missing
variables needed for the methodological workflow. Calibrate ranges and distributions to
public VJTI totals, department capacity, Indian public-engineering-institute benchmarks,
published unit costs, and accounting identities. Preserve plausible correlations,
integer/count behavior, non-negativity, budget and effort totals, temporal continuity,
and logical lags. Use fixed seeds and versioned formulas; record every bound, distribution,
correlation, scaling rule, and source or assumption. Never overwrite public values, copy
institution totals into department fields without a declared allocation rule, or use
generated target values to claim out-of-sample empirical validation.

**Exit:** a data-readiness report states which variables and objective families are
publicly observed, derived, synthetic-calibrated, or unsupported and reports synthetic
coverage by row and column. Freeze the public or explicitly synthetic baseline, budget
and effort units, constraints, peer cohort, outcome lags, generator version, and split
rules before model fitting. The resulting track is called `public_plus_synthetic` unless
all required fields are publicly observed.

### Phase 10 - Fit evidence-aware DEA and resource-to-KPI models

**DEA:** run the documented VRS model on a defensible comparable public peer cohort. Report
solver status, efficiency, peers, slacks, targets, sensitivity to DEA specification,
and discrimination limits, and the provenance mix of every DEA input/output. If a
synthetic peer cohort is required, publish it as a method fixture and do not label its
peers or efficiency scores as observed institutions. Keep institution-level peers
separate from department-level training labels.

**Prediction:** maintain separate public-evidence and synthetic-calibrated model tracks.
Train simple baselines and justified nonlinear alternatives for every supported KPI.
Use grouped unit splits and time-aware validation where public evidence supports them,
fit preprocessing inside training folds, and measure uncertainty and extrapolation
support. Synthetic holdouts test code and generalization under the generator; they are
not empirical test sets. Never use rank, future outcomes, or target-derived proxies.

**Exit:** versioned models report MAE/RMSE, interval coverage, residual diagnostics,
data/generator fingerprints, synthetic share, and limitations. Weak or absent public
outcome families may use a synthetic scenario response model, but remain labeled
scenario-only and cannot support empirical or causal claims.

### Phase 11 - Expand the public-plus-synthetic decision model and scenarios

**Build:** connect public-supported and synthetic-scenario research, innovation,
student-development, and societal KPIs to the shared evaluator while preserving a
per-objective evidence flag. Use public allocation variables and unit costs where found;
otherwise use documented calibrated assumptions. Introduce patent and compute shocks
when their variables and costs are public or transparently synthesized. Replace the
legacy illustrative reference with a VJTI public-plus-synthetic baseline whose observed
and generated components are individually visible.

**Verify:** check units, integrality, budget and effort conservation, minimum service
commitments, model-support flags, objective direction and normalization, and raw KPI
traceability. Each objective family must expose its evidence status. Synthetic objective
responses must vary through documented response functions, pass realism checks, and
remain scenario-only.

**Exit:** all enabled objectives respond to defensible decision variables, every saved
recommendation is feasible, and current-versus-optimized comparisons include prediction
intervals and model-support warnings.

### Phase 12 - Run the VJTI public-plus-synthetic experiments and issue the final report

**Run:** pilot the frozen empirical evaluator, then execute the approved repeated-seed
algorithm benchmark and the required budget, policy, resource-shock, and uncertainty
scenarios. Evaluate both held-fixed strategies and scenario-specific reoptimization
using common uncertainty draws.

**Report:** regenerate the strategy portfolio, current-versus-strategy tables, DEA
results, prediction diagnostics, allocation actions, trade-off figures, uncertainty
summaries, and algorithm comparisons exclusively from saved artifacts. Separate
predictive associations from causal claims.

**Exit:** an independent reproduction confirms data/model/generator hashes, no leakage,
feasibility, metric calculations, run counts, selection rules, and report provenance.
The project may claim completion as a VJTI-calibrated methodological study. It may claim
empirical validation only for analyses based entirely on adequate public observations.

### Phase 13 - Evidence-gated advanced extensions

Implement Network DEA only after Phase 9 provides observed intermediate links for a
comparable cohort and an agreed treatment of shared resources. Implement a 2-3 year
allocation model only after repeated units, per-period decisions, carry-overs, and
defensible outcome lags are available. If those public evidence gates fail, a separate
realistically calibrated synthetic method fixture may demonstrate the mathematics and
software, while empirical Network DEA or longitudinal conclusions remain deferred. A
Gaussian-process model is optional and must
win a predeclared validation comparison or provide materially better calibrated
uncertainty. An optional dashboard must read immutable saved artifacts through the
same reporting definitions and must not contain another evaluator.

### Updated completion gates

- [x] The configured 25-seed synthetic benchmark is fully executed and independently checked.
- [ ] Public VJTI/CE&IT sources are exhaustively searched and recorded before synthetic fallback.
- [ ] A VJTI baseline separates public, derived, and synthetic-calibrated components.
- [ ] Public and synthetic datasets pass provenance, realism, and readiness checks.
- [ ] KPI models report validation type and synthetic coverage without treating synthetic holdouts as empirical evidence.
- [ ] Research, innovation, student, and societal objectives are public-supported or explicitly scenario-only.
- [ ] Patent/compute shocks use public evidence or documented calibrated assumptions.
- [ ] VJTI public-plus-synthetic repeated experiments and robustness scenarios are complete.
- [ ] The final report reports synthetic coverage and is independently reproduced from saved artifacts.
- [ ] Network DEA and multi-period planning use public evidence when supported, otherwise only separately labeled calibrated synthetic fixtures.
- [ ] Optional GP/dashboard work, if undertaken, passes its separate acceptance criteria without changing scientific results.
