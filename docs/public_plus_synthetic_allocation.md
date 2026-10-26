# Four-family public-plus-synthetic allocation model

Prompt 16 extends the shared repair, feasibility, and evidence contract to the VJTI
baseline and Prompt 15 KPI bundle:

```sh
make public-allocation
```

The evaluator enables research, innovation, student development, and societal
contribution. It stores raw KPI predictions and intervals, component normalization and
weights, constraint residuals, support warnings, and synthetic coverage. All modeled
responses remain `synthetic_scenario`; public placement evidence may define a target but
does not turn its modeled response into observed or causal evidence. DEA remains
descriptive context and is never used as a multiplier.

The allocation uses total—not incremental—semantics on an FY2023-24 nominal INR basis.
It accounts for direct funding, research-assistant unit costs, compute unit costs, three
faculty-effort categories, integer decisions, service floors, and funding dependencies.
Patent and compute responses use versioned local scenario adjustments centered on the
Prompt 14 reference.

Target-cost results are separate:

- `public_informed_student_targets` uses public descriptive placement/higher-study rates
  as its target basis while retaining synthetic response labels;
- `scenario_four_family_targets` uses generator-supported scenario thresholds.

Every saved recommendation is independently evaluated against the same constraints.
Unsupported objective families fail during configuration, before any optimization.
