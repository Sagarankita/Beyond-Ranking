# Optional Network DEA and multi-period planning assessment

Run:

```bash
python -m department_optimizer.extensions.run --config configs/extensions/evidence_assessment.json
```

This evidence gate checks the audited dataset before either advanced extension is implemented. Network DEA requires documented comparable decision-making units plus observed stage inputs, intermediate links, and final outputs. Multi-period planning requires stable unit identifiers, at least two ordered observed periods per unit, documented resource carry-over, per-period constraints, and outcome lags.

The current file contains 521 synthetic institution-like rows. It has no observed stage-link variables and no period column. Its row identifier does not turn the cross-section into a verified peer cohort or longitudinal panel. Network DEA and multi-period planning are therefore both deferred. The assessment records the missing fields and evidence needed to resume.

No synthetic stage links or repeated pseudo-periods are generated. Doing so would manufacture the assumptions that these methods are intended to analyze.
