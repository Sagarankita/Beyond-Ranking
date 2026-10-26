"""CLI for the VJTI public-plus-synthetic completion audit."""

import argparse
import json

from .public_completion import run_public_audit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    print(json.dumps(run_public_audit(args.config, args.output), indent=2))


if __name__ == "__main__":
    main()
