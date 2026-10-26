"""Resumable repeated benchmark runner with frozen, matched evaluation budgets."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from department_optimizer.allocation import (
    AllocationProblem,
    CanonicalNSGA2Adapter,
    MOEADAdapter,
    MOPSOAdapter,
    NSGA3Adapter,
    RandomSearchAdapter,
    RionAllocationAdapter,
)
from department_optimizer.allocation.problem import OBJECTIVE_FAMILIES
from department_optimizer.modeling import load_prediction_bundle

from .metrics import hypervolume, igd, nondominated, normalize_objectives, spacing


def _now():
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(_json_safe(payload), indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _adapter(name, settings, seed):
    arguments = {key: value for key, value in settings.items() if key != "enabled"}
    arguments["seed"] = int(seed)
    constructors = {
        "nsga2": CanonicalNSGA2Adapter,
        "nsga3": NSGA3Adapter,
        "moead": MOEADAdapter,
        "mopso": MOPSOAdapter,
        "rion": RionAllocationAdapter,
        "random_search": RandomSearchAdapter,
    }
    if name not in constructors:
        raise ValueError(f"unknown benchmark algorithm: {name}")
    return constructors[name](**arguments)


def _configured_budget(name, settings):
    if name == "random_search":
        return int(settings["evaluations"])
    if name == "rion":
        return int(settings["population_size"]) * (
            1 + int(settings["generations"]) * (int(settings["pso_iterations"]) + 2)
        )
    if name in {"nsga3", "moead"}:
        partitions = int(settings["reference_partitions"])
        objectives = len(OBJECTIVE_FAMILIES)
        population = math.comb(partitions + objectives - 1, objectives - 1)
    else:
        population = int(settings["population_size"])
    return population * (int(settings["generations"]) + 1)


def _validate_config(config):
    if config.get("data_role") not in {"smoke", "final_benchmark"}:
        raise ValueError("data_role must be smoke or final_benchmark")
    seeds = [int(value) for value in config["seeds"]]
    if not seeds or len(seeds) != len(set(seeds)):
        raise ValueError("seeds must be a non-empty unique list")
    target = int(config["evaluation_budget"])
    enabled = {
        name: settings
        for name, settings in config["algorithms"].items()
        if settings.get("enabled", False)
    }
    if not enabled:
        raise ValueError("at least one algorithm must be enabled")
    mismatches = {
        name: _configured_budget(name, settings)
        for name, settings in enabled.items()
        if _configured_budget(name, settings) != target
    }
    if mismatches:
        raise ValueError(f"algorithm budgets do not equal {target}: {mismatches}")
    scaling = config["objective_scaling"]
    if scaling["objective_order"] != list(OBJECTIVE_FAMILIES):
        raise ValueError("objective scaling order differs from the shared evaluator")
    if len(config["hypervolume_reference_point"]) != len(OBJECTIVE_FAMILIES):
        raise ValueError("hypervolume reference point has the wrong dimension")
    return seeds, enabled


def _hardware_metadata():
    import joblib
    import scipy
    import sklearn

    thread_names = [
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ]
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or None,
        "logical_cpu_count": os.cpu_count(),
        "python": sys.version,
        "packages": {
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
            "scikit_learn": sklearn.__version__,
            "joblib": joblib.__version__,
        },
        "thread_environment": {name: os.environ.get(name) for name in thread_names},
    }


def _git_metadata():
    import subprocess

    def command(*arguments):
        result = subprocess.run(
            ["git", *arguments], capture_output=True, text=True, check=False
        )
        return result.stdout.strip() if result.returncode == 0 else None

    return {
        "commit": command("rev-parse", "HEAD"),
        "branch": command("branch", "--show-current"),
        "dirty": bool(command("status", "--porcelain")),
    }


def _run_path(root, algorithm, seed):
    return root / "runs" / algorithm / f"seed_{int(seed)}"


def _execute_one(root, algorithm, settings, seed, problem, config_hash, target, retry_failed):
    directory = _run_path(root, algorithm, seed)
    status_path = directory / "status.json"
    previous = json.loads(status_path.read_text()) if status_path.exists() else {}
    if previous.get("status") == "complete" and previous.get("config_sha256") == config_hash:
        return previous, "skipped_complete"
    if previous.get("status") == "failed" and not retry_failed:
        return previous, "skipped_failed"
    directory.mkdir(parents=True, exist_ok=True)
    attempt = int(previous.get("attempt", 0)) + 1
    base = {
        "algorithm": algorithm,
        "seed": int(seed),
        "attempt": attempt,
        "config_sha256": config_hash,
        "target_candidate_evaluations": target,
        "started_at_utc": _now(),
        "status": "running",
    }
    _write_json(status_path, base)
    started = time.perf_counter()
    try:
        result = _adapter(algorithm, settings, seed).run(problem)
        elapsed = time.perf_counter() - started
        accounting = result.accounting
        actual = int(accounting["candidate_evaluations_total"])
        overshoot = max(0, actual - target)
        if actual < target:
            raise RuntimeError(
                f"{algorithm} consumed {actual} candidate evaluations, below target {target}"
            )
        result.population.to_csv(directory / "population.csv", index=False)
        result.archive.to_csv(directory / "archive.csv", index=False)
        _write_json(directory / "evaluation_accounting.json", accounting)
        complete = {
            **base,
            "status": "complete",
            "completed_at_utc": _now(),
            "runtime_seconds": elapsed,
            "candidate_evaluations": actual,
            "final_batch_overshoot": overshoot,
            "unique_shared_evaluator_calls": int(
                accounting["unique_shared_evaluator_calls_total"]
            ),
            "population_size": len(result.population),
            "archive_size": len(result.archive),
        }
        _write_json(status_path, complete)
        return complete, "executed"
    except Exception as error:
        failed = {
            **base,
            "status": "failed",
            "completed_at_utc": _now(),
            "runtime_seconds": time.perf_counter() - started,
            "error_type": type(error).__name__,
            "error": str(error),
            "traceback": traceback.format_exc(),
        }
        _write_json(status_path, failed)
        return failed, "failed"


def _objective_matrix(frame, objective_order):
    columns = [f"objective__{name}" for name in objective_order]
    if frame.empty:
        return np.empty((0, len(columns)), dtype=float)
    return frame[columns].to_numpy(dtype=float)


def _completed_statuses(root, config_hash, expected_jobs):
    statuses = []
    for path in sorted((root / "runs").glob("*/seed_*/status.json")):
        status = json.loads(path.read_text())
        key = (status.get("algorithm"), int(status.get("seed", -1)))
        if status.get("config_sha256") != config_hash or key not in expected_jobs:
            continue
        status["run_directory"] = str(path.parent)
        statuses.append(status)
    return statuses


def _metric_outputs(root, config, statuses):
    scaling = config["objective_scaling"]
    order = scaling["objective_order"]
    lower = scaling["lower"]
    upper = scaling["upper"]
    reference_point = np.asarray(config["hypervolume_reference_point"], dtype=float)
    pooled = []
    complete = [item for item in statuses if item["status"] == "complete"]
    for item in complete:
        archive = pd.read_csv(Path(item["run_directory"]) / "archive.csv")
        values = _objective_matrix(archive, order)
        if len(values):
            pooled.append(normalize_objectives(values, lower, upper, scaling["clip"]))
    pooled_front = nondominated(np.vstack(pooled)) if pooled else np.empty((0, len(order)))
    columns = [f"normalized_objective__{name}" for name in order]
    pd.DataFrame(pooled_front, columns=columns).to_csv(
        root / "pooled_reference_front.csv", index=False
    )
    front_hash = _sha256(root / "pooled_reference_front.csv")
    _write_json(
        root / "reference_metadata.json",
        {
            "reference_front_version": config["reference_front_version"],
            "sha256": front_hash,
            "construction": "unique nondominated union of all successful benchmark archives",
            "known_limitation": (
                "This is an approximate pooled front. It can favor algorithms represented "
                "in the pool and can improve when additional successful runs are added."
            ),
            "successful_runs_in_pool": len(complete),
            "point_count": len(pooled_front),
            "objective_scaling": scaling,
            "hypervolume_reference_point": reference_point.tolist(),
        },
    )
    rows = []
    for item in statuses:
        row = {
            "algorithm": item["algorithm"],
            "seed": item["seed"],
            "status": item["status"],
            "runtime_seconds": item.get("runtime_seconds"),
            "target_candidate_evaluations": item.get("target_candidate_evaluations"),
            "candidate_evaluations": item.get("candidate_evaluations"),
            "final_batch_overshoot": item.get("final_batch_overshoot"),
            "unique_shared_evaluator_calls": item.get("unique_shared_evaluator_calls"),
            "error": item.get("error"),
            "archive_size": np.nan,
            "feasible_solution_rate": np.nan,
            "hypervolume": np.nan,
            "igd": np.nan,
            "spacing": np.nan,
        }
        if item["status"] == "complete":
            directory = Path(item["run_directory"])
            population = pd.read_csv(directory / "population.csv")
            archive = pd.read_csv(directory / "archive.csv")
            values = normalize_objectives(
                _objective_matrix(archive, order), lower, upper, scaling["clip"]
            )
            row.update(
                archive_size=len(archive),
                feasible_solution_rate=float(population["feasible"].astype(bool).mean()),
                hypervolume=hypervolume(values, reference_point),
                igd=igd(values, pooled_front),
                spacing=spacing(values),
                metric_status="ok" if len(values) else "empty_feasible_archive",
            )
        else:
            row["metric_status"] = "run_failed_or_incomplete"
        rows.append(row)
    metrics = pd.DataFrame(rows).sort_values(["algorithm", "seed"])
    metrics.to_csv(root / "per_seed_metrics.csv", index=False)
    return metrics, front_hash


def _summary(metrics):
    rows = []
    numeric = [
        "hypervolume",
        "igd",
        "spacing",
        "feasible_solution_rate",
        "runtime_seconds",
        "candidate_evaluations",
        "final_batch_overshoot",
        "unique_shared_evaluator_calls",
    ]
    for algorithm, group in metrics.groupby("algorithm"):
        successful = group[group["status"] == "complete"]
        for metric in numeric:
            values = pd.to_numeric(successful[metric], errors="coerce").dropna()
            rows.append(
                {
                    "algorithm": algorithm,
                    "metric": metric,
                    "successful_runs": len(successful),
                    "failed_or_incomplete_runs": len(group) - len(successful),
                    "observations": len(values),
                    "median": values.median() if len(values) else np.nan,
                    "q1": values.quantile(0.25) if len(values) else np.nan,
                    "q3": values.quantile(0.75) if len(values) else np.nan,
                    "iqr": values.quantile(0.75) - values.quantile(0.25)
                    if len(values)
                    else np.nan,
                }
            )
    return pd.DataFrame(rows)


def _holm_adjust(p_values):
    count = len(p_values)
    order = np.argsort(p_values)
    adjusted = np.empty(count, dtype=float)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (count - rank) * p_values[index])
        adjusted[index] = min(1.0, running)
    return adjusted


def _statistics(metrics, minimum_runs):
    from scipy.stats import wilcoxon

    algorithms = sorted(metrics["algorithm"].unique())
    metric_names = ["hypervolume", "igd", "spacing", "feasible_solution_rate"]
    rows = []
    for metric in metric_names:
        metric_rows = []
        for first_index, first in enumerate(algorithms):
            for second in algorithms[first_index + 1 :]:
                left = metrics[(metrics.algorithm == first) & (metrics.status == "complete")][
                    ["seed", metric]
                ]
                right = metrics[(metrics.algorithm == second) & (metrics.status == "complete")][
                    ["seed", metric]
                ]
                paired = left.merge(right, on="seed", suffixes=("_first", "_second")).dropna()
                differences = paired[f"{metric}_first"] - paired[f"{metric}_second"]
                nonzero = differences[differences != 0]
                row = {
                    "metric": metric,
                    "algorithm_first": first,
                    "algorithm_second": second,
                    "paired_runs": len(paired),
                }
                if len(paired) < minimum_runs:
                    row.update(status="not_performed_insufficient_paired_runs")
                elif len(nonzero) == 0:
                    row.update(
                        status="all_paired_differences_zero",
                        p_value=1.0,
                        rank_biserial=0.0,
                    )
                else:
                    statistic = wilcoxon(
                        paired[f"{metric}_first"], paired[f"{metric}_second"],
                        alternative="two-sided", zero_method="wilcox",
                    )
                    ranks = pd.Series(np.abs(nonzero)).rank(method="average").to_numpy()
                    signs = np.sign(nonzero.to_numpy())
                    effect = float(np.sum(ranks * signs) / np.sum(ranks))
                    row.update(
                        status="performed",
                        p_value=float(statistic.pvalue),
                        rank_biserial=effect,
                    )
                metric_rows.append(row)
        performed = [index for index, row in enumerate(metric_rows) if "p_value" in row]
        if performed:
            adjusted = _holm_adjust([metric_rows[index]["p_value"] for index in performed])
            for index, value in zip(performed, adjusted):
                metric_rows[index]["holm_adjusted_p_value"] = value
        rows.extend(metric_rows)
    return pd.DataFrame(rows)


def run_benchmark(config_path: Path, output_root: Path | None = None, retry_failed=False):
    config_path = Path(config_path)
    config = json.loads(config_path.read_text())
    seeds, algorithms = _validate_config(config)
    root = Path(output_root or config["output_root"])
    root.mkdir(parents=True, exist_ok=True)
    config_hash = _sha256(config_path)
    allocation_path = Path(config["allocation_config"])
    allocation = json.loads(allocation_path.read_text())
    model_path = Path(allocation["model_bundle"])
    problem = AllocationProblem(allocation, load_prediction_bundle(model_path))
    model_manifest = json.loads((model_path / "manifest.json").read_text())
    _write_json(root / "benchmark_config_snapshot.json", config)
    _write_json(
        root / "benchmark_manifest.json",
        {
            "benchmark_id": config["benchmark_id"],
            "data_role": config["data_role"],
            "config_path": str(config_path),
            "config_sha256": config_hash,
            "allocation_config": str(allocation_path),
            "allocation_config_sha256": _sha256(allocation_path),
            "model_bundle": str(model_path),
            "model_manifest_sha256": _sha256(model_path / "manifest.json"),
            "model_track_id": model_manifest.get("model_track_id"),
            "model_interface_version": model_manifest.get("interface_version"),
            "data_path": model_manifest.get("data_path"),
            "data_sha256": model_manifest.get("data_sha256"),
            "seeds": seeds,
            "algorithm_implementation_version": "phase5-repository-native-v1",
            "algorithms": algorithms,
            "evaluation_budget": config["evaluation_budget"],
            "budget_definition": config["budget_definition"],
            "hardware": _hardware_metadata(),
            "git": _git_metadata(),
            "created_or_refreshed_at_utc": _now(),
        },
    )
    events = []
    for seed in seeds:
        for algorithm, settings in algorithms.items():
            status, action = _execute_one(
                root, algorithm, settings, seed, problem, config_hash,
                int(config["evaluation_budget"]), retry_failed,
            )
            events.append({"algorithm": algorithm, "seed": seed, "action": action})
    expected_jobs = {(algorithm, seed) for seed in seeds for algorithm in algorithms}
    statuses = _completed_statuses(root, config_hash, expected_jobs)
    pd.DataFrame(statuses).to_csv(root / "run_index.csv", index=False)
    metrics, reference_hash = _metric_outputs(root, config, statuses)
    _summary(metrics).to_csv(root / "summary_median_iqr.csv", index=False)
    _statistics(metrics, int(config["minimum_runs_for_inference"])).to_csv(
        root / "statistical_tests.csv", index=False
    )
    _write_json(
        root / "completion.json",
        {
            "refreshed_at_utc": _now(),
            "configured_jobs": len(seeds) * len(algorithms),
            "complete_jobs": sum(item["status"] == "complete" for item in statuses),
            "failed_jobs": sum(item["status"] == "failed" for item in statuses),
            "events_this_invocation": events,
            "pooled_reference_front_sha256": reference_hash,
        },
    )
    return root


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--retry-failed", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    root = run_benchmark(
        Path(args.config), Path(args.output_root) if args.output_root else None,
        retry_failed=args.retry_failed,
    )
    completion = json.loads((root / "completion.json").read_text())
    print(
        f"Benchmark {root}: {completion['complete_jobs']}/"
        f"{completion['configured_jobs']} complete, {completion['failed_jobs']} failed"
    )


if __name__ == "__main__":
    main()
