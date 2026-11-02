# Beyond Ranking Evidence Dashboard

Read-only browser for versioned benchmark, scenario, strategy, evidence, and provenance
artifacts produced by the Beyond Ranking optimization workflows.

The dashboard deliberately contains no evaluator or optimization logic. It copies and
renders the existing saved CSV, JSON, and SVG outputs. Synthetic method fixtures,
public-plus-synthetic scenario results, and public empirical evidence are kept in
separate views.

## Refreshing the snapshot

Copy the documented artifacts from the repository into `dist/data/` without changing
their contents. Update the version labels in `dist/app.js` only when a new versioned
artifact package is introduced.

## Local preview

Serve `dist/` with any static HTTP server. Opening `index.html` directly is unsupported
because browser security prevents local `fetch()` calls.
