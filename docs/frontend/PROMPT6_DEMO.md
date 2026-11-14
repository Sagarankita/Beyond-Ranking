# Prompt 6 professor-facing demo record

Date: 2026-11-13

This record documents the final local browser walkthrough against the real FastAPI and
Streamlit services. It is not a research result.

## Walkthrough

1. Loaded the configured reference scenario. The Overview identified it as public plus
   synthetic and did not label it as observed current spending.
2. Opened Resource Planner, changed available budget from INR 36 million to INR 30
   million, changed faculty capacity from 15 to 16 annual FTE, selected NSGA-II seed
   19601, and ran the fixed 16-candidate interactive budget.
3. The service returned run `55ffd6fe94b0e50b52aa4475`, scenario hash
   `932523073df9503ebf4d406cde25ef59601ed9a79766ba1ed535057e6054338d`, and four
   independently revalidated feasible strategies. The selected plan displayed exact
   budget, faculty use, objective scores, 34 of 34 named constraints passed, and nine
   stored KPI intervals.
4. Opened Improvement Advisor. The balanced profile traced candidate
   `3555079c2d1ab7bd9df16502` through 12 exact decision changes, four objective-family
   trade-offs, uncertainty, constraint evidence, and stable recommendation identity.
5. Requested optional Groq wording. The local semantic validator rejected an
   unsupported claim and safely displayed deterministic wording. Structured actions,
   values, feasibility, and charts remained unchanged.
6. Changed the budget factor from INR 30 million to INR 31 million. The controlled
   diagnostic used the same NSGA-II method, seed 19601, and 16 evaluations. The UI kept
   the held-fixed no-repair assessment separate from the reoptimized scenario and
   labeled both as modeled, non-causal sensitivity.
7. Verified the professor-facing Markdown export control after recommendation and
   sensitivity rendering.
8. Opened Experiment Lab. It displayed 150 of 150 completed jobs, six algorithms, 25
   matched seeds, and 100 evaluations per job. Hypervolume distributions contained all
   saved seed points. The paired-statistics view offered only metrics with performed
   tests and showed Wilcoxon p values, Holm-adjusted p values, and rank-biserial effects.
   The current interactive run remained in a separate panel.
9. Opened Evidence & Assumptions. The Evidence map showed zero complete comparable
   public DMUs against twelve required and separately labeled the 30-unit synthetic DEA
   fixture. The KPI tab showed the selected model, three-model test comparison, training
   support ranges, and all nine interval-calibration checks. The robustness tab showed
   held-fixed and reoptimized feasibility frequencies as separate series across five
   saved scenarios. The audit tab exposed the versioned checks and provenance downloads.
10. Returned to Resource Planner, entered INR 1 million and 10 annual FTE, and validated
    the scenario. The UI blocked the run and displayed field-specific lower-bound errors:
    budget must be at least INR 8.7 million and faculty capacity at least 11 annual FTE.

## Automated verification

```bash
.venv/bin/python -m unittest discover -s streamlit_app/tests -v
.venv/bin/python -m compileall -q streamlit_app
git diff --check
```

Result before the final selector correction: 48 tests passed. The affected Experiment
Lab UI test was rerun after the correction and passed. The complete suite is rerun as
the final release check.

## Remaining evidence limitations

- Allocation responses and KPI relationships are synthetic or public-calibrated plus
  synthetic, not causal effects.
- Public DEA remains blocked by insufficient comparable complete DMUs.
- The one-period public evidence package is not a longitudinal intervention panel.
- Interactive runs are not added to the completed matched-seed benchmark.
- Optional native OpenMP RION was not built in the reported workspace.
