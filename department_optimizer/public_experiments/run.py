"""CLI for Prompt 17 VJTI experiments and artifact-only reporting."""

import argparse
import json

from .workflow import run_public_experiments


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/public_experiments/vjti_experiments_v1.json")
    args = parser.parse_args()
    print(json.dumps(run_public_experiments(args.config), indent=2))


if __name__ == "__main__":
    main()
