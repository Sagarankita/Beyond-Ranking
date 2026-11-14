# Dashboard live-run API

The FastAPI service in `streamlit_app/api/` is a thin orchestration layer around
`VJTIPublicAllocationProblem` and the six existing optimizer adapters. It does not
duplicate repair, scoring, constraints, KPI prediction, or Pareto logic.

## Start

```bash
make frontend-install PYTHON=.venv/bin/python
make frontend-api PYTHON=.venv/bin/python
```

Base URL: `http://127.0.0.1:8000`

## Operations

- `GET /health`: service health.
- `GET /config/defaults`: validated VJTI defaults, units, provenance, presets, and
  supported algorithms.
- `POST /scenarios/validate`: validate budget, faculty supply, and monetary cost
  multipliers without running an optimizer.
- `POST /runs`: submit one real interactive run.
- `GET /runs/{run_id}`: read persisted status, phase, errors, and result summary.
- `POST /runs/{run_id}/retry`: retry a failed or restart-interrupted run.
- `GET /runs/{run_id}/candidates`: fetch independently revalidated feasible archive
  candidates.
- `GET /runs/{run_id}/recommendations`: retrieve deterministic strategy profiles,
  exact action deltas, objective changes, signed constraint margins, uncertainty, and
  provenance. No LLM is called.
- `GET /explanations/status`: report whether optional explanation wording is enabled
  and provider-configured without exposing credentials.
- `POST /runs/{run_id}/explanations`: request plain-language wording for one
  recommendation that belongs to the completed run. This is the only user action that
  can trigger the optional provider.
- `POST /runs/{run_id}/sensitivity`: change exactly one supported factor and launch a
  matched-method reoptimization using the baseline algorithm, seed, and evaluation
  budget.
- `GET /runs/{run_id}/sensitivity/{sensitivity_run_id}`: retrieve separate held-fixed
  and reoptimized assessments for a completed controlled factor case.
- `POST /comparisons`: compare two candidates from the same run with exact units.
- `GET /benchmarks/final`: retrieve the separate completed 150-job synthetic benchmark,
  including per-seed metrics, median/IQR summaries, paired statistical tests, metric
  definitions, and implementation-grounded algorithm explanations.
- `GET /evidence/summary`: retrieve public and synthetic evidence gates, source and data
  registers, audit checks, nine-KPI model and interval records, support ranges, and saved
  held-fixed versus reoptimized robustness assessments.

## Allowed live inputs

- total budget in INR;
- total faculty supply in annual FTE;
- cost multipliers from 0.1 to 10 for existing monetary decision variables.

Arbitrary fields, changed units, model edits, objective edits, and unknown decisions are
rejected. Interactive runs currently use the frozen 16-candidate evaluation budget
from `configs/public_experiments/vjti_experiments_v1.json`.

## Persistence and identity

Run IDs are stable hashes of the scenario hash, algorithm, seed, evaluation budget,
and service protocol version. Identical active or completed submissions return the
same run ID and are not launched twice.

Each run directory contains:

- `request.json`;
- `scenario_config.json`;
- `status.json`;
- `population.csv`;
- `archive.csv`;
- `evaluation_accounting.json`;
- `candidates.json`; and
- `manifest.json`.

Controlled factor cases also persist `sensitivity_context.json` in the changed run and
a matching record under the baseline run's `sensitivities/` directory.

## Deterministic recommendation profiles

The service applies the documented weighted-utility rules to the feasible archive:

- balanced compromise;
- research focused;
- innovation focused;
- student focused; and
- conservative-service feasible, when supported.

Profile results disclose when two rules select the same candidate. Recommendation
facts include stable IDs, exact variable changes and units, budget effects, nominal and
conservative-service feasibility as separate values, objective deltas on the defined
normalized scale, signed actionable-constraint margins, support warnings, and stored
KPI intervals. Missing reference data or an empty valid candidate set produces
`no_supported_recommendation`.

Sensitivity results never merge assessment modes. `held_fixed_without_repair` evaluates
the original selected allocation unchanged under the new factor. `reoptimized` is a
new matched-method search. Neither result is described as causal.

The service reports real phases only: `queued`, `optimization`, `revalidation`,
`complete`, or `failed`. It does not emit estimated percentages. If the process restarts
during a run, the persisted state becomes `interrupted` and can be retried explicitly.

## Optional explanation wording

`streamlit_app/api/explanations.py` contains the isolated wording service.
`GroqExplanationProvider.generate` is the only production network call site. It is
called after deterministic recommendation selection and never from an optimizer,
evaluator, repair, revalidation, or sensitivity loop.

The provider receives only the selected preference profile, modeled objective
directions, the synthetic evidence boundary, and permitted fact IDs. It does not
receive arbitrary provenance text, raw saved artifacts, exact quantities, credentials,
or tools. Groq strict structured output enforces the six-field response shape, field
lengths, list sizes, and permitted source-ID enum before local semantic checks for
source IDs, quantities, actions, feasibility claims, unsupported causal
claims, evidence-boundary wording, and disallowed punctuation.

Successful output is cached by scenario, candidate, complete structured-fact hash,
schema version, and language. Safe audit metadata records provider, model, validator
result, timestamp, and content hash. Provider errors, timeouts, disabled configuration,
missing credentials, malformed JSON, stale cache entries, and validation failures all
return deterministic rule-based wording. Structured fields remain authoritative in
every mode.

## Evidence boundary

All live results are public-calibrated plus synthetic scenario outputs. They are not
causal estimates or empirically validated VJTI policy effects. The completed 25-seed
benchmark remains separate from interactive runs.
