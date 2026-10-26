"""Small clean-workspace reproduction used only by the VJTI completion audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from department_optimizer.allocation import CanonicalNSGA2Adapter, RandomSearchAdapter
from department_optimizer.benchmark.metrics import hypervolume, igd, nondominated
from department_optimizer.public_allocation.problem import FAMILIES, VJTIPublicAllocationProblem


def run(config_path, model_root, output_root, seed=18001, evaluations=8):
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    problem = VJTIPublicAllocationProblem(config, model_root)
    output = Path(output_root)
    output.mkdir(parents=True, exist_ok=True)
    baseline = problem.evaluate_fixed(config["reference_allocation"])
    (output / "baseline_evaluation.json").write_text(
        json.dumps(baseline.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    adapters = {
        "nsga2": CanonicalNSGA2Adapter(population_size=4, generations=1, seed=seed),
        "random_search": RandomSearchAdapter(evaluations=evaluations, seed=seed),
    }
    frames, records = [], []
    for name, adapter in adapters.items():
        result = adapter.run(problem)
        run_root = output / "runs" / name
        run_root.mkdir(parents=True, exist_ok=True)
        result.population.to_csv(run_root / "population.csv", index=False)
        result.archive.to_csv(run_root / "archive.csv", index=False)
        (run_root / "accounting.json").write_text(
            json.dumps(result.accounting, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if len(result.archive):
            frames.append(result.archive)
        records.append({"algorithm": name, "candidate_evaluations": result.accounting["candidate_evaluations_total"],
                        "population_rows": len(result.population), "archive_rows": len(result.archive)})
    columns = [f"objective__{name}" for name in FAMILIES]
    pooled_values = np.vstack([frame[columns].to_numpy(float) for frame in frames])
    reference_front = nondominated(pooled_values)
    pd.DataFrame(reference_front, columns=columns).to_csv(output / "pooled_reference_front.csv", index=False)
    metric_rows = []
    for record in records:
        archive = pd.read_csv(output / "runs" / record["algorithm"] / "archive.csv")
        points = archive[columns].to_numpy(float) if len(archive) else np.empty((0, 4))
        metric_rows.append({**record, "hypervolume": hypervolume(points, np.full(4, 0.05)),
                            "igd": igd(points, reference_front)})
    pd.DataFrame(metric_rows).to_csv(output / "metrics.csv", index=False)
    (output / "reproduction_manifest.json").write_text(json.dumps({
        "seed": seed, "evaluation_budget": evaluations, "algorithms": list(adapters),
        "evidence_scope": "small public-plus-synthetic software reproduction; not empirical validation"
    }, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--model-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=18001)
    parser.add_argument("--evaluations", type=int, default=8)
    args = parser.parse_args()
    run(args.config, args.model_root, args.output, args.seed, args.evaluations)


if __name__ == "__main__":
    main()
