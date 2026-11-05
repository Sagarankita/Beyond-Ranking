# React-to-Streamlit frontend migration plan

> **Implementation status (2026-11-04):** Complete for the read-only migration
> scope. Streamlit is now the default dashboard, the Overview is backed by validated
> saved artifacts, prompts 2–5 remain clearly non-executable placeholders, and the
> React/Vite viewer is retained as a deprecated one-release fallback.

## Objective

Replace the current React/Vite dashboard with a Python Streamlit application while
preserving the behavior and scientific boundaries already established by the frontend:

- read only from versioned, saved CSV/JSON artifacts;
- keep synthetic, public-plus-synthetic, and empirical evidence in separate lanes;
- reuse the existing reporting definitions and Python evaluator outputs;
- never implement optimizer, prediction, repair, constraint, Pareto, or robustness math
  in the UI;
- retain hashes, versions, units, claim boundaries, empty/error/loading states, and
  downloadable provenance; and
- keep the original static artifact viewer available during and after migration.

This is a presentation-layer migration, not a backend or model rewrite.

## Recommended target structure

```text
streamlit_app/
  app.py                         # Streamlit entry point and page registration
  pages/
    overview.py                  # First fully populated page
    scenario_studio.py           # Honest placeholder until backend execution exists
    algorithm_lab.py
    pareto_explorer.py
    robustness_lab.py
    target_cost_explorer.py
    evidence_audit.py
  components/
    allocation_chart.py
    evidence.py
    intervals.py
    metrics.py
    provenance.py
    states.py
  data/
    adapters.py                  # Evidence-lane-specific view-model adapters
    catalog.py                   # Catalog creation/loading and path allow-list
    contracts.py                 # Validation and typed domain models
    loaders.py                   # CSV/JSON loading and SHA-256 checks
    types.py                     # Dataclasses/enums for UI-facing models
  styles/
    app.css
  static/
    legacy/                      # Optional build copy of the existing static viewer
  tests/
    test_adapters.py
    test_app.py
    test_contracts.py
    test_loaders.py
.streamlit/
  config.toml                    # Theme and optional static serving configuration
requirements-ui.txt
```

Keep `department_optimizer/` unchanged. The Streamlit package may import shared,
side-effect-free reporting constants if they already exist, but it must not call an
optimizer during normal page rendering.

## Technology choices

- Use Streamlit's multipage navigation API for the seven existing sections.
- Use Plotly for allocation and KPI interval charts because it supports responsive
  layouts, exact-value tooltips, accessible text labels, and point selection without a
  JavaScript build step.
- Use Python `dataclasses`, `Enum`, `pathlib`, `hashlib`, pandas, and explicit validation
  functions for the data contract. Avoid introducing a web API solely for the read-only
  dashboard.
- Use `st.cache_data` only for pure file reads keyed by path, modification time, expected
  hash, and schema version. Do not cache mutable optimizer state.
- Use Streamlit session state only for UI selections such as snapshot, strategy, and
  active comparison—not as the source of scientific results.
- Put UI-only dependencies in `requirements-ui.txt` so optimizer installations can stay
  minimal. Pin compatible version ranges and commit the resolved environment policy.

## Data and evaluator boundary

The saved artifacts remain the source of truth. The Streamlit app must preserve these
three evidence classes exactly:

1. `synthetic_method_fixture` — methodology demonstration only.
2. `public_plus_synthetic_scenario` — public-calibrated baseline with synthetic,
   noncausal intervention responses.
3. `empirical_descriptive` — observed or derived public evidence with no empirical
   optimizer recommendation.

The UI may format, filter, normalize chart coordinates, and calculate display-only
counts. It must not:

- recompute objective values, KPI predictions, intervals, feasibility, dominance,
  hypervolume, robustness, or target cost;
- repair a candidate allocation;
- convert an optional missing value into zero;
- combine incompatible units on one numeric scale; or
- display synthetic output as empirical evidence.

For the VJTI constraint file, the existing reporting interpretation
`residual <= 1e-9` may remain a display rule only because the artifact lacks a persisted
boolean pass field. Document it beside the visualization.

## Migration phases

### Phase 0 — freeze the current behavior

- Record screenshots and a short acceptance checklist for all three Overview snapshots.
- Save the current React test/build results and the legacy viewer readiness check.
- Treat `docs/frontend/DATA_CONTRACTS.md` and `BACKEND_MAPPING.md` as migration inputs.
- Do not delete or edit the React implementation in this phase.

Exit criteria:

- Expected metrics, strategy counts, evidence labels, source-file counts, and empty
  states are recorded for comparison.
- Existing unrelated modified artifacts remain untouched.

### Phase 1 — build the Python contract layer

- Port `frontend/scripts/sync-artifacts.mjs` into a Python catalog builder with the same
  explicit source allow-list.
- Port the TypeScript catalog/evidence types to Python dataclasses and enums.
- Implement safe repository-relative path resolution; reject paths outside the repository
  and never accept a raw path from a browser query parameter.
- Verify SHA-256 before parsing every artifact.
- Validate catalog version, evidence class, duplicate IDs, required columns, required
  values, finite numeric values, explicit booleans, units, and JSON shape.
- Port the three Overview adapters without changing their claim boundaries.
- Add pytest parity tests using the same fixture cases as the current Vitest suite.

Exit criteria:

- Malformed, empty, non-finite, hash-mismatched, and evidence-misclassified artifacts
  fail with a typed, user-safe error.
- Adapter outputs match the current React view models for all three saved snapshots.
- No evaluator or optimizer module is invoked by loader tests.

### Phase 2 — implement the Streamlit shell

- Add the seven-page navigation structure and repository branding.
- Recreate the responsive light theme in `.streamlit/config.toml` and a small scoped CSS
  file; avoid brittle selectors tied to generated Streamlit class names.
- Add a persistent read-only notice and an evidence badge/claim boundary on every page.
- Implement reusable loading, error, warning, empty, and unavailable components.
- Add an explicit link or documented command for the preserved static legacy viewer.
- Keep the six not-yet-implemented pages as non-executable placeholders.

Exit criteria:

- Navigation works with keyboard and browser back/forward behavior.
- Placeholder pages have no control that implies a backend run occurred.
- The app works at desktop, tablet, and narrow mobile widths without horizontal overflow.

### Phase 3 — reach Overview feature parity

- Add snapshot and saved-strategy selectors.
- Render the four summary metrics from the adapted view model.
- Recreate current-versus-recommended allocation bars. Normalize only for display and
  show exact saved values and units in tooltips.
- Recreate KPI prediction intervals with exact current/recommended estimates and bounds.
- Render budget/FTE utilization only when the artifact provides a compatible limit;
  otherwise show the saved absolute value.
- Render named constraint residuals and persisted/display pass status.
- Add claim-support cards and explicit unsupported/unavailable states.
- Add provenance disclosure with source path, hash, byte count, and `st.download_button`
  for the exact validated file bytes.

Exit criteria:

- Synthetic and mixed snapshots match the current dashboard's saved values.
- The empirical snapshot visibly reports zero optimizer runs and contains no allocation,
  modeled utilization, constraint, or intervention-response chart.
- Downloads hash to the value displayed in the provenance panel.

### Phase 4 — testing, accessibility, and operational hardening

- Use pytest for contract/adapter tests and Streamlit `AppTest` for page smoke tests,
  selector changes, empty states, and validation errors.
- Add an integration test that loads every catalog snapshot and verifies every source
  hash and required schema.
- Test a deliberately corrupted copy and confirm the app shows an error rather than a
  partial chart.
- Verify headings, labels, contrast, keyboard navigation, focus visibility, chart text,
  and reduced-motion behavior where applicable.
- Confirm that rendering the app makes no writes under `artifacts/` or `results/`.
- Run the existing reporting and public-experiment Python tests to confirm there was no
  evaluator regression.

Exit criteria:

- Streamlit tests, artifact-contract tests, and the selected existing Python tests pass.
- Browser console/server logs have no errors during all snapshot and page transitions.
- Dependency audit reports no known critical production vulnerability.

### Phase 5 — switch the default frontend

- Add Make targets:
  - `frontend-install`: install `requirements-ui.txt`;
  - `frontend-dev`: run `streamlit run streamlit_app/app.py`;
  - `frontend-test`: run the Streamlit/contract pytest suite;
  - `frontend-build` should be removed or renamed because Streamlit has no static build.
- Update the root README and frontend architecture documents with Streamlit commands,
  expected port, environment variables, and deployment notes.
- Change local/deployment entry points only after parity acceptance.
- Keep the React frontend for one release as a fallback, clearly marked deprecated.
- After the fallback window, remove React source, `package.json`, `package-lock.json`,
  Vite/TypeScript configuration, generated Node artifacts, and npm-specific Make targets
  in a dedicated cleanup commit.
- Keep `sites/beyond-ranking-evidence-dashboard/` unless a separate decision explicitly
  retires the legacy viewer.

Exit criteria:

- A clean checkout can start the dashboard using only the documented Python commands.
- No npm/Node installation is needed for the default frontend.
- Rollback consists only of restoring the previous entry point; no artifact conversion
  is required.

## React-to-Streamlit feature mapping

- `AppShell.tsx` becomes Streamlit page registration, sidebar navigation, header, and
  shared theme helpers.
- `OverviewPage.tsx` becomes `streamlit_app/pages/overview.py`.
- React metric cards become `st.metric` inside responsive `st.columns`.
- ECharts allocation and interval components become Plotly figures rendered with
  `st.plotly_chart(..., use_container_width=True)`.
- React resource/constraint indicators become native Streamlit containers, progress
  bars, status chips, and data frames with formatted residuals.
- React `<details>` provenance becomes `st.expander` plus download buttons.
- React loading/error/empty components become `st.status`, `st.spinner`, `st.error`,
  `st.warning`, and shared empty-state helpers.
- Hash-based page navigation becomes Streamlit's native multipage navigation.
- Browser-side `crypto.subtle` hash verification becomes Python `hashlib.sha256` over the
  exact bytes sent to the download button.

## Documentation updates

Revise these files during implementation:

- `README.md` — Streamlit install/run/test commands and legacy viewer command.
- `docs/frontend/ARCHITECTURE.md` — Python runtime, caching, navigation, and deployment.
- `docs/frontend/DATA_CONTRACTS.md` — unchanged scientific contract, new Python types.
- `docs/frontend/BACKEND_MAPPING.md` — Streamlit page/module mapping.
- Replace or archive `frontend/README.md` after the fallback window.

Add a short troubleshooting section covering port conflicts, missing UI dependencies,
artifact hash mismatches, and running from a non-repository working directory.

## Deployment notes

- Start with a single-process read-only deployment. The application has no database and
  should not persist user session state.
- Mount or package the versioned artifacts read-only.
- Resolve the repository root from the application file, not the current shell working
  directory.
- Disable telemetry if project policy requires it and bind only to the intended interface.
- If later prompts add genuine execution, place it behind a separate validated service
  or job boundary. Do not run long optimizer work synchronously in the Streamlit render
  loop.

## Risks and mitigations

- **Streamlit reruns can repeat expensive reads.** Cache only validated immutable file
  loads using the expected hash in the cache key.
- **Session state can look like durable run state.** Label it as a view selection only;
  genuine runs must produce versioned backend artifacts.
- **Custom CSS can break across Streamlit upgrades.** Prefer native components and style
  stable application-owned wrappers only.
- **Chart parity may drift.** Compare exact tooltip values and evidence labels against the
  recorded React acceptance fixtures, not screenshots alone.
- **Removing React too early weakens rollback.** Run both implementations in parallel
  until the Streamlit acceptance checklist passes.
- **Static legacy hosting differs from Streamlit routing.** Preserve the standalone
  `make legacy-dashboard` path even if a copied legacy link is also exposed.

## Definition of done

The migration is complete when:

- Streamlit is the documented and deployed default dashboard;
- all seven sections exist, with Overview fully populated and future sections honestly
  scoped to their implementation phase;
- the three evidence lanes are impossible to confuse in navigation, labels, or data;
- every rendered value traces to a validated saved artifact and can be downloaded with
  matching provenance;
- the UI contains no duplicate evaluator or optimizer implementation;
- Streamlit contract, integration, and accessibility smoke tests pass;
- selected existing reporting/evaluator tests still pass;
- the original static viewer remains accessible; and
- React/Node files are removed only after the agreed fallback period in a separate,
  reviewable cleanup commit.
