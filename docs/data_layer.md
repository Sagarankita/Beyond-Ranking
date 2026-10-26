# Data layer and Phase 1 contract

Prompt 03 separates the committed legacy synthetic fixture from future observed records.
The source of truth for machine-readable field definitions is
`department_optimizer/data/schemas.py`; a complete JSON dictionary is emitted by the
audit command as `artifacts/data_audit/legacy_synthetic/data_dictionary.json`.

## Named schemas

| Schema | Observation unit | Purpose |
| --- | --- | --- |
| `observed_department_period` | CE/IT department and reporting period | Historical inputs, fixed context, and measured outcomes used for prediction |
| `institutional_peer_benchmark` | Institution and reporting period | Comparable public peer records used for benchmarking, not department-level labels |
| `current_allocation` | CE/IT department and reporting period | Documented present allocation used as the decision baseline |
| `synthetic_scenario_record` | Synthetic scenario record | Explicitly assumed pipeline/scenario data with generator lineage |
| `legacy_synthetic_research` | Synthetic institution-like row | Unmodified 521-row fixture for legacy optimizer smoke tests |

Every canonical record identifies its source, period, provenance (`observed`, `derived`,
`assumed`, or `synthetic`), and imputation status. Monetary values require INR and a base
year. Fields are classified as identifiers, metadata, controllable decisions, fixed
context, outcomes, or evaluation indicators. Column order has no meaning.

Validation reports missing/non-finite values, invalid units/categories, fractional counts,
duplicate primary keys, cross-source conflicts, and schema range errors. Scenario-policy
bounds are a separate warning layer: historical values are reported and never clipped,
coerced, reordered, or imputed by validation.

## Existing CSV audit

`data/department_research_data.csv` has 521 records and 15 fields. Its values reproduce
the seed-42 formulas in `data/datagen.py` to floating-point round-trip precision. It is
therefore classified as synthetic. It is not a department-period panel and must not be
used as empirical evidence about VJTI CE/IT or other institutions.

The legacy policy-bound comparison reports two types of mismatch without editing data:
teaching load exceeds the old upper bound of 15 in some rows, and synthetic rank exceeds
the old upper bound of 200 in many rows. These mismatches show why historical/data-valid
ranges and future decision-policy ranges must remain separate.

Run the reproducible audit with:

```sh
make data-audit
```

It writes the dataset hash, validation report, generator check, EDA summary, schema
dictionary, and objective inventory under `artifacts/data_audit/legacy_synthetic/`.

## Objective evidence inventory

| Objective family | Current evidence status | Consequence |
| --- | --- | --- |
| Research impact | Synthetic only | Usable for pipeline tests; not an empirical intervention model |
| Innovation | Unsupported | Need patent, industry-project, or technology-transfer outcomes |
| Student development | Unsupported | Need participation, projects, placements, or higher-study outcomes |
| Societal contribution | Unsupported | Need open-access, SDG, outreach, or societal-impact outcomes |
| Efficiency benchmarking | Scenario/method fixture only | Need a comparable observed peer cohort before DEA interpretation |

No missing objective labels are synthesized. Until observed records exist, the proposal's
four-objective result remains a methodological scenario track.

## Allocation and scenario contract

`configs/scenarios/baseline.synthetic.json` freezes an illustrative decision vector with:

- seven direct INR funding categories;
- integer research-assistant and compute-capacity quantities with unit costs;
- research, student-support, and service effort in annual faculty FTE;
- total-allocation semantics, a budget capacity, a faculty-time capacity, and minimum
  service commitments.

Each cost-bearing variable has one cost mode and a unique cost key. Direct-money variables
cannot also define unit costs, which prevents the same expenditure being counted through
two representations. Incremental scenarios must name their current-allocation baseline.
The example values are assumptions, not current CE/IT data, and its response model is
explicitly marked unavailable.

## Synthetic generation

The refactored generator has no import-time side effects and accepts a JSON config, seed,
record count, and output path:

```sh
make generate-synthetic
python data/datagen.py --seed 7 --n-records 100 --output /tmp/scenario.csv
```

New outputs include provenance, seed, generator version, response-model identifier, period,
and imputation fields, plus a separate assumptions JSON. `--legacy-columns-only` exists
only to reproduce the old fixture shape. The committed fixture is never overwritten by
the default generator path.

## Records still needed

Before empirical DEA, prediction, or allocation recommendations, obtain and document:

- CE/IT department-period faculty counts/FTE, teaching and service commitments, research
  and activity-level spending, RA/support counts, compute capacity, and a current allocation;
- publications/Q1 outputs with documented matching, normalized citations, collaborations,
  patents/applications, industry projects, and technology-transfer outcomes;
- student research participation/projects, placements, higher studies, and societal/open-
  access/SDG/outreach outcomes with stable definitions and time lags;
- comparable institution-period peer inputs/outputs from public ranking releases and
  institutional annual/research reports, keeping institutional rows separate from CE/IT;
- currency/base-year conversions, source URLs or document identifiers, access dates,
  coverage, missingness, and derivation/imputation logs.

Departmental records may require institutional permission. No private access is assumed,
and external bibliometric records should be used only with documented coverage and entity
matching. Data acquisition status is currently `not provided in repository`.
