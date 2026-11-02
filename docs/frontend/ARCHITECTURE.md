# Frontend architecture

## Purpose

The frontend is a read-only evidence browser for versioned outputs already produced by
the Department Resource Allocation Optimizer. It does not optimize, repair candidates,
predict KPIs, or duplicate the Python evaluator. Its job is narrower: validate saved
artifacts, adapt their reporting schemas, and render comparisons with explicit evidence
boundaries.

The React application lives in `frontend/`. The original static evidence dashboard is
preserved in `sites/beyond-ranking-evidence-dashboard/dist/` and is copied to
`frontend/public/legacy/` during development and production builds.

## Runtime shape

The application is a static Vite build. It requires no backend service for Prompt 1.

1. `frontend/scripts/sync-artifacts.mjs` copies an allow-listed set of repository
   artifacts into the build's public data directory.
2. The sync records the source path, byte count, units, required columns, numeric
   columns, SHA-256 digest, version, evidence class, and claim boundary in
   `data/catalog.json`.
3. The browser loads the catalog, verifies the catalog schema, downloads the selected
   artifact set, recomputes each SHA-256 digest, and validates the CSV/JSON contract.
4. Evidence-specific adapters convert validated rows into the common Overview view
   model. They do not alter optimizer results.
5. React components render the normalized model with ECharts, accessible HTML, and
   explicit empty/error/loading states.

This boundary is intentional:

```text
Python workflows and shared evaluator
             |
             v
versioned CSV / JSON / SVG artifacts
             |
             v
build-time allow-list + hashes + evidence metadata
             |
             v
browser validation and read-only adapters
             |
             v
React views and downloadable provenance
```

## Application sections

- **Overview** is implemented in Prompt 1. It shows saved allocation comparisons, KPI
  intervals, utilization, constraints, evidence boundaries, and downloadable source
  artifacts.
- **Scenario Studio** is reserved for Prompt 2 and is visibly non-executable now.
- **Algorithm Lab** and **Pareto Explorer** are reserved for Prompt 3.
- **Robustness Lab** and **Target-Cost Explorer** are reserved for Prompt 4.
- **Evidence & Audit** is reserved for Prompt 5.

Unimplemented sections are honest placeholders. They never imply that a scenario or
optimizer action has executed.

## Source structure

- `src/data/types.ts` defines evidence, catalog, artifact, and Overview view-model types.
- `src/data/csv.ts` parses quoted CSV fields, escaped quotes, and embedded line breaks.
- `src/data/contracts.ts` validates evidence classes, versions, required columns,
  missing values, finite numeric values, and explicit booleans.
- `src/data/loaders.ts` fetches files and verifies SHA-256 integrity before parsing.
- `src/data/adapters.ts` maps the three evidence lanes to a shared Overview model.
- `src/components/` contains presentation components and ECharts views.
- `src/pages/` contains the populated Overview and future-section placeholders.
- `scripts/sync-artifacts.mjs` is the only build-time artifact allow-list.

## Evidence isolation

Evidence is separated by snapshot, not merely by a decorative badge.

- `synthetic_method_fixture` is for method validation only.
- `public_plus_synthetic_scenario` combines a public-calibrated baseline with synthetic,
  noncausal intervention responses.
- `empirical_descriptive` contains observed or derived public evidence and deliberately
  exposes no optimizer strategies, allocation recommendation, KPI response interval,
  resource utilization, or candidate constraints.

The browser has no operation that merges these lanes. A snapshot change replaces the
entire loaded artifact set and its claim boundary.

## No second evaluator

Constraint residuals, objective values, KPI predictions, uncertainty intervals,
allocations, and costs are read from saved reporting artifacts. The only frontend
threshold is the already documented reporting interpretation `residual <= 1e-9` for
the VJTI constraints file, whose schema does not include a separate boolean pass field.
The frontend never repairs a decision vector or recreates feasibility math.

Future interactive execution must call the existing Python workflows and shared
allocation evaluator in `department_optimizer/allocation/problem.py` or the public VJTI
workflow in `department_optimizer/public_allocation/problem.py`. It must return a saved,
versioned result package before the UI renders it.

## Deployment and routing

Vite uses a relative base so the production bundle works under a subpath or a static
file host. Navigation uses URL hashes and therefore needs no server-side route rewrite.
The legacy viewer is linked at `./legacy/index.html` in the production bundle.

For a future service-backed deployment, keep the artifact catalog as the response
contract. Add an API that lists immutable packages and returns package files by ID;
do not expose raw filesystem paths and do not move evaluation logic into TypeScript.

## Accessibility and resilience

- Navigation, controls, details, and retry actions are keyboard reachable.
- Focus states are visible and reduced-motion preferences are respected.
- Charts have textual headings, descriptions, exact-value tooltips, and surrounding
  evidence context.
- Mixed-unit allocations are normalized only for bar length; exact saved values and
  units remain in tooltips.
- Missing, malformed, non-finite, hash-mismatched, empty, and network-failed artifacts
  render an explicit error rather than a plausible-looking chart.
- Mobile navigation becomes a dismissible drawer and analytical grids collapse to one
  column.

## Test boundary

Frontend unit tests cover CSV quoting, schema failures, numeric validation, evidence
classification, explicit booleans, and empirical/synthetic separation. The production
build runs artifact synchronization, TypeScript checking, and Vite bundling. Existing
Python reporting and allocation tests remain the authority for optimizer behavior.
