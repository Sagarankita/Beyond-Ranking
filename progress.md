# Project implementation progress

**Updated:** 14 November 2026  
**Overall status:** The optimization backend is implemented as a reproducible,
evidence-aware methodological prototype. It supports complete synthetic and
public-calibrated-plus-synthetic studies, but it is **not** an empirically validated or
causal allocation system.

## Current verification snapshot

- Optimization/backend suite: **90 tests run, 84 passed, 6 skipped**. The skipped
  checks require the optional OpenMP native PSO library; the serial implementation is
  available and tested.
- Streamlit/API/reporting suite: **48 tests passed**, including live scenario changes,
  optimizer execution through the API, candidate revalidation, recommendation
  reconciliation, evidence views, Experiment Lab, Groq fallback safeguards, and the
  professor-facing export.
- Combined automated status: **138 tests run, 132 passed, 6 optional native tests
  skipped, 0 failures** on 14 November 2026.
- Final synthetic benchmark: **150/150 jobs complete**.
- Public-calibrated experiment: **18/18 runs complete**.
- VJTI completion audit: **20 passed, 0 failed, 3 explicit evidence gaps**.

## 1. Optimization backend: implemented

### Data, schemas, and provenance

- Configuration-driven synthetic data generation with fixed seeds.
- Dataset and scenario validation for columns, units, finite values, identifiers,
  source conflicts, bounds, and allocation semantics.
- Data audits with dictionaries, validation issues, objective inventories, source
  registers, field-level traceability, missingness reports, and SHA-256 manifests.
- Explicit separation of observed public, derived public, synthetic-calibrated, and
  unsupported values.
- The VJTI CE&IT package contains 12 reproducible source searches, 7 immutable source
  snapshots, and 12 passing realism/accounting checks.

### DEA benchmarking

- Input-oriented, variable-returns-to-scale DEA with solver-status checks, efficiency
  scores, peer weights, slacks, targets, provenance, and discrimination warnings.
- Tests cover known frontiers, unit-rescaling invariance, invalid inputs, duplicate
  DMUs, missing values, and incomparable cohorts.
- A 30-DMU calibrated synthetic DEA fixture is complete; all 30 solves are optimal.
- Public DEA is correctly blocked because the repository has 0 sufficiently complete,
  comparable public DMUs against the configured minimum of 12.
- DEA remains descriptive context and is not used as a multiplier inside allocation
  objectives.

### KPI response modeling

- Mean baseline, linear regression, and Random Forest candidate models.
- Reproducible, disjoint train/calibration/test splits with leakage checks.
- Persisted preprocessing, models, metrics, residual diagnostics, test predictions,
  support bounds, manifests, and prediction intervals.
- Finite-sample conformal interval logic is tested.
- The VJTI-calibrated fixture compares models for 9 KPIs. These models validate the
  generator/scenario, not real VJTI intervention effects.

### Shared allocation evaluators

- Each experiment track has one canonical evaluator shared by all six optimizers:
  `AllocationProblem` for the legacy fixture and `VJTIPublicAllocationProblem` for the
  VJTI public-plus-synthetic track. There is no algorithm-specific evaluator.
- Supports continuous, integer, incremented, direct-money, unit-cost, and non-monetary
  decisions.
- Deterministic repair handles bounds, increments, integer snapping, faculty capacity,
  dependency rules, and budget overruns.
- Feasibility covers named residuals for bounds, integrality, increments, budget,
  faculty capacity, teaching/student/service floors, dependencies, and conservative
  KPI service thresholds.
- Returns repaired allocations, repair actions, costs, KPI predictions and intervals,
  four objective-family scores, evidence/support flags, and nominal/robust feasibility.
- Uses feasibility-first Pareto comparison and independently rechecks saved archive
  candidates.

### Optimization algorithms

Six repository-native algorithms use the same evaluator and result schema:

- NSGA-II
- NSGA-III with reference directions and niching
- MOEA/D with decomposition and neighborhoods
- MOPSO with a bounded external archive and crowding-based leaders
- RION, the corrected hybrid NSGA-II/PSO method
- Random search as a baseline

RION supports serial PSO and an optional OpenMP native backend. The native library is
not currently built in this workspace, so its 6 native-only tests are skipped; the
serial implementation is fully available and tested.

### Benchmarking and statistical comparison

- Resume-safe per-algorithm/per-seed execution with configuration hashes and exact
  candidate-evaluation accounting.
- Matched evaluation budgets across algorithms.
- Persisted populations, nondominated archives, status, runtime, and accounting.
- Metrics: hypervolume, IGD, spacing, feasibility rate, archive size, and runtime.
- Paired Wilcoxon tests, rank-biserial effect sizes, and Holm correction.
- Three-seed smoke benchmark: 18/18 jobs complete.
- Final synthetic benchmark: **150/150 jobs complete**, using 6 algorithms × 25 seeds.
- The benchmark supports software/method comparison, not a universal
  "best algorithm" claim.

### Robustness and uncertainty

- Held-fixed strategy assessment is kept separate from scenario reoptimization.
- Supported scenarios cover base, lean, and expanded budgets; reduced faculty
  capacity; and increased centre unit cost.
- Monte Carlo assessment uses common random numbers and explicit uncertainty
  assumptions.
- Low/base/high assumption sensitivity and fixed-vs-reoptimized comparisons are saved.
- Five supported scenarios are complete. Patent-cost and compute-cost shocks are
  explicitly reported as unsupported in the legacy decision model instead of being
  simulated with invented variables.

### Strategy reporting

- Builds conservative, balanced, research-first, innovation-first, student-first, and
  compromise views from saved optimization artifacts.
- Exports allocation changes, KPI intervals, resources, constraints, Pareto plots,
  robustness, algorithm summaries, assumptions, hashes, and reproducible commands.
- Detects duplicate recommendations and reports when a Pareto knee is unavailable.
- The legacy synthetic portfolio produced 6 labels but only 1 unique allocation;
  unsupported preference weights are disclosed rather than presented as evidence.
- Reporting reads saved outputs and does not implement a second evaluator.

### Reverse target-cost optimization

- Finds a low-cost feasible allocation subject to supported KPI targets.
- Uses bounded seeded search, multiple seeds, cost-coordinate polishing, and final
  reevaluation through the shared evaluator.
- Legacy synthetic results include feasible moderate and ambitious research targets.
- Unsupported innovation/student targets terminate without running a fake search.
- The VJTI workflow also contains separate public-informed student target and
  four-family scenario target tracks.
- Results are heuristic upper bounds on target-achieving cost, not proofs of a global
  minimum.

### VJTI public-plus-synthetic study

- A reproducible public-data workflow preserves public values and prevents institute
  totals from being silently treated as department values.
- The allocation model contains 12 decisions across funding, faculty effort, research
  assistants, and compute capacity.
- Research, innovation, student development, and societal contribution objectives are
  all represented in the scenario model.
- Public placement and higher-study facts inform selected baselines/targets; allocation
  response functions remain synthetic.
- Reference allocation: INR 33.3 million total cost under an INR 36 million limit.
- Frozen public-calibrated experiment: **18/18 runs complete**, using 6 algorithms ×
  3 seeds with a matched budget of 16 candidate evaluations per run.
- Saved outputs include algorithm comparisons, 18 strategy/scenario records,
  11 retained recommendations, KPI intervals, resources, constraints, objective
  evidence, uncertainty, Pareto trade-offs, and public-only sensitivity.

### Reproducibility and completion audits

- Manifests hash source data, configurations, model bundles, and report inputs.
- Independent checks recompute selected predictions, constraint residuals, Pareto
  status, hypervolume, and IGD from saved artifacts.
- A clean reproduction runs without relying on previous result directories.
- Legacy completion audit: all required implementation checks pass, with evidence gaps
  recorded separately from failures.
- VJTI completion audit: **20 passed, 0 failed, 3 explicit evidence gaps**.
- Current backend suite: **90 tests run, 84 pass and 6 optional native-backend tests
  are skipped**.

## 2. Optimization backend: not yet supported

- Causal or empirically validated claims that a recommended allocation will improve
  VJTI or another real institution.
- A longitudinal observed department-level allocation/outcome panel.
- A public response-model test set; only one CE&IT public outcome period is available.
- Network DEA: deferred because observed stage-link variables and comparable public
  DMUs are missing.
- Multi-period planning: deferred because stable longitudinal decisions, carry-over
  resources, and lagged outcomes are missing.
- The optional Gaussian-process model comparison has not been run.
- A guaranteed global optimum for target-cost search.
- Production deployment and live institutional data ingestion.
- Distributed or multi-process live-run workers; the current service uses one local
  persisted worker with restart detection and explicit retry.

These are evidence or productization gaps, not hidden completed features. The software
must continue to label synthetic scenario results as synthetic and non-causal.

## 3. UI development: separate status

- The primary frontend has been migrated from React/Vite to Streamlit.
- A local FastAPI run service validates allowlisted VJTI scenario edits, executes all
  six existing optimizer adapters, persists run state, and independently revalidates
  feasible archive candidates.
- Department Overview and Resource Planner are wired to the API over HTTP. A professor
  can edit budget, faculty capacity, or supported cost multipliers; validate the
  scenario; launch a real matched-budget run; select a feasible candidate; and inspect
  exact allocations, utilization, objective scores, constraints, and stored KPI
  intervals.
- Strategy Comparison supports same-run candidate deltas with exact units.
- Experiment Lab exposes completed benchmark metadata while keeping it separate from
  the current interactive run.
- Evidence & Assumptions exposes field provenance, the blocked public DEA state, the
  synthetic DEA label, hashes, and downloadable browser-session provenance.
- Department Improvement Advisor is now deterministic and grounded. It selects only
  independently revalidated feasible candidates using balanced, research-focused,
  innovation-focused, student-focused, and conservative-service profiles. Duplicate
  profile selections are disclosed.
- Recommendation facts include exact controllable action deltas, per-variable budget
  effects, faculty utilization, objective changes on the defined normalized scale,
  actionable constraint margins, model-support warnings, uncertainty intervals,
  stable IDs, selection rules, and provenance.
- Controlled budget or faculty diagnostics change one factor and rerun the same
  algorithm, seed, and evaluation budget. Held-fixed without repair and reoptimized
  assessments remain separate and are explicitly non-causal.
- Prompt 5 adds an isolated, optional Groq wording service. It runs only after an
  explicit **Explain in plain language** action, receives a minimal allowlisted fact
  packet, and cannot select candidates, calculate values, mutate data, retrieve files,
  or call optimizers. Strict local schema, grounding, quantity, action, feasibility,
  causal-claim, source-ID, and punctuation checks protect the structured facts.
- Missing keys, disabled configuration, provider failures, timeouts, malformed output,
  hallucinated content, and stale cache entries fall back to deterministic wording.
  Safe cache and audit records contain hashes and provider metadata, never credentials.
- Prompt 6 populates Experiment Lab from all 150 saved synthetic benchmark jobs with
  distributions, median/IQR tables, paired Wilcoxon results, rank-biserial effects,
  Holm adjustment, metric definitions, and implementation-grounded algorithm summaries.
- Evidence & Assumptions now exposes the explicit blocked public DEA gate, labeled
  30-unit synthetic DEA fixture, public sources, data dictionary, nine KPI model and
  interval records, support ranges, audit checks, and the saved held-fixed versus
  reoptimized robustness comparison without mixing assessment modes.
- The Advisor exports a deterministic professor-facing Markdown summary containing
  scenario identity, exact inputs and allocation changes, trade-offs, uncertainty,
  evidence class, controlled sensitivity when available, and reproduction metadata.
- Synthetic, public-plus-synthetic, and empirical evidence lanes are visibly separated.
- UI files are allow-listed and validated by path, schema, byte count, and SHA-256
  before rendering.
- Streamlit never imports optimization, prediction, repair, or constraint logic. Live
  work is delegated to the Prompt 2 API and canonical backend evaluator.
- The React/static dashboard is retained temporarily as a deprecated fallback.
- The Streamlit suite includes component tests and an interactive scenario test that
  changes a budget, runs the optimizer through the API, and verifies a revalidated
  strategy and budget headroom. Prompt 3 was also exercised in a real browser against
  the local API. Prompt 4 adds recommendation reconciliation, abstention, support,
  provenance, and controlled-sensitivity tests. Prompt 5 adds provider-independent
  call-isolation, caching, fallback, stale-cache, and adversarial-output tests. The
  current Streamlit, contract, API, recommendation, explanation, reporting, and
  interaction suite has **48 passing tests**.

## 4. Bottom line

The project already contains a complete and well-tested **optimization research
pipeline**: validate data → benchmark with DEA → train response models → evaluate and
repair allocations → run six optimizers → compare matched-budget results → test
robustness → create strategy and target-cost outputs → independently audit everything.

What is still missing is the evidence required to call the recommendations empirically
validated institutional policy. At present, the strongest defensible description is:

> A reproducible synthetic and public-calibrated-plus-synthetic decision-support
> methodology, with explicit evidence boundaries and independent audit artifacts.

## 5. Main reproduction commands

```bash
make test
make public-data
make evidence-models
make public-allocation
make public-experiments
make public-completion-audit

make benchmark-smoke
make benchmark-final
make robustness-smoke
make strategy-report
make target-cost
make completion-audit
```

Install the UI dependencies once:

```bash
make frontend-install PYTHON=.venv/bin/python
```

Then run the API and Streamlit UI in separate terminals:

```bash
make frontend-api PYTHON=.venv/bin/python
```

```bash
make frontend-dev PYTHON=.venv/bin/python
```
