"""CLI for the Prompt 14 VJTI public-plus-synthetic data package."""

from __future__ import annotations

import argparse

from .workflow import build_public_data_package


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default="configs/data/vjti_public_plus_synthetic_v1.json"
    )
    args = parser.parse_args(argv)
    result = build_public_data_package(args.config)
    print(f"VJTI public-data package complete: {result['output_root']}")
    print(f"Public values: {result['public_value_count']}")
    print(f"Synthetic values: {result['synthetic_value_count']}")
    print(f"Checks passed: {result['checks_passed']}")


if __name__ == "__main__":
    main()
