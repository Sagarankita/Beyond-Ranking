# Frontend architecture

## Purpose

The supported frontend is a read-only Streamlit evidence browser for versioned outputs
already produced by the Department Resource Allocation Optimizer. It validates saved
artifacts, adapts reporting schemas, and renders comparisons with explicit evidence
boundaries. It does not optimize, repair candidates, predict KPIs, or duplicate the
Python evaluator.

The application lives in `streamlit_app/`. The deprecated React/Vite implementation
remains in `frontend/` for one rollback release. The original static evidence dashboard
remains independently runnable from `sites/beyond-ranking-evidence-dashboard/dist/`.

## Runtime shape

Streamlit is the Python presentation server. It reads the original repository files
directly; there is no copied dataset and no separate read API.

1. `streamlit_app/data/catalog.json` provides the committed allow-list, source path,
   byte count, units, required columns, numeric columns, SHA-256 digest, version,
   evidence class, and claim boundary.
2. `streamlit_app/data/loaders.py` resolves each path inside the repository root,
   recomputes its hash, checks its byte count, parses UTF-8 CSV/JSON, and validates the
   declared contract.
3. Evidence-specific adapters convert validated rows into one common Overview model.
4. Streamlit components render Plotly charts, native metrics and progress indicators,
   explicit empty/error states, and downloads of the exact validated bytes.

```text
Python workflows and shared evaluator
             |
             v
versioned CSV / JSON / SVG artifacts
             |
             v
committed allow-list + hashes + evidence metadata
             |
             v
Python validation and read-only adapters
             |
             v
Streamlit views and validated downloads
```

## Application sections

- **Overview** is populated with authentic saved artifacts.
- **Scenario Studio** is a non-executable Prompt 2 placeholder.
- **Algorithm Lab** and **Pareto Explorer** are Prompt 3 placeholders.
- **Robustness Lab** and **Target-Cost Explorer** are Prompt 4 placeholders.
- **Evidence & Audit** is a Prompt 5 placeholder.

Placeholders contain no control that implies a backend run occurred.

## Source structure

- `streamlit_app/app.py` configures the application and native multipage navigation.
- `streamlit_app/data/types.py` defines evidence, catalog, artifact, and Overview models.
- `streamlit_app/data/contracts.py` validates paths, required values, finite numbers,
  explicit booleans, versions, and evidence classes.
- `streamlit_app/data/catalog.py` owns the source allow-list and explicit refresh command.
- `streamlit_app/data/loaders.py` verifies SHA-256/byte count before parsing.
- `streamlit_app/data/adapters.py` isolates the three evidence lanes.
- `streamlit_app/components/` contains Plotly and Streamlit presentation components.
- `streamlit_app/pages/` contains Overview and future-section placeholders.
- `streamlit_app/tests/` covers contracts, hashes, adapters, and an application smoke run.

## Evidence isolation

Evidence is separated by complete snapshot:

- `synthetic_method_fixture` is for method validation only.
- `public_plus_synthetic_scenario` combines a public-calibrated baseline with synthetic,
  noncausal intervention responses.
- `empirical_descriptive` contains observed or derived public evidence and exposes no
  optimizer strategy, recommendation, modeled utilization, candidate constraint, or
  intervention-response interval.

A snapshot selection replaces the whole view model and claim boundary. The application
has no operation that merges evidence lanes.

## No second evaluator

Constraint residuals, objective values, KPI predictions, uncertainty intervals,
allocations, and costs come from saved artifacts. The only UI threshold is the documented
reporting interpretation `residual <= 1e-9` for the VJTI constraints file, which has no
persisted boolean pass field. Streamlit never repairs a vector or recreates feasibility
math.

Future execution must call the existing Python workflow and shared evaluator, then save
a versioned result package before the UI renders it. Long optimizer work must never run
inside Streamlit's rerender loop.

## Caching and deployment

Only the fully adapted read-only Overview is cached, keyed by snapshot ID and catalog
modification time. Session state contains view selections only. Deployments must mount
or package `artifacts/`, `results/`, and the catalog as read-only inputs.

The legacy static viewer remains available through `make legacy-dashboard`; Streamlit's
sidebar documents the local URL. It is not embedded and has no dependency on Streamlit.

## Accessibility and resilience

- Streamlit's native navigation, selects, expanders, and downloads remain keyboard
  reachable.
- Charts have textual headings, descriptions, legends, and exact-value tooltips.
- Mixed-unit allocation bars are normalized only for layout; exact values keep units.
- Missing, malformed, non-finite, path-escaping, byte-count-mismatched, hash-mismatched,
  empty, or invalid artifacts render an error instead of a partial chart.
- Analytical columns collapse through Streamlit's responsive layout on narrow screens.

## Test boundary

Frontend tests cover contract failures, boolean parsing, path confinement, hash mismatch,
every allow-listed saved package, adapter parity, empirical/synthetic separation, and a
Streamlit `AppTest` smoke run. Existing Python reporting and allocation tests remain the
authority for optimizer behavior.
