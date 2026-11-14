# Beyond Ranking final report source

The submission PDF is compiled from `Beyond_Ranking_Final_Report.tex`. All statistical
figures are regenerated from committed CSV artifacts by `report/generate_report_assets.py`.
The script does not rerun or overwrite optimization experiments.

```bash
.venv/bin/python report/generate_report_assets.py
/Applications/ChatGPT.app/Contents/Resources/tectonic/tectonic Beyond_Ranking_Final_Report.tex
```

Figures are written to `report_assets/figures/`; authentic UI captures are stored in
`report_assets/screenshots/`. Bibliographic metadata is in `references.bib`.

Evidence labels are part of the report contract: legacy benchmark results are synthetic,
VJTI scenario results are public-calibrated plus synthetic, and no optimizer result is
presented as empirical or causal validation.
