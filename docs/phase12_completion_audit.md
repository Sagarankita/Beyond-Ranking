# Phase 12 completion audit

Run the final audit with:

```bash
python -m department_optimizer.audit.run --config configs/audit/phase12.json
```

The auditor checks source and artifact existence, the data hash chain, synthetic provenance, target-leakage exclusions, model/version/uncertainty metadata, algorithm coverage, matched evaluation accounting, archive feasibility and integrality, objective signs, nondominance, independently recomputed benchmark metrics, scenario coverage, common uncertainty draws, fixed-versus-reoptimized separation, report source hashes, strategy duplicate disclosure, and constraint checks.

It copies the required source, configuration, data, and model files into a temporary workspace without existing results. There it executes a new two-algorithm small benchmark and independently recomputes hypervolume through inclusion-exclusion and IGD through direct distance calculation. The reproduction and metric comparison are saved under `results/audit/phase12-small-reproduction/`.

The optional native backend is checked separately against the existing compiled library when present. An absent optional library is recorded as a gap and does not invalidate the serial workflow. The complete unit-test suite is also executed as part of the audit.

Statuses have distinct meanings:

- `pass`: directly supported by a successful check or artifact.
- `fail`: evidence contradicts the implementation claim or a required check failed.
- `gap`: configured, optional, unsupported, or unevidenced work that must not be described as complete.

The completion matrix verifies the executed 25-seed final synthetic benchmark,
including full algorithm/seed coverage, matched evaluation accounting, and independent
hypervolume/IGD recomputation. It must continue to retain unavailable empirical
departmental evidence and unsupported patent/compute decisions as gaps or limited-scope
statuses. A completed synthetic benchmark does not convert these limitations into
empirical claims.
