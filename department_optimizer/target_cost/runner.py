"""Configuration-driven reverse target-cost workflow and report."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from department_optimizer.allocation import AllocationProblem
from department_optimizer.modeling import load_prediction_bundle

from .optimizer import TargetCostOptimizer, assess_targets


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _flatten(target_set, seed, result, baseline_cost):
    row = {
        "target_set": target_set["id"],
        "label": target_set["label"],
        "seed": seed,
        "status": result.status,
        "candidate_evaluations": result.accounting["candidate_evaluations_total"],
    }
    if result.evaluation is None:
        row["unsupported"] = "; ".join(result.accounting.get("unsupported", []))
        return row
    evaluation = result.evaluation
    row.update(result.candidate)
    row.update(
        total_cost=evaluation.cost,
        baseline_total_cost=baseline_cost,
        incremental_cost_vs_baseline=evaluation.cost - baseline_cost,
        nominal_feasible=evaluation.nominal_feasible,
        normalized_violation=evaluation.normalized_violation,
        target_feasible=all(value <= 1e-9 for value in result.target_residuals.values()),
        out_of_model_support=evaluation.support_flags["out_of_model_support"],
    )
    row.update({f"kpi__{key}": value for key, value in evaluation.raw_kpis.items()})
    for key, interval in evaluation.uncertainty.items():
        row[f"lower__{key}"] = interval["lower"]
        row[f"upper__{key}"] = interval["upper"]
    row.update(
        {f"objective_benefit__{key}": value for key, value in evaluation.objective_benefits.items()}
    )
    row.update({f"target_residual__{key}": value for key, value in result.target_residuals.items()})
    return row


def _write_report(path, config, baseline, all_runs, best):
    lines = [
        "# Optional reverse target-cost results",
        "",
        "> Synthetic method fixture. The baseline is illustrative and predictions are not causal intervention estimates.",
        "",
        f"The objective minimizes total annual allocation cost. Incremental cost is the optimized total minus the illustrative baseline cost of INR {baseline.cost:,.0f}; a negative value is reported as a modeled saving.",
        "",
        "| Target set | Status | Total cost | Incremental cost | Papers | Citation percentile | Evaluations |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for target_set in config["target_sets"]:
        rows = best[best.target_set == target_set["id"]]
        if rows.empty:
            source = all_runs[all_runs.target_set == target_set["id"]].iloc[0]
            lines.append(
                f"| {target_set['id']} | {source.status}: {source.get('unsupported', '')} | — | — | — | — | {int(source.candidate_evaluations)} |"
            )
        else:
            row = rows.iloc[0]
            lines.append(
                f"| {target_set['id']} | {row.status} | INR {row.total_cost:,.0f} | "
                f"INR {row.incremental_cost_vs_baseline:,.0f} | {row.kpi__papers_t1:.2f} | "
                f"{row.kpi__citation_percentile_avg:.4f} | {int(row.candidate_evaluations)} |"
            )
    lines += [
        "",
        "Each supported result was independently reevaluated through the shared allocation evaluator after search. Raw target residuals, KPI intervals, feasibility, support flags, allocation values, seeds, and evaluation counts are exported in CSV/JSON artifacts.",
        "",
        "The requested innovation and student target set is unsupported because the current model contains no innovation or student outcome components. It is reported without optimization rather than replaced with invented scores.",
        "",
        "The search is a bounded seeded heuristic and does not prove a global minimum. Multiple seeds and a cost-coordinate polishing stage improve the method fixture, while the minimum found remains an upper bound on the true target-achieving cost.",
    ]
    Path(path).write_text("\n".join(lines) + "\n")


def run_target_cost(config_path, output_root=None):
    config_path = Path(config_path)
    config = json.loads(config_path.read_text())
    output = Path(output_root or config["output_root"])
    output.mkdir(parents=True, exist_ok=True)
    allocation_path = Path(config["allocation_config"])
    allocation_config = json.loads(allocation_path.read_text())
    model_path = Path(allocation_config["model_bundle"])
    problem = AllocationProblem(allocation_config, load_prediction_bundle(model_path))
    baseline = problem.evaluate(allocation_config["reference_allocation"]["values"])
    rows = []
    run_details = []
    settings = config["optimizer"]
    for target_set in config["target_sets"]:
        support = assess_targets(problem, target_set["targets"])
        if support["status"] != "supported":
            result = TargetCostOptimizer(seed=settings["seeds"][0]).run(
                problem, target_set["targets"]
            )
            rows.append(_flatten(target_set, settings["seeds"][0], result, baseline.cost))
            run_details.append(
                {
                    "target_set": target_set["id"],
                    "seed": settings["seeds"][0],
                    "status": result.status,
                    "support": support,
                    "accounting": result.accounting,
                }
            )
            continue
        for seed in settings["seeds"]:
            optimizer = TargetCostOptimizer(
                population_size=settings["population_size"],
                generations=settings["generations"],
                evaluation_budget=settings["evaluation_budget"],
                seed=seed,
            )
            result = optimizer.run(problem, target_set["targets"])
            row = _flatten(target_set, seed, result, baseline.cost)
            rows.append(row)
            independent = problem.evaluate(result.candidate) if result.candidate else None
            if independent is not None and (
                any(
                    abs(independent.repaired[name] - result.candidate[name]) > 1e-9
                    for name in problem.variable_names
                )
                or independent.nominal_feasible != result.evaluation.nominal_feasible
            ):
                raise RuntimeError("target-cost result failed independent evaluator check")
            run_details.append(
                {
                    "target_set": target_set["id"],
                    "seed": seed,
                    "status": result.status,
                    "targets": target_set["targets"],
                    "target_residuals": result.target_residuals,
                    "accounting": result.accounting,
                    "evaluation": result.evaluation.to_dict() if result.evaluation else None,
                }
            )
    all_runs = pd.DataFrame(rows)
    all_runs.to_csv(output / "all_seed_results.csv", index=False)
    feasible = all_runs[
        (all_runs.status == "target_feasible")
        & all_runs["nominal_feasible"].eq(True)
        & all_runs["target_feasible"].eq(True)
    ]
    best = (
        feasible.sort_values(["target_set", "total_cost", "seed"], kind="stable")
        .groupby("target_set", as_index=False)
        .first()
    )
    best.to_csv(output / "best_target_cost_allocations.csv", index=False)
    (output / "run_details.json").write_text(json.dumps(run_details, indent=2) + "\n")
    _write_report(output / "report.md", config, baseline, all_runs, best)
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": config["run_id"],
                "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                "evidence_status": config["evidence_status"],
                "config_path": str(config_path),
                "config_sha256": _sha256(config_path),
                "allocation_config_sha256": _sha256(allocation_path),
                "model_manifest_sha256": _sha256(model_path / "manifest.json"),
                "data_sha256": problem.model.manifest["data_sha256"],
                "cost_semantics": config["cost_semantics"],
                "baseline_status": allocation_config["reference_allocation"]["status"],
                "baseline_total_cost": baseline.cost,
                "global_optimality": "not_proven_seeded_heuristic",
                "supported_target_sets": sorted(best.target_set.unique().tolist()),
                "unsupported_target_sets": [
                    item["id"]
                    for item in config["target_sets"]
                    if assess_targets(problem, item["targets"])["status"] != "supported"
                ],
            },
            indent=2,
        )
        + "\n"
    )
    return output


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default="configs/target_cost/synthetic_targets.json"
    )
    parser.add_argument("--output-root")
    return parser.parse_args()


def main():
    args = parse_args()
    output = run_target_cost(
        Path(args.config), Path(args.output_root) if args.output_root else None
    )
    print(f"Reverse target-cost optimization complete: {output}")


if __name__ == "__main__":
    main()
