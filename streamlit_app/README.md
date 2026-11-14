# Streamlit Department Decision Studio

The supported professor-facing dashboard for saved evidence and validated live
optimization runs.

```bash
python -m pip install -r requirements-ui.txt
python -m streamlit run streamlit_app/app.py --server.address 127.0.0.1 --server.port 8501
```

Start the live-run API separately:

```bash
python -m uvicorn streamlit_app.api.app:app --host 127.0.0.1 --port 8000
```

The API validates allowlisted scenario changes, runs one approved optimizer with the
frozen 16-evaluation interactive budget, persists run state, and independently
revalidates feasible archive candidates. See `docs/frontend/API.md` for endpoints and
failure behavior.

The application has six routes: Department Overview, Resource Planner, Department
Improvement Advisor, Strategy Comparison, Experiment Lab, and Evidence & Assumptions.
Overview, Planner, Advisor, and Strategy Comparison are live. The Advisor applies
deterministic profile rules to revalidated candidates, exposes exact facts, and can run
one-factor matched-method sensitivity cases. Its optional Groq integration rewrites an
allowlisted fact packet only after an explicit explanation request. It cannot select a
candidate, calculate values, invoke an optimizer, or change structured facts. Invalid,
unsupported, or unavailable provider output falls back to deterministic wording. The
research and evidence routes expose only data already supported by the API.

Experiment Lab renders all 150 saved per-seed benchmark records, median and IQR
summaries, paired Wilcoxon tests, rank-biserial effects, and Holm-adjusted p values.
Evidence & Assumptions exposes the public and synthetic DEA boundary, source and data
registers, nine KPI model comparisons and interval checks, saved held-fixed versus
reoptimized robustness assessments, and the public audit checks. The Advisor can export
a deterministic professor-facing Markdown summary with exact facts and reproduction
identity.

Configure the optional server-side wording provider in the repository-root `.env`:

```dotenv
GROQ_API_KEY=your_server_side_key
LLM_EXPLANATIONS_ENABLED=true
GROQ_MODEL=openai/gpt-oss-20b
```

Omit the key or set `LLM_EXPLANATIONS_ENABLED=false` to keep the Advisor fully
rule-based. Restart the API after changing these settings.

Streamlit calls the API over HTTP. It does not execute an optimizer, repair candidates,
or duplicate evaluator math. Restart both services after changing Python source files.

Run tests with:

```bash
python -m unittest discover -s streamlit_app/tests -v
```

Refresh the integrity catalog only after intentionally reviewing changed versioned
artifacts:

```bash
python -m streamlit_app.data.catalog --write
```
