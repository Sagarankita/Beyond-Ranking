"""Evaluate a reproducible reference candidate through the shared allocation problem."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from department_optimizer.modeling import load_prediction_bundle

from .problem import AllocationProblem, OBJECTIVE_FAMILIES


def _sha256(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_fixture(config_path: Path, output_dir: Path):
    config = json.loads(config_path.read_text())
    model_path = Path(config["model_bundle"])
    model = load_prediction_bundle(model_path)
    problem = AllocationProblem(config, model)
    reference = config["reference_allocation"]["values"]
    result = problem.evaluate(reference)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "problem_id": config["problem_id"],
        "evidence_status": config["evidence_status"],
        "reference_status": config["reference_allocation"]["status"],
        "config_path": str(config_path),
        "config_sha256": _sha256(config_path),
        "model_bundle": str(model_path),
        "model_manifest_sha256": _sha256(model_path / "manifest.json"),
        "evaluation": result.to_dict(),
    }
    (output_dir / "reference_evaluation.json").write_text(
        json.dumps(payload, indent=2) + "\n"
    )
    definitions = {
        "objective_direction": "minimize",
        "objective_order": list(OBJECTIVE_FAMILIES),
        "families": config["objective_families"],
        "constraint_residual_convention": "residual <= 0 is satisfied; positive values are violations",
        "normalized_violation": "sum(max(0, residual) / declared constraint scale)",
        "cost_policy": "hard constraint and reporting field; not an objective",
        "dea_policy": config["dea_reporting"],
        "unsupported_decisions": config["unsupported_decisions"],
    }
    (output_dir / "objective_definitions.json").write_text(
        json.dumps(definitions, indent=2) + "\n"
    )
    return payload


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default="configs/allocation/legacy_synthetic_method_fixture.json"
    )
    parser.add_argument("--output-dir", default="artifacts/allocation/shared_evaluator")
    return parser.parse_args()


def main():
    args = parse_args()
    payload = run_fixture(Path(args.config), Path(args.output_dir))
    evaluation = payload["evaluation"]
    print(f"Evaluated {payload['problem_id']}")
    print(f"Nominal feasible: {evaluation['nominal_feasible']}")
    print(f"Normalized violation: {evaluation['normalized_violation']:.6g}")
    print(f"Cost: {evaluation['cost']:.2f}")
    print(f"Outputs: {args.output_dir}")


if __name__ == "__main__":
    main()
