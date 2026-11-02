# Beyond Ranking — Codex Implementation Prompts

## Goal
Transform the existing **Beyond-Ranking** Python optimization research repository and its read-only evidence dashboard into an **interactive, visual, explainable decision-support application**. Users should be able to configure inputs, run real optimizer experiments, compare algorithms and scenario episodes, explore individual Pareto solutions, and stress-test recommendations without an overcrowded interface.

**How to use:** Open Codex at the root of the existing `Beyond-Ranking` repository, give it this file (or paste prompts individually), and execute **Prompts 1–5 in order**. After each prompt, review the deliverables, run the listed checks, and make a Git commit. Each prompt assumes all previously completed phases are present.

### Repository facts Codex must preserve

- The Python backend uses a **shared allocation evaluator** and includes **NSGA-II, NSGA-III, MOEA/D, MOPSO, RION**, and **random search**.
- Existing workflows include input validation, DEA, KPI models, allocation optimization, benchmark evaluation, robustness analysis, target-cost optimization, and reproducibility audits.
- `main.py`, `Makefile`, `department_optimizer/`, `configs/`, `results/`, `artifacts/`, and `docs/` are important integration points.
- The current frontend is a **read-only static dashboard** under `sites/beyond-ranking-evidence-dashboard/dist/` (not a simulation API).
- Useful saved outputs include `results/reporting/phase7-synthetic-v1/` (`current_vs_strategy_allocations.csv`, `current_vs_strategy_kpis.csv`, `resource_utilization.csv`, `constraint_checks.csv`, `strategy_portfolio.csv`, `scenario_robustness.csv`, `assumption_sensitivity.csv`, `algorithm_comparison.csv`) and `results/benchmarks/phase6-final-synthetic-25seeds-v1/` (`summary_median_iqr.csv`, `per_seed_metrics.csv`, `statistical_tests.csv`, `run_index.csv`). Additional public-calibrated scenario outputs are under `artifacts/public_allocation/vjti_v1/` and related directories.
- There are **three distinct evidence lanes**: synthetic methodological fixtures; public-calibrated scenarios with **synthetic, noncausal intervention responses**; and descriptive public empirical evidence. Do not conflate them.
- The original small synthetic experiment supports the **research** objective; its innovation/student/societal results can be explicitly unsupported zeros. The public + synthetic scenario has modeled four-family outputs, but they are still not empirically validated intervention effects.
- Benchmark comparisons should use matched evaluation budgets and distinguish per-seed metrics from final candidates. Larger hypervolume is better; smaller IGD is better. Pooled-reference IGD is approximate. Never present a synthetic winner as proven best for a real institution.

### Global implementation rules (apply to all five prompts)

1. **Do not rewrite the core algorithms or replace the shared evaluator.** Wrap and reuse the existing Python code. Add optional non-invasive diagnostics only when necessary.
2. **Never fabricate data, convergence traces, metrics, uncertainty distributions, or successful executions.** Every chart must be linked to a real saved artifact or a verified new computation. Show a truthful empty state otherwise.
3. **Preserve evidence boundaries** visibly across pages, tooltips, saved runs, and exports; no causal or verified real-world improvement claims from synthetic models.
4. **Do not delete the existing dashboard.** Preserve it as an accessible legacy artifact viewer while introducing a more interactive application.
5. Prefer a maintainable **React + TypeScript** frontend with **ECharts or Plotly** for interactive scientific charts and a **FastAPI** bridge to Python, unless the repository audit demonstrates a better fit. Avoid unnecessary dependencies and duplicate business logic.
6. Give the user a crisp visual experience: light theme, restrained colors, large legible charts, max 1–2 primary plots per view, collapsible technical details, consistent units and legends, accessible interactions, and responsive layout. No excessive gradients or gimmicks.
7. For each phase: implement actual working functionality, create/update tests and docs, run relevant tests/builds, report commands and results, and explicitly list unfinished or unsupported functionality. Do not claim completion merely because the UI renders.
8. Use a small, inexpensive **demo preset** by default; make rigorous repeated benchmarks opt-in. Preserve seeds, configs, model hashes and experiment provenance.

---

## PROMPT 1 OF 5 — Audit, architecture, design system and read-only visual foundation

### Context
We already have a sophisticated backend and a static evidence dashboard. Before introducing execution and simulation, establish a clear architecture, verify the data contracts, and build a visual frontend shell that reads real saved outputs. Existing static pages and Python functionality must continue working.

### Paste into Codex

> You are in the root of the existing Beyond-Ranking repository. Read this `prompts.md`, especially the repository facts and global rules.
>
> **Task:** Audit the existing codebase and implement the frontend foundation without changing optimization mathematics.
>
> 1. Inspect `README.md`, `main.py`, `Makefile`, `department_optimizer/`, `configs/`, the current dashboard, representative saved artifacts, and tests. Create `docs/frontend/ARCHITECTURE.md`, `DATA_CONTRACTS.md`, and `BACKEND_MAPPING.md` describing actual integration points, field semantics, evidence labels, and features not yet executable interactively.
> 2. Choose and justify the frontend setup (prefer React + TypeScript + Vite with ECharts or Plotly). Preserve the old static dashboard at an accessible route or documented URL. Implement reusable components for the app shell, navigation, chart panels, run/evidence labels, metric cards, tooltips, empty/error/loading states, and accessibility.
> 3. Create the following main sections: **Overview**, **Scenario Studio**, **Algorithm Lab**, **Pareto Explorer**, **Robustness Lab**, **Target-Cost Explorer**, **Evidence & Audit**. For now, only fully populate **Overview** with real, read-only saved artifacts; other pages may display clearly marked implementation placeholders until later prompts.
> 4. The Overview should have a snapshot selector (synthetic/public+synthetic/empirical where artifacts exist), a 4-card summary, an uncluttered current-vs-recommended allocation chart, a KPI prediction interval chart, simple constraint/resource indicators, and an explanation of what claims the dataset supports. Do not display unsupported objective dimensions as if they were meaningful scores.
> 5. Implement a robust typed loader/adapter for persisted CSV/JSON files, validating missing values, column names, units, hashes/version metadata, and evidence classifications. Do not introduce hardcoded chart numbers.
> 6. Add responsive styles, chart legends, readable labels, informative tooltips, and simple explanatory text near each graph. Create setup instructions for running the new frontend and old viewer.
> 7. Run build/tests, verify the existing dashboard remains accessible, and fix errors before stopping.
>
> **Limit this phase to audit, foundation and read-only Overview. Do not pretend that editable settings can execute optimization yet.**

### Expected output

- `docs/frontend/ARCHITECTURE.md`, `DATA_CONTRACTS.md`, `BACKEND_MAPPING.md`.
- New frontend app with consistent navigation/design system and an operational artifact-backed Overview.
- Old dashboard preserved and launchable.
- Explicit mappings from each graph to its source file and evidence type.
- Build and smoke-test results, plus a short list of missing execution integrations.

### Acceptance checks

- Overview reads at least one authentic saved artifact collection without mock metrics.
- Evidence lane switching does not show synthetic KPIs as observed performance.
- No Python optimizer files were rewritten.
- `npm run build` (or chosen equivalent) succeeds; old viewer still works.

---

## PROMPT 2 OF 5 — Real simulation API, Scenario Studio and episode/run history

### Context
The current dashboard is read-only. Users now need to modify valid resource-allocation inputs and run backend optimizers. Multiple sets of inputs should become persistent, reproducible **episodes** that users can revisit and compare. A click on **Run** must launch genuine backend work, not generate UI-only simulations.

### Paste into Codex

> Implement end-to-end experiment execution for the new Beyond Ranking frontend, continuing from Prompt 1. Reuse the existing Python evaluators, optimizer adapters and configuration loaders.
>
> **Backend/API:** Introduce a safe local FastAPI service (or equivalently justified architecture) exposing dataset/config discovery, supported variables/constraints, algorithm availability, scenario validation, run submission, run status, run results, artifact metadata and history. Use typed schemas. Accept only allowlisted datasets/configs and validated values; do not expose arbitrary paths or construct untrusted shell commands. Execute longer jobs outside the request lifecycle with a durable local run registry, unique IDs, honest queued/running/completed/failed/cancelled statuses, error logs, output validation, and concurrency limits. Support cancellation safely if feasible; otherwise clearly mark it unavailable.
>
> **Scenario Studio:** Build a guided UI with 4 concise steps: (1) choose evidence lane and scenario, (2) adjust resource inputs and constraints, (3) choose algorithms/seeds/evaluation budgets, (4) review and run. Generate inputs from actual backend variable definitions rather than assuming fixed fields. Provide budget/effort utilization graphics, inline validation, defaults, reset, duplicate and advanced settings. Only allow editable objective weights where the backend gives them real semantics; otherwise make preference selection explicitly a post-optimization strategy filter.
>
> **Execution:** Let users select NSGA-II, NSGA-III, MOEA/D, MOPSO, RION and Random Search where supported. Provide a small-demo preset and separate rigorous preset. Show per-algorithm execution cards, recorded evaluation counts where available, logs, and progress stages. Do not invent percentages if live progress is not emitted. Respect the accounting rules of matched evaluation budgets and hybrid RION evaluations.
>
> **Episodes / Run History:** Persist scenario snapshots, seed(s), selected methods, budgets, evidence labels, model/config hashes, timestamps, status, actual output references and errors. Build run browsing/filtering, rename, duplicate, inspect, rerun and 2–3 run comparison. Show inputs and outcomes side by side using real data. Warn or disable misleading comparisons between incompatible models, objective definitions, datasets or evaluation budgets.
>
> **Technical quality:** Use a single source of truth for serialized configurations, clear API response contracts, and stable persistence across browser refreshes/server restarts. Add integration tests for validation, run lifecycle, failed execution, and a complete small example run. Preserve existing workflows and docs.
>
> Stop only after demonstrating one genuine submitted experiment that reaches verified outputs and appears in Run History.

### Expected output

- Working Python API and documented endpoints.
- Functional Scenario Studio with genuine input editing and backend experiment submission.
- Job processing, status/error/progress display and persistent run metadata.
- Repeatable run/episode history with clone and compare actions.
- One verified small end-to-end optimizer execution with its artifacts.

### Acceptance checks

- Changing a valid input affects a new backend configuration and execution, not merely labels.
- Invalid scenarios fail with actionable errors before execution.
- Refreshing the browser does not erase run history or create fake completed jobs.
- Each run records reproducibility and evidence metadata.

---

## PROMPT 3 OF 5 — Results visualization, algorithm benchmarking, convergence and Pareto explorer

### Context
The backend already exports resource allocations, KPI predictions, constraints, full candidate populations, Pareto archives and repeated benchmark summaries. The UI must make **differences among algorithms and solutions** easy to understand without presenting dozens of charts simultaneously. Some past experiments contain only final populations, so convergence history may be unavailable and must never be fabricated.

### Paste into Codex

> Implement the complete **Results Overview**, **Algorithm Lab**, and **Pareto Explorer** for saved and newly completed runs. Read the contracts and API built in Prompts 1–2; only use genuine backend data.
>
> **Results Overview:** For a selected run/algorithm/candidate, show 4 headline indicators, current-vs-recommended decision bars, KPI before/after dumbbell or paired charts with prediction intervals, resource utilization, feasible/violated constraints, and an expandable technical ledger. Every chart must update consistently when candidate selection changes. Use compatible units and explain the evidence boundary. Connect the candidate to its original run and archived row.
>
> **Algorithm Lab:** Load the existing 25-seed final benchmark from `results/benchmarks/phase6-final-synthetic-25seeds-v1/` alongside any compatible newly created comparisons. Provide algorithm multi-selection and a single metric selector for hypervolume, IGD, spacing, runtime, feasibility, evaluations and unique model calls when present. Show a compact median/IQR leaderboard and an interactive box/strip plot of authentic per-seed observations. Show counts of completed/failed runs. Include Wilcoxon/Holm statistical comparisons only when available and valid; explain nondistinguishable results and approximate pooled-reference IGD. Never label an algorithm universally best from one synthetic benchmark.
>
> **Convergence:** First check whether per-evaluation or per-generation history actually exists. If not, add OPTIONAL, non-invasive progress/checkpoint recording in the backend orchestration (not optimizer mathematics), without changing results, random seeds or evaluation counting. Plot metric versus actual candidate-evaluation count, with seed selection and optional real multi-seed bands. For historical runs without checkpoints show 'History not recorded', not interpolated invented curves. Verify instrumented and noninstrumented runs behave equivalently.
>
> **Pareto Explorer:** Render a zoomable scatter plot of actual candidate solutions; X and Y are user-selectable valid objectives or benefit/cost dimensions. Color by algorithm or scenario; mark feasibility and nondominated solutions correctly. Click a point to open its exact allocation, predicted KPI intervals, constraints, cost, evidence label and provenance. Permit pinning up to 3 actual candidates to compare side by side. Handle duplicate points and missing/unsupported objective families honestly. Do not display an artificial four-dimensional frontier where objectives are unsupported.
>
> **Visual quality:** Each screen answers one headline question. Use clear subtitles, legends, accessible colors, hover help, compact takeaways derived from actual values, and collapsible advanced plots. Default the frontend to the most interpretable view, not all metrics at once.
>
> Add automated tests for metric direction and units, statistical labels, candidate identity, cross-chart selection sync, missing values, and evidence limitations. Verify plotted values against original CSV/JSON artifacts.

### Expected output

- Results page explaining recommended allocation and predicted changes visually.
- Algorithm Lab comparing all available methods with valid per-seed distributions and statistics.
- Genuine convergence plots for newly instrumented runs, honest missing-history states for older runs.
- Interactive Pareto plot, candidate detail drawer and 3-way candidate comparison.
- Test coverage for actual-vs-displayed metrics and chart interactions.

### Acceptance checks

- Picking different algorithms actually changes the source data/plots where results differ.
- No fictitious convergence traces or unsupported dimensions are displayed.
- Clicking a Pareto point shows the exact corresponding archived candidate.
- Median/IQR and per-seed values reconcile with the benchmark files.

---

## PROMPT 4 OF 5 — Robustness, what-if comparisons and target-cost reverse optimization

### Context
Beyond Ranking has uncertainty, robustness, sensitivity and reverse/target-cost workflows. The UI should allow an understandable answer to two distinct questions: **“What happens if assumptions change?”** and **“What is the lowest modeled cost to hit my target?”** Re-evaluating an existing allocation under a shock is not the same as reoptimizing; the interface must keep these operations separate.

### Paste into Codex

> Extend the app with a **Robustness Lab** and **Target-Cost Explorer** using the existing Python workflows and the validated API/runner. Do not implement substitute mathematical logic in JavaScript.
>
> **Robustness Lab:** Read genuine artifacts including `scenario_robustness.csv`, `assumption_sensitivity.csv`, decision sensitivity files and the appropriate scenario manifests. Let users compare a baseline with up to 3 saved or newly computed scenarios: budget adjustments, capacity shocks, policy changes and uncertainty settings only when supported by the selected backend config. Explicitly differentiate (A) viewing saved assessments, (B) stress-testing the same fixed allocation, and (C) reoptimizing in a changed environment. Expose only backend-supported actions.
>
> Visuals should include: scenario outcome grouped dot/bar comparisons, feasibility probability bars with Monte Carlo draw counts, mean/downside/upper percentile indicators, and a ranked sensitivity or tornado plot only where input perturbations are genuinely comparable. Provide simple textual interpretation and a transparent assumptions drawer. Do not invent raw Monte Carlo distributions from stored quantiles.
>
> **Target-Cost Explorer:** Inspect the existing reverse optimization interface and target definition schema. Build a guided input view to choose valid KPI targets, thresholds and conservative lower-bound options when supported. Execute the real target-cost workflow. Show target-vs-achieved bullet charts, recommended minimum modeled cost, allocation bars, feasibility, budget/resource limits and target shortfalls. If no feasible solution is found, show the actual solver status and reasons rather than making a recommendation up. Support viewing existing public-calibrated target-cost examples and comparing two or three verified target settings.
>
> **Integration:** Every simulation or target-cost execution becomes a reproducible episode with configuration, seed, evidence classification, status, model hash, results and provenance. Ensure comparison UI cannot accidentally conflate results across incompatible models or datasets. Provide meaningful loading/failure states and a small compute-efficient test preset.
>
> Test scenario identity, probability bounds, percentile labeling, correct solver statuses, objective support, real backend execution and chart mapping. Update docs and run the relevant checks.

### Expected output

- Functional Robustness Lab with real scenarios, feasibility/uncertainty charts and clearly differentiated reassessment vs reoptimization.
- Functional target-cost input, execution and result visualization.
- Scenario/target history integrated with the existing run registry.
- Backend-backed sensitivity comparisons rather than frontend approximations.
- Tests confirming calculations, labels and failure handling.

### Acceptance checks

- At least one saved and one newly computed robustness/target-cost example can be opened where supported by the backend.
- Raw simulated draws are never inferred from aggregate percentiles.
- Target outputs are checked against real backend recommendation/status files.
- Public descriptive observations are not described as intervention effects.

---

## PROMPT 5 OF 5 — Explanation layer, reproducibility, visual polish, E2E validation and demo mode

### Context
The app must now be something a student can **present and explain** to faculty, while still providing deep technical inspection when asked. The last phase turns functional research visualizations into a coherent walkthrough, removes clutter, verifies every claim and creates a safe way to demo precomputed results if optimization runs are slow.

### Paste into Codex

> Finish Beyond Ranking as a polished, demonstrable **interactive optimization studio**. Audit all work from Prompts 1–4 and fix incomplete, disconnected or misleading UI states rather than adding cosmetic-only features.
>
> **Guided explanation:** Add a short 5-step optional walkthrough: (1) define the problem/resources, (2) choose algorithms and run, (3) inspect a recommendation, (4) compare algorithms and Pareto trade-offs, (5) test robustness/targets. Provide one concise, automatically derived 'What this tells us' note beside each major chart and simple tooltips for DEA, Pareto dominance, hypervolume, IGD, feasibility, uncertainty intervals and statistical comparison. Separate simple explanations from an expandable technical explanation. Do not produce unsupported conclusions.
>
> **Evidence & Audit:** Build an accessible page that shows the dataset/evidence lane, method, provenance, configuration and model hashes, seeds, candidate-evaluation accounting, benchmark reference-front caveats, tests/audit outputs, and verified links/downloads to original experiment artifacts. Preserve distinction between raw observed evidence, synthetic scenario predictions and method-validation results across exports and screenshots.
>
> **Demo mode:** Add an explicitly labeled read-only demonstration mode using existing verified saved runs (including the final 25-seed synthetic benchmark). It must work without rerunning expensive experiments and must not pretend sliders change precomputed results. For an interactive presentation, provide a small valid live-run preset as a separate option. Supply a realistic 5–7 minute demo script explaining which pages to open and which charts to discuss.
>
> **UX polish:** Remove clutter, eliminate unnecessary tables from primary views, ensure chart titles/units/legends and tooltip values are consistent, improve mobile/laptop responsiveness, add keyboard/accessibility basics, error boundaries, loading and empty states, and useful exports (PNG/SVG plots and CSV/JSON only when grounded in real plotted data). Keep multiple comparisons to at most 3 candidates/scenarios by default. Avoid decorative elements that distract from interpreting results.
>
> **Validation:** Execute backend unit/integration tests, API tests, frontend build/tests and browser-level end-to-end flows for: selecting a saved demo, editing a valid scenario, running a small optimizer experiment, comparing two algorithms, inspecting a Pareto point, running a robustness or target-cost example, and opening provenance. Confirm values in visualizations match backend files. Record failures honestly.
>
> **Deliverables:** Add a root-level `DEMO_GUIDE.md`, `FRONTEND_SETUP.md`, and `docs/frontend/FINAL_VALIDATION.md` including commands, test outcomes, remaining limitations and screenshots or reproducible screenshot instructions. Ensure the application is runnable on a local Mac with clear prerequisites and one documented launch workflow. Preserve the legacy read-only viewer.
>
> Stop only after providing a concise implementation summary, test results, limitations, and concrete instructions to run and present the application. If any requested feature is technically unsupported, show the limitation instead of faking it.

### Expected output

- Finished presentation-friendly UI with consistent explainers and evidence labels.
- Evidence & Audit page, downloadable authentic artifacts and provenance.
- Read-only demo mode plus a separate small live simulation path.
- `FRONTEND_SETUP.md`, `DEMO_GUIDE.md`, `docs/frontend/FINAL_VALIDATION.md`.
- Passing builds/tests and a documented, repeatable end-to-end walkthrough.

### Acceptance checks

- A new viewer can understand the basic story without reading raw tables.
- Demonstration is possible using saved data even if a large benchmark takes time.
- Genuine scenario changes produce new real backend runs, while demo snapshots are explicitly static.
- The frontend never overstates causal evidence, statistical significance or algorithm superiority.
- Existing Python workflows and the legacy dashboard remain operational.

---

## Final definition of done

The project is complete when a user can:

1. Select a supported synthetic or public-calibrated scenario and understand its evidence type.
2. Change real supported resource inputs and execute an actual optimization experiment.
3. Save, duplicate, revisit and compare 2–3 distinct input episodes.
4. Compare the six supported algorithms using **real** benchmark metrics and distributions.
5. Inspect a recommended allocation, predicted KPIs, uncertainty and constraints visually.
6. Explore and pin actual Pareto solutions, with each plotted point linked to exact output records.
7. Stress-test assumptions or solve supported KPI target-cost problems without invented numbers.
8. Show a professor a concise, visual demo and open deeper technical/provenance evidence on demand.

**Operational suggestion:** Commit after each prompt with messages such as `frontend: foundation`, `frontend: experiment runner`, `frontend: algorithm and pareto views`, `frontend: robustness and target cost`, and `frontend: validation and demo`.
