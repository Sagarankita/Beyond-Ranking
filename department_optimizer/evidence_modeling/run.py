"""CLI for Prompt 15 evidence-aware DEA and KPI models."""

from __future__ import annotations

import argparse

from .workflow import run_evidence_modeling


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default="configs/evidence_modeling/vjti_evidence_models_v1.json"
    )
    args = parser.parse_args(argv)
    result = run_evidence_modeling(args.config)
    print(f"Evidence-aware modeling complete: {result['output_root']}")
    print(f"DEA solves: {result['dea_successful_solves']}/{result['dea_dmu_count']}")
    print(f"Synthetic KPI models: {result['trained_kpis']}")
    print(f"Checks passed: {result['checks_passed']}")


if __name__ == "__main__":
    main()
