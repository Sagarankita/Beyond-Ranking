# Frontend data contracts

## Contract principles

Only allow-listed, versioned repository artifacts may enter the UI. Every file is
described by a committed catalog entry containing its repository-relative path,
format, byte count, SHA-256 digest, required columns, numeric columns, and units where
applicable.

The Streamlit loader rejects a snapshot when:

- its catalog schema version is unsupported;
- its snapshot ID is duplicated;
- its evidence class is unknown;
- version or claim-boundary metadata is missing;
- a requested file cannot be loaded;
- a file's recomputed SHA-256 differs from the catalog;
- JSON parsing fails;
- a CSV has no rows, lacks a required column, contains a missing required value, or
  contains a non-finite value in a numeric column; or
- a required boolean is not one of `true`, `false`, `1`, `0`, `yes`, or `no`.

Validation occurs before adaptation and rendering.

## Catalog schema

`streamlit_app/data/catalog.json` has `schemaVersion: 1`, a description, and
a non-empty `snapshots` array. Each snapshot includes:

- stable `id`, display `label`, and artifact `version`;
- one of the three supported `evidenceClass` values;
- an `evidenceLabel` and plain-language `claimBoundary`;
- `supportsInterventionClaims`, currently false for every available snapshot; and
- a list of file definitions.

Each file definition has a stable `id`, repository-relative source path, `csv` or
`json` format, SHA-256 digest, and byte count. CSV definitions can additionally declare
required and numeric columns plus field-unit metadata.

## Synthetic method fixture

Snapshot ID: `synthetic-phase7-v1`

Evidence class: `synthetic_method_fixture`

Source package: `results/reporting/phase7-synthetic-v1/`

The Overview reads these saved reporting outputs:

- `manifest.json` supplies the report identity.
- `current_vs_strategy_allocations.csv` supplies `strategy`, `variable`, `unit`,
  `current`, `recommended`, and `difference`. Values use the row's declared unit.
- `current_vs_strategy_kpis.csv` supplies current and recommended predictions with lower
  and upper bounds. Units are KPI-specific.
- `resource_utilization.csv` supplies cost and budget in INR plus research effort and
  capacity in FTE.
- `constraint_checks.csv` supplies named residuals and the reporting layer's persisted
  boolean `passed` value.
- `strategy_portfolio.csv` supplies selected rows, allocation groups, cost, feasibility,
  and saved research benefit. It is used for summary counts, not reevaluation.

The synthetic fixture supports method demonstration, not institutional or causal
claims. Unsupported innovation, student, and societal scores are not promoted as
meaningful KPI outcomes.

## Public-calibrated synthetic scenario

Snapshot ID: `vjti-public-synthetic-v1`

Evidence class: `public_plus_synthetic_scenario`

Source packages:

- `artifacts/public_experiments/vjti_v1/`
- `artifacts/evidence_modeling/vjti_v1/kpi_evidence_registry.csv`

The Overview reads:

- `experiment_manifest.json` for comparison-run and matched-evaluation counts;
- `strategy_allocations.csv` for saved current and policy decision values;
- `strategy_kpis.csv` for saved predictions and lower/upper intervals;
- `strategy_resource_summary.csv` for INR cost, INR budget remaining, and allocated FTE;
- `strategy_constraints.csv` for named raw and normalized residuals; and
- `kpi_evidence_registry.csv` for status and claim boundaries.

Decision values use decision-specific units. Fields whose name contains `funding` or
`support` are labeled INR; other decisions retain the conservative label “configured
decision unit” until the source publishes an explicit unit column. Faculty effort is
shown as an absolute FTE value because this package does not record a compatible total
capacity in the same summary artifact.

The baseline uses public evidence, while intervention responses remain synthetic,
associational, and noncausal.

## Empirical descriptive evidence

Snapshot ID: `vjti-empirical-v1`

Evidence class: `empirical_descriptive`

Source packages:

- `artifacts/public_data/vjti_ceit_v1/`
- `artifacts/public_experiments/vjti_v1/public_only_sensitivity.csv`
- `artifacts/evidence_modeling/vjti_v1/kpi_evidence_registry.csv`

The Overview reads provenance coverage, source registration, saved public-only
denominator sensitivity checks, and KPI evidence classifications. It reports observed
and derived coverage counts and the number of registered sources.

This lane intentionally has no strategies, allocation comparisons, modeled utilization,
candidate constraints, or KPI response intervals. The count of empirical optimizer runs
is explicitly zero. Public outcome values are descriptive and cannot be presented as
effects of a proposed allocation.

## Hash and version semantics

Hashes are calculated from exact file bytes by the explicit catalog refresh command.
Streamlit verifies the hash and byte count before decoding or parsing. Line-ending or
content changes invalidate the digest and require a reviewed `make frontend-catalog`.
Scientific versions are inherited from the saved package and remain visible in the UI.

## Missing values and units

Required empty cells are errors. Optional blank cells remain blank and must be handled
by a view-specific adapter; they are never automatically converted to zero. Numeric
columns must parse to finite Python floats. `NaN`, positive or negative infinity,
and empty strings are rejected.

The UI does not aggregate incompatible units. Allocation bar lengths are normalized
within each decision solely for comparison, while tooltips show exact saved values and
units. KPI intervals are likewise normalized per KPI for drawing, with exact predictions
and bounds in tooltips.

## Provenance downloads

Every file backing the selected Overview snapshot appears in the provenance disclosure
with its original repository path and abbreviated SHA-256. The download link returns the
exact validated source bytes used for the current visualization.
