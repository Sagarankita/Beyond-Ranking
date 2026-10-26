# VJTI public evidence and calibrated fallback

Prompt 14 is implemented as a declarative, reproducible data package. Run:

```sh
make public-data
```

The reviewed extraction configuration is
`configs/data/vjti_public_plus_synthetic_v1.json`. It records every query, successful
and unsuccessful retrieval, source authority and scope, page/table references,
derivations, units, calibration assumptions, bounds, correlations, and sensitivity
ranges. Raw downloads under `data/raw/public/vjti_v1/` are never modified by the
workflow; their SHA-256 hashes are written to the source register and manifest.

## Evidence boundary

The public search found department-level evidence for CE&IT programme capacity, the
current regular-faculty roster, and 2023-24 Computer/IT placement and higher-study
counts. VJTI NIRF records provide institute-level student, expenditure, patent,
sponsored-research, and consultancy values. Those institute totals remain institution
records and are used only as calibration targets. They are never presented as observed
department values. COEP's NIRF submission is retained as one public peer record, not an
adequate DEA cohort.

No public department-period panel was found for budgets, faculty effort, research and
innovation outputs, research participation, open access, or outreach. The workflow
therefore labels these fields `synthetic_calibrated`. It preserves public cells when a
synthetic field has the same unit/period/field key.

## Outputs

The generated package under `artifacts/public_data/vjti_ceit_v1/` includes:

- machine-readable search and source registers with immutable hashes;
- public value extraction and source-to-field traceability;
- data dictionary, conversions, missingness, and duplicate/conflict reports;
- separate public-only, synthetic-only, and merged long-form views;
- a synthetic current allocation that reconciles to its declared budget;
- coverage by field, row, period, and objective family;
- fixed-seed assumptions and realism/accounting checks;
- a readiness report and hash manifest.

The synthetic generator uses a one-period budget lag for research output, explicit
capacity bounds, correlated response formulas, and fixed seeds. Reproduction with the
same seed and distinction under an alternate seed are tested. All outputs remain
scenario data; they do not establish causal or observed departmental improvement.
