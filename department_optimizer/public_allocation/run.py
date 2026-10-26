"""CLI for Prompt 16 four-family VJTI allocation modeling."""

from __future__ import annotations

import argparse

from .workflow import run_public_allocation


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default="configs/public_allocation/vjti_four_family_v1.json"
    )
    args = parser.parse_args(argv)
    result = run_public_allocation(args.config)
    print(f"Four-family allocation complete: {result['output_root']}")
    print(f"Reference feasible: {result['reference_feasible']}")
    print(f"Target-cost recommendations: {result['target_recommendations']}")
    print(f"Checks passed: {result['checks_passed']}")


if __name__ == "__main__":
    main()
