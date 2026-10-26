# VJTI public-plus-synthetic completion audit

Run the final audit with:

```bash
python -m department_optimizer.audit.public_run --config configs/audit/vjti_public_completion_v1.json
```

The auditor verifies the public snapshot and generated-data hashes, Prompt 14–17
manifest chain, model-file hashes, group split isolation, leakage controls, interval
coverage, synthetic share, VRS DEA formulation, objective signs, units, accounting,
integrality, feasibility, experiment budgets and seed counts, scenario modes, strategy
selection records, statistical-test metadata, report regeneration, and advanced-
extension evidence gates.

For the clean reproduction it copies only source code, the frozen allocation
configuration, and the versioned model bundle to a temporary directory. No prior run
results are copied. It executes NSGA-II and random search with a shared eight-candidate
budget and independently recomputes a selected prediction, every baseline constraint
residual, archive nondominance, hypervolume, and IGD.

Outputs are written to `artifacts/public_audit/vjti_v1/`. The implementation/evidence
matrix deliberately separates software completion from evidence strength. A passing
audit supports the phrase “complete VJTI-calibrated methodological study.” It does not
support empirical optimization, causal effects, institutional efficiency rankings, or
guaranteed ranking improvement.

The retained gaps are substantive rather than test failures: Network DEA needs
observed comparable stage links; multi-period planning needs repeated observed
department decisions, carry-overs, and outcomes; causal validation needs an appropriate
intervention design. The Gaussian-process comparison and dashboard are optional and
were not run.
