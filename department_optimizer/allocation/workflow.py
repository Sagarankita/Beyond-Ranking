"""Configuration-driven end-to-end allocation optimization workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn

from department_optimizer.modeling import load_prediction_bundle

from .optimizers import CanonicalNSGA2Adapter, RionAllocationAdapter
from .advanced_optimizers import (
    MOEADAdapter,
    MOPSOAdapter,
    NSGA3Adapter,
    RandomSearchAdapter,
)
from .problem import AllocationProblem


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


def _git_metadata():
    def command(*args):
        result = subprocess.run(
            ["git", *args], capture_output=True, text=True, check=False
        )
        return result.stdout.strip() if result.returncode == 0 else None

    status = command("status", "--porcelain")
    return {
        "commit": command("rev-parse", "HEAD"),
        "branch": command("branch", "--show-current"),
        "dirty": bool(status),
    }


def _unique_run_directory(root: Path, prefix: str, seed: int):
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid.uuid4().hex[:8]
    path = root / f"{timestamp}_{prefix}_seed{seed}_{suffix}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def _independent_feasibility_check(problem, archive):
    records = []
    for index, row in archive.iterrows():
        allocation = {name: row[name] for name in problem.variable_names}
        checked = problem.evaluate(allocation)
        repair_unchanged = all(
            np.isclose(allocation[name], checked.repaired[name])
            for name in problem.variable_names
        )
        passed = bool(
            repair_unchanged
            and checked.nominal_feasible
            and checked.normalized_violation <= 1e-12
        )
        records.append(
            {
                "archive_row": int(index),
                "repair_unchanged": repair_unchanged,
                "nominal_feasible": checked.nominal_feasible,
                "robust_feasible": checked.robust_feasible,
                "normalized_violation": checked.normalized_violation,
                "passed": passed,
            }
        )
    result = pd.DataFrame(
        records,
        columns=[
            "archive_row",
            "repair_unchanged",
            "nominal_feasible",
            "robust_feasible",
            "normalized_violation",
            "passed",
        ],
    )
    if len(result) == 0:
        raise RuntimeError("optimizer returned no feasible nondominated recommendations")
    if not result["passed"].all():
        raise RuntimeError("an archived recommendation failed independent feasibility checking")
    return result


def _comparison_rows(problem, reference, algorithm, recommendation):
    rows = []
    for name in problem.variable_names:
        rows.append(
            {
                "algorithm": algorithm,
                "category": "allocation",
                "metric": name,
                "reference": reference.repaired[name],
                "recommendation": float(recommendation[name]),
                "difference": float(recommendation[name]) - reference.repaired[name],
            }
        )
    fields = {
        "cost": reference.cost,
        "research_fte": problem._research_fte(reference.repaired),
        "papers_t1": reference.raw_kpis["papers_t1"],
        "citation_percentile_avg": reference.raw_kpis["citation_percentile_avg"],
        "research_benefit": reference.objective_benefits["research"],
    }
    recommendation_fields = {
        "cost": recommendation["cost"],
        "research_fte": problem._research_fte(recommendation),
        "papers_t1": recommendation["kpi__papers_t1"],
        "citation_percentile_avg": recommendation["kpi__citation_percentile_avg"],
        "research_benefit": recommendation["objective_benefit__research"],
    }
    for name, reference_value in fields.items():
        rows.append(
            {
                "algorithm": algorithm,
                "category": "outcome",
                "metric": name,
                "reference": reference_value,
                "recommendation": float(recommendation_fields[name]),
                "difference": float(recommendation_fields[name]) - reference_value,
            }
        )
    return rows


def _write_report(path, config, problem, reference, summaries):
    lines = [
        "# Small synthetic allocation workflow",
        "",
        "This run is a methodological fixture based on synthetic data. The configured current allocation is illustrative, not observed.",
        "",
        f"Reference spending is INR {reference.cost:,.0f}, with predicted papers {reference.raw_kpis['papers_t1']:.2f} "
        f"and citation percentile {reference.raw_kpis['citation_percentile_avg']:.4f}.",
        "",
        "## Recommendations",
        "",
    ]
    for summary in summaries:
        recommendation = summary["recommendation"]
        recommendation_effort = problem._research_fte(recommendation)
        reference_effort = problem._research_fte(reference.repaired)
        lines.extend(
            [
                f"### {summary['algorithm'].upper()}",
                "",
                f"The run returned {summary['archive_size']} independently checked feasible nondominated allocations. "
                f"The displayed research-first recommendation spends INR {recommendation['cost']:,.0f}, predicts "
                f"{recommendation['kpi__papers_t1']:.2f} papers "
                f"[{recommendation['lower__papers_t1']:.2f}, {recommendation['upper__papers_t1']:.2f}] and citation percentile "
                f"{recommendation['kpi__citation_percentile_avg']:.4f} "
                f"[{recommendation['lower__citation_percentile_avg']:.4f}, {recommendation['upper__citation_percentile_avg']:.4f}].",
                "",
                f"Relative to the illustrative reference, spending rises by INR {recommendation['cost'] - reference.cost:,.0f} "
                f"and modeled research effort rises from {reference_effort:.2f} to {recommendation_effort:.2f} FTE. "
                f"The allocation uses {recommendation['centres_of_excellence_count']:.0f} centres and "
                f"{recommendation['industry_collaboration_support_count']:.0f} collaboration supports.",
                "",
            ]
        )
    lines.extend(
        [
            "## Interpretation limits",
            "",
            "Only the research objective has a supported synthetic response model. Innovation, student, and societal scores are explicit unsupported zeros, so this run does not establish a four-way empirical trade-off. Model intervals describe synthetic-fixture predictive residuals and do not establish causal effects. DEA remains separate.",
            "",
        ]
    )
    path.write_text("\n".join(lines))


def run_workflow(config_path: Path, output_root: Path | None = None):
    started = datetime.now(timezone.utc)
    workflow_config = json.loads(config_path.read_text())
    seed = int(workflow_config["seed"])
    allocation_path = Path(workflow_config["allocation_config"])
    allocation_config = json.loads(allocation_path.read_text())
    model_path = Path(allocation_config["model_bundle"])
    model = load_prediction_bundle(model_path)
    problem = AllocationProblem(allocation_config, model)
    root = Path(output_root or workflow_config["output_root"])
    run_dir = _unique_run_directory(root, workflow_config["run_id_prefix"], seed)
    (run_dir / "workflow_config.json").write_text(
        json.dumps(workflow_config, indent=2) + "\n"
    )
    (run_dir / "allocation_config.json").write_text(
        json.dumps(allocation_config, indent=2) + "\n"
    )
    reference = problem.evaluate(allocation_config["reference_allocation"]["values"])
    (run_dir / "reference_evaluation.json").write_text(
        json.dumps(
            {
                "status": allocation_config["reference_allocation"]["status"],
                "evaluation": reference.to_dict(),
            },
            indent=2,
        )
        + "\n"
    )

    adapters = []
    nsga_config = workflow_config["algorithms"].get("nsga2", {})
    if nsga_config.get("enabled"):
        adapters.append(
            CanonicalNSGA2Adapter(
                population_size=nsga_config["population_size"],
                generations=nsga_config["generations"],
                seed=seed,
            )
        )
    nsga3_config = workflow_config["algorithms"].get("nsga3", {})
    if nsga3_config.get("enabled"):
        adapters.append(
            NSGA3Adapter(
                reference_partitions=nsga3_config["reference_partitions"],
                generations=nsga3_config["generations"],
                seed=seed,
            )
        )
    moead_config = workflow_config["algorithms"].get("moead", {})
    if moead_config.get("enabled"):
        adapters.append(
            MOEADAdapter(
                reference_partitions=moead_config["reference_partitions"],
                neighborhood_size=moead_config["neighborhood_size"],
                max_replacements=moead_config["max_replacements"],
                generations=moead_config["generations"],
                seed=seed,
            )
        )
    mopso_config = workflow_config["algorithms"].get("mopso", {})
    if mopso_config.get("enabled"):
        adapters.append(
            MOPSOAdapter(
                population_size=mopso_config["population_size"],
                generations=mopso_config["generations"],
                archive_size=mopso_config["archive_size"],
                inertia=mopso_config["inertia"],
                cognitive=mopso_config["cognitive"],
                social=mopso_config["social"],
                maximum_velocity_rate=mopso_config["maximum_velocity_rate"],
                seed=seed,
            )
        )
    rion_config = workflow_config["algorithms"].get("rion", {})
    if rion_config.get("enabled"):
        adapters.append(
            RionAllocationAdapter(
                population_size=rion_config["population_size"],
                generations=rion_config["generations"],
                pso_iterations=rion_config["pso_iterations"],
                seed=seed,
            )
        )
    random_config = workflow_config["algorithms"].get("random_search", {})
    if random_config.get("enabled"):
        adapters.append(
            RandomSearchAdapter(
                evaluations=random_config["evaluations"],
                seed=seed,
            )
        )
    if not adapters:
        raise ValueError("at least one allocation algorithm must be enabled")

    comparison = []
    summaries = []
    for adapter in adapters:
        result = adapter.run(problem)
        algorithm_dir = run_dir / adapter.name
        algorithm_dir.mkdir()
        result.population.to_csv(algorithm_dir / "population.csv", index=False)
        result.archive.to_csv(algorithm_dir / "pareto_archive.csv", index=False)
        check = _independent_feasibility_check(problem, result.archive)
        check.to_csv(algorithm_dir / "feasibility_check.csv", index=False)
        (algorithm_dir / "evaluation_accounting.json").write_text(
            json.dumps(result.accounting, indent=2) + "\n"
        )
        recommendation = result.archive.sort_values(
            ["objective__research", "cost"], kind="stable"
        ).iloc[0]
        comparison.extend(
            _comparison_rows(problem, reference, adapter.name, recommendation)
        )
        summaries.append(
            {
                "algorithm": adapter.name,
                "population_size": len(result.population),
                "archive_size": len(result.archive),
                "all_recommendations_independently_feasible": bool(check["passed"].all()),
                "accounting": result.accounting,
                "recommendation": recommendation.to_dict(),
            }
        )
    pd.DataFrame(comparison).to_csv(run_dir / "reference_comparison.csv", index=False)
    _write_report(run_dir / "report.md", workflow_config, problem, reference, summaries)
    completed = datetime.now(timezone.utc)
    metadata = {
        "run_directory": str(run_dir),
        "started_at_utc": started.isoformat(),
        "completed_at_utc": completed.isoformat(),
        "duration_seconds": (completed - started).total_seconds(),
        "seed": seed,
        "evidence_status": allocation_config["evidence_status"],
        "reference_status": allocation_config["reference_allocation"]["status"],
        "workflow_config_path": str(config_path),
        "workflow_config_sha256": _sha256(config_path),
        "allocation_config_path": str(allocation_path),
        "allocation_config_sha256": _sha256(allocation_path),
        "model_manifest_sha256": _sha256(model_path / "manifest.json"),
        "data_sha256": model.manifest["data_sha256"],
        "model_track_id": model.manifest["model_track_id"],
        "model_interface_version": model.interface_version,
        "tuning_budget": workflow_config.get("tuning_budget"),
        "algorithm_api_review": workflow_config.get("algorithm_api_review"),
        "algorithms": summaries,
        "git": _git_metadata(),
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
            "joblib": joblib.__version__,
        },
    }
    metadata = _json_safe(metadata)
    (run_dir / "run_metadata.json").write_text(
        json.dumps(metadata, indent=2, allow_nan=False) + "\n"
    )
    return run_dir, metadata


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/optimization/small_synthetic.json")
    parser.add_argument("--output-root")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    run_dir, metadata = run_workflow(
        Path(args.config), Path(args.output_root) if args.output_root else None
    )
    print(f"Allocation workflow complete: {run_dir}")
    for algorithm in metadata["algorithms"]:
        print(
            f"{algorithm['algorithm']}: population={algorithm['population_size']}, "
            f"archive={algorithm['archive_size']}, "
            f"checked={algorithm['all_recommendations_independently_feasible']}"
        )


if __name__ == "__main__":
    main()
