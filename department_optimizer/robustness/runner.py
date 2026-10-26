"""Reoptimize scenarios and evaluate fixed strategies under common uncertainty draws."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from department_optimizer.allocation import AllocationProblem, CanonicalNSGA2Adapter
from department_optimizer.allocation.problem import OBJECTIVE_FAMILIES
from department_optimizer.modeling import load_prediction_bundle


def _now():
    return datetime.now(timezone.utc).isoformat()


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(_json_safe(payload), indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def apply_scenario(base_config, specification):
    """Return a copied allocation config plus explicit support status."""
    scenario = copy.deepcopy(base_config)
    scenario["scenario_id"] = specification["id"]
    if "budget_limit" in specification:
        scenario["budget_limit"] = float(specification["budget_limit"])
    if "faculty_capacity_fte" in specification:
        scenario["faculty_time"]["capacity_fte"] = float(
            specification["faculty_capacity_fte"]
        )
    variables = {item["name"]: item for item in scenario["decision_variables"]}
    missing = []
    for name, multiplier in specification.get("unit_cost_multipliers", {}).items():
        variable = variables.get(name)
        if variable is None or variable.get("cost_mode") != "unit_cost":
            missing.append(name)
            continue
        variable["unit_cost"] = float(variable["unit_cost"]) * float(multiplier)
    if missing:
        return None, "unsupported", "missing unit-cost decision variables: " + ", ".join(missing)
    return scenario, "supported", None


def evaluate_fixed(problem, allocation):
    """Evaluate an unchanged allocation without invoking automatic repair."""
    decoded = problem.decode(allocation)
    features = problem._model_features(decoded)
    prediction = problem.model.predict(pd.DataFrame([features])).iloc[0].to_dict()
    benefits, scores, supported = problem._objectives(prediction)
    residuals, robust_residuals, normalized = problem._constraints(decoded, prediction)
    return {
        "allocation": decoded,
        "raw_kpis": {
            target: float(prediction[f"prediction__{target}"])
            for target in problem.model.manifest["target_columns"]
        },
        "uncertainty": {
            target: {
                "lower": float(prediction[f"lower__{target}"]),
                "upper": float(prediction[f"upper__{target}"]),
            }
            for target in problem.model.manifest["target_columns"]
        },
        "objective_benefits": benefits,
        "objective_scores": scores,
        "objective_supported": supported,
        "constraint_residuals": {key: float(value) for key, value in residuals.items()},
        "robust_constraint_residuals": {
            key: float(value) for key, value in robust_residuals.items()
        },
        "normalized_violation": float(sum(normalized.values())),
        "nominal_feasible": bool(all(value <= 1e-9 for value in residuals.values())),
        "robust_feasible": bool(
            all(value <= 1e-9 for value in robust_residuals.values())
        ),
        "cost": float(problem.allocation_cost(decoded)),
        "budget_remaining": float(problem.config["budget_limit"])
        - float(problem.allocation_cost(decoded)),
        "out_of_model_support": bool(prediction["out_of_support"]),
        "out_of_support_features": str(prediction["out_of_support_features"]),
    }


def _validate(config):
    algorithm = config["algorithm"]
    if algorithm["name"] != "nsga2":
        raise ValueError("the Phase 6B fixture currently requires canonical nsga2")
    actual = int(algorithm["population_size"]) * (int(algorithm["generations"]) + 1)
    if actual != int(algorithm["candidate_evaluation_budget"]):
        raise ValueError("configured NSGA-II settings do not match the candidate budget")
    if len(config["scenarios"]) < 3:
        raise ValueError("at least three scenarios are required")
    required_policies = {"balanced", "research_first", "innovation_first", "student_first"}
    if not required_policies.issubset(config["policies"]):
        raise ValueError("required policy preferences are missing")
    for name, weights in config["policies"].items():
        if set(weights) != set(OBJECTIVE_FAMILIES) or not np.isclose(sum(weights.values()), 1.0):
            raise ValueError(f"policy {name} must assign weights summing to one")


def _run_scenario(root, specification, problem, algorithm_config, config_hash):
    scenario_id = specification["id"]
    rows = []
    for seed in algorithm_config["seeds"]:
        directory = root / "optimization_runs" / scenario_id / f"seed_{seed}"
        status_path = directory / "status.json"
        previous = json.loads(status_path.read_text()) if status_path.exists() else {}
        if previous.get("status") == "complete" and previous.get("config_sha256") == config_hash:
            archive = pd.read_csv(directory / "archive.csv")
            rows.append(archive)
            continue
        directory.mkdir(parents=True, exist_ok=True)
        started_at = _now()
        started = time.perf_counter()
        _write_json(
            status_path,
            {
                "status": "running",
                "scenario_id": scenario_id,
                "seed": seed,
                "config_sha256": config_hash,
                "started_at_utc": started_at,
            },
        )
        adapter = CanonicalNSGA2Adapter(
            population_size=algorithm_config["population_size"],
            generations=algorithm_config["generations"],
            seed=seed,
        )
        result = adapter.run(problem)
        if result.accounting["candidate_evaluations_total"] != algorithm_config[
            "candidate_evaluation_budget"
        ]:
            raise RuntimeError("scenario optimizer violated its evaluation budget")
        archive = result.archive.copy()
        archive["scenario_id"] = scenario_id
        archive["optimization_seed"] = seed
        result.population.to_csv(directory / "population.csv", index=False)
        archive.to_csv(directory / "archive.csv", index=False)
        _write_json(directory / "evaluation_accounting.json", result.accounting)
        _write_json(
            status_path,
            {
                "status": "complete",
                "scenario_id": scenario_id,
                "seed": seed,
                "config_sha256": config_hash,
                "started_at_utc": started_at,
                "completed_at_utc": _now(),
                "runtime_seconds": time.perf_counter() - started,
                "candidate_evaluations": result.accounting["candidate_evaluations_total"],
                "archive_size": len(archive),
            },
        )
        rows.append(archive)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _supported_families(allocation_config):
    return {
        family: bool(allocation_config["objective_families"][family].get("components"))
        for family in OBJECTIVE_FAMILIES
    }


def _select_policies(candidates, policies, variable_names, supported):
    rows = []
    for scenario_id, group in candidates.groupby("scenario_id"):
        feasible = group[group["feasible"].astype(bool)].copy()
        if feasible.empty:
            for policy_name, weights in policies.items():
                rows.append(
                    {
                        "scenario_id": scenario_id,
                        "policy": policy_name,
                        "selection_status": "no_feasible_candidate",
                        "unsupported_preference_weight": sum(
                            weights[name] for name in OBJECTIVE_FAMILIES if not supported[name]
                        ),
                    }
                )
            continue
        feasible = feasible.drop_duplicates(subset=variable_names).copy()
        for policy_name, weights in policies.items():
            utility = sum(
                float(weights[name]) * feasible[f"objective_benefit__{name}"]
                for name in OBJECTIVE_FAMILIES
            )
            ranked = feasible.assign(policy_utility=utility).sort_values(
                ["policy_utility", "cost"], ascending=[False, True], kind="stable"
            )
            chosen = ranked.iloc[0].to_dict()
            chosen.update(
                policy=policy_name,
                selection_status="selected",
                unsupported_preference_weight=sum(
                    weights[name] for name in OBJECTIVE_FAMILIES if not supported[name]
                ),
                declared_weights=json.dumps(weights, sort_keys=True),
            )
            rows.append(chosen)
    selected = pd.DataFrame(rows)
    selected["duplicate_strategy_within_scenario"] = False
    successful = selected[selected["selection_status"] == "selected"]
    for _, indexes in successful.groupby(["scenario_id", *variable_names]).groups.items():
        if len(indexes) > 1:
            selected.loc[list(indexes), "duplicate_strategy_within_scenario"] = True
    return selected


def _flatten_assessment(mode, source_scenario, assessed_scenario, policy, result):
    row = {
        "assessment_mode": mode,
        "source_scenario_id": source_scenario,
        "assessed_scenario_id": assessed_scenario,
        "policy": policy,
        "nominal_feasible": result["nominal_feasible"],
        "robust_feasible": result["robust_feasible"],
        "normalized_violation": result["normalized_violation"],
        "cost": result["cost"],
        "budget_remaining": result["budget_remaining"],
        "out_of_model_support": result["out_of_model_support"],
        "out_of_support_features": result["out_of_support_features"],
    }
    row.update(result["allocation"])
    row.update({f"kpi__{key}": value for key, value in result["raw_kpis"].items()})
    for key, interval in result["uncertainty"].items():
        row[f"lower__{key}"] = interval["lower"]
        row[f"upper__{key}"] = interval["upper"]
    row.update(
        {f"objective_benefit__{key}": value for key, value in result["objective_benefits"].items()}
    )
    row.update(
        {f"constraint__{key}": value for key, value in result["constraint_residuals"].items()}
    )
    return row


def _assess_strategies(selected, problems, base_scenario_id, variable_names):
    rows = []
    successful = selected[selected["selection_status"] == "selected"]
    for _, strategy in successful.iterrows():
        scenario_id = strategy["scenario_id"]
        allocation = {name: strategy[name] for name in variable_names}
        result = evaluate_fixed(problems[scenario_id], allocation)
        rows.append(
            _flatten_assessment("reoptimized", scenario_id, scenario_id, strategy["policy"], result)
        )
    baseline = successful[successful["scenario_id"] == base_scenario_id]
    for _, strategy in baseline.iterrows():
        allocation = {name: strategy[name] for name in variable_names}
        for scenario_id, problem in problems.items():
            result = evaluate_fixed(problem, allocation)
            rows.append(
                _flatten_assessment(
                    "fixed_baseline_strategy", base_scenario_id, scenario_id,
                    strategy["policy"], result,
                )
            )
    return pd.DataFrame(rows)


def _common_draws(model_manifest, problems, uncertainty):
    count = int(uncertainty["draws"])
    rng = np.random.default_rng(int(uncertainty["seed"]))
    draws = {"draw": np.arange(count, dtype=int)}
    for target in model_manifest["target_columns"]:
        draws[f"prediction_z__{target}"] = rng.normal(size=count)
    unit_variables = sorted(
        {
            item["name"]
            for problem in problems.values()
            for item in problem.variables
            if item["cost_mode"] == "unit_cost"
        }
    )
    cv = float(uncertainty["unit_cost_coefficient_of_variation"])
    sigma = math.sqrt(math.log1p(cv * cv))
    for name in unit_variables:
        cost_z = rng.normal(size=count)
        draws[f"cost_z__{name}"] = cost_z
        draws[f"cost_multiplier__{name}"] = np.exp(
            -0.5 * sigma * sigma + sigma * cost_z
        )
    return pd.DataFrame(draws)


def _sampled_family_benefit(problem, family, sampled_kpis):
    definition = problem.config["objective_families"][family]
    benefit = np.zeros(len(next(iter(sampled_kpis.values()))))
    used = False
    for component in definition.get("components", []):
        if component["kpi"] not in sampled_kpis:
            continue
        used = True
        norm = component["normalization"]
        value = (sampled_kpis[component["kpi"]] - norm["minimum"]) / (
            norm["maximum"] - norm["minimum"]
        )
        if component["direction"] == "minimize":
            value = 1.0 - value
        benefit += component["weight"] * value
    return benefit if used else np.zeros_like(benefit)


def _monte_carlo(
    assessments,
    problems,
    model_manifest,
    draws,
    uncertainty,
    assumption_id="base",
    prediction_scale=1.0,
    cost_cv=None,
):
    rows = []
    z_value = float(uncertainty["prediction_interval_z"])
    cost_cv = float(
        uncertainty["unit_cost_coefficient_of_variation"] if cost_cv is None else cost_cv
    )
    cost_sigma = math.sqrt(math.log1p(cost_cv * cost_cv))
    for _, assessment in assessments.iterrows():
        problem = problems[assessment["assessed_scenario_id"]]
        allocation = {name: assessment[name] for name in problem.variable_names}
        sampled_kpis = {}
        for target in model_manifest["target_columns"]:
            center = float(assessment[f"kpi__{target}"])
            half_width = (
                float(assessment[f"upper__{target}"])
                - float(assessment[f"lower__{target}"])
            ) / 2.0
            sampled = center + prediction_scale * (half_width / z_value) * draws[
                f"prediction_z__{target}"
            ].to_numpy()
            bounds = model_manifest["target_bounds"][target]
            if bounds[0] is not None:
                sampled = np.maximum(sampled, bounds[0])
            if bounds[1] is not None:
                sampled = np.minimum(sampled, bounds[1])
            sampled_kpis[target] = sampled
        sampled_cost = np.zeros(len(draws))
        for variable in problem.variables:
            amount = float(allocation[variable["name"]])
            if variable["cost_mode"] == "direct_money":
                sampled_cost += amount
            elif variable["cost_mode"] == "unit_cost":
                multiplier = np.exp(
                    -0.5 * cost_sigma * cost_sigma
                    + cost_sigma
                    * draws[f"cost_z__{variable['name']}"].to_numpy()
                )
                sampled_cost += (
                    amount
                    * float(variable["unit_cost"])
                    * multiplier
                )
        non_budget_residuals = [
            float(value)
            for column, value in assessment.items()
            if column.startswith("constraint__") and column != "constraint__budget"
        ]
        deterministic_other_feasible = all(value <= 1e-9 for value in non_budget_residuals)
        feasible = (sampled_cost <= float(problem.config["budget_limit"])) & bool(
            deterministic_other_feasible
        )
        row = {
            "assumption_id": assumption_id,
            "prediction_uncertainty_scale": prediction_scale,
            "unit_cost_coefficient_of_variation": cost_cv,
            "assessment_mode": assessment["assessment_mode"],
            "source_scenario_id": assessment["source_scenario_id"],
            "assessed_scenario_id": assessment["assessed_scenario_id"],
            "policy": assessment["policy"],
            "draws": len(draws),
            "probability_feasible": float(feasible.mean()),
            "cost_mean": float(sampled_cost.mean()),
            "cost_p90": float(np.quantile(sampled_cost, 0.9)),
        }
        for target, values in sampled_kpis.items():
            row[f"{target}_mean"] = float(values.mean())
            row[f"{target}_p10_downside"] = float(np.quantile(values, 0.1))
            row[f"{target}_p90"] = float(np.quantile(values, 0.9))
        for family in OBJECTIVE_FAMILIES:
            values = _sampled_family_benefit(problem, family, sampled_kpis)
            row[f"{family}_benefit_mean"] = float(values.mean())
            row[f"{family}_benefit_p10_downside"] = float(np.quantile(values, 0.1))
        rows.append(row)
    return pd.DataFrame(rows)


def _write_report(path, catalog, selected, assessments, monte_carlo, comparison):
    supported = catalog[catalog.status == "supported"]
    unsupported = catalog[catalog.status == "unsupported"]
    balanced = monte_carlo[
        (monte_carlo.policy == "balanced")
        & (monte_carlo.assumption_id == "base")
    ]
    lines = [
        "# Phase 6B synthetic robustness results",
        "",
        "This is synthetic method-fixture evidence. Predicted changes are associations from the synthetic response model, not causal estimates.",
        "",
        f"The run completed {len(supported)} supported scenarios. {len(unsupported)} requested scenarios were retained as unsupported rather than simulated with invented variables.",
        "",
        "## Fixed strategy versus reoptimization",
        "",
        "| Scenario | Fixed nominal feasible | Reoptimized nominal feasible | Fixed Monte Carlo feasible | Reoptimized Monte Carlo feasible | Reoptimized papers mean | Reoptimized papers p10 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for scenario_id in supported.scenario_id:
        fixed_nominal = assessments[
            (assessments.assessment_mode == "fixed_baseline_strategy")
            & (assessments.assessed_scenario_id == scenario_id)
            & (assessments.policy == "balanced")
        ]
        optimized_nominal = assessments[
            (assessments.assessment_mode == "reoptimized")
            & (assessments.assessed_scenario_id == scenario_id)
            & (assessments.policy == "balanced")
        ]
        fixed_mc = balanced[
            (balanced.assessment_mode == "fixed_baseline_strategy")
            & (balanced.assessed_scenario_id == scenario_id)
        ]
        optimized_mc = balanced[
            (balanced.assessment_mode == "reoptimized")
            & (balanced.assessed_scenario_id == scenario_id)
        ]
        lines.append(
            f"| {scenario_id} | {bool(fixed_nominal.iloc[0].nominal_feasible)} | "
            f"{bool(optimized_nominal.iloc[0].nominal_feasible)} | "
            f"{fixed_mc.iloc[0].probability_feasible:.3f} | "
            f"{optimized_mc.iloc[0].probability_feasible:.3f} | "
            f"{optimized_mc.iloc[0].papers_t1_mean:.2f} | "
            f"{optimized_mc.iloc[0].papers_t1_p10_downside:.2f} |"
        )
    lines.extend(
        [
            "",
            "The held-fixed base strategy is evaluated unchanged. Reoptimization is a separate adaptive response. A strategy close to a scenario budget can be nominally feasible while having a lower feasibility fraction after assumed unit-cost variation.",
            "",
            "## Preference and evidence limits",
            "",
            f"All {len(selected)} policy selections are marked duplicate within their scenario because only the research family has modeled outcomes. Innovation-first and student-first labels therefore do not constitute innovation or student recommendations.",
            "",
        ]
    )
    for _, row in unsupported.iterrows():
        lines.append(f"- `{row.scenario_id}`: {row.reason}.")
    lines.extend(
        [
            "",
            "Monte Carlo results use common random numbers and explicit normal/lognormal sensitivity assumptions. The low/base/high table changes prediction-width and unit-cost-variation assumptions; it does not provide calibrated causal probabilities.",
            "",
        ]
    )
    Path(path).write_text("\n".join(lines))


def _comparison(monte_carlo):
    fixed = monte_carlo[monte_carlo.assessment_mode == "fixed_baseline_strategy"]
    optimized = monte_carlo[monte_carlo.assessment_mode == "reoptimized"]
    keys = ["assessed_scenario_id", "policy"]
    paired = fixed.merge(optimized, on=keys, suffixes=("_fixed", "_reoptimized"))
    for metric in (
        "probability_feasible",
        "papers_t1_mean",
        "papers_t1_p10_downside",
        "citation_percentile_avg_mean",
        "research_benefit_mean",
    ):
        paired[f"delta_reoptimized_minus_fixed__{metric}"] = (
            paired[f"{metric}_reoptimized"] - paired[f"{metric}_fixed"]
        )
    return paired


def run_robustness(config_path, output_root=None):
    started_at = _now()
    config_path = Path(config_path)
    config = json.loads(config_path.read_text())
    _validate(config)
    config_hash = _sha256(config_path)
    root = Path(output_root or config["output_root"])
    root.mkdir(parents=True, exist_ok=True)
    allocation_path = Path(config["allocation_config"])
    base_config = json.loads(allocation_path.read_text())
    model_path = Path(base_config["model_bundle"])
    model = load_prediction_bundle(model_path)
    catalog = []
    problems = {}
    candidates = []
    for specification in config["scenarios"]:
        scenario_config, status, reason = apply_scenario(base_config, specification)
        catalog.append(
            {
                "scenario_id": specification["id"],
                "label": specification["label"],
                "status": status,
                "reason": reason,
                "selection_baseline": bool(specification.get("selection_baseline", False)),
                "budget_limit": specification.get("budget_limit"),
                "faculty_capacity_fte": specification.get("faculty_capacity_fte"),
                "unit_cost_multipliers": json.dumps(
                    specification.get("unit_cost_multipliers", {}), sort_keys=True
                ),
            }
        )
        if status != "supported":
            continue
        problem = AllocationProblem(scenario_config, model)
        problems[specification["id"]] = problem
        candidates.append(
            _run_scenario(
                root, specification, problem, config["algorithm"], config_hash
            )
        )
    catalog_frame = pd.DataFrame(catalog)
    catalog_frame.to_csv(root / "scenario_catalog.csv", index=False)
    all_candidates = pd.concat(candidates, ignore_index=True)
    all_candidates.to_csv(root / "reoptimized_candidates.csv", index=False)
    supported = _supported_families(base_config)
    selected = _select_policies(
        all_candidates, config["policies"],
        next(iter(problems.values())).variable_names, supported,
    )
    selected.to_csv(root / "selected_strategies.csv", index=False)
    baseline_ids = catalog_frame[catalog_frame.selection_baseline & (catalog_frame.status == "supported")][
        "scenario_id"
    ].tolist()
    if len(baseline_ids) != 1:
        raise ValueError("exactly one supported selection baseline is required")
    variable_names = next(iter(problems.values())).variable_names
    assessments = _assess_strategies(selected, problems, baseline_ids[0], variable_names)
    assessments.to_csv(root / "strategy_scenario_assessments.csv", index=False)
    draws = _common_draws(model.manifest, problems, config["uncertainty"])
    draws.to_csv(root / "common_uncertainty_draws.csv", index=False)
    monte_carlo = _monte_carlo(
        assessments, problems, model.manifest, draws, config["uncertainty"]
    )
    monte_carlo.to_csv(root / "monte_carlo_summary.csv", index=False)
    sensitivity = pd.concat(
        [
            _monte_carlo(
                assessments, problems, model.manifest, draws, config["uncertainty"],
                assumption_id="low_uncertainty", prediction_scale=0.5, cost_cv=0.05,
            ),
            monte_carlo,
            _monte_carlo(
                assessments, problems, model.manifest, draws, config["uncertainty"],
                assumption_id="high_uncertainty", prediction_scale=1.5, cost_cv=0.20,
            ),
        ],
        ignore_index=True,
    )
    sensitivity.to_csv(root / "assumption_sensitivity.csv", index=False)
    comparison = _comparison(monte_carlo)
    comparison.to_csv(
        root / "fixed_vs_reoptimized_comparison.csv", index=False
    )
    _write_report(
        root / "report.md", catalog_frame, selected, assessments, monte_carlo, comparison
    )
    _write_json(root / "robustness_config_snapshot.json", config)
    _write_json(
        root / "manifest.json",
        {
            "analysis_id": config["analysis_id"],
            "evidence_status": config["evidence_status"],
            "started_at_utc": started_at,
            "completed_at_utc": _now(),
            "config_path": str(config_path),
            "config_sha256": config_hash,
            "allocation_config_path": str(allocation_path),
            "allocation_config_sha256": _sha256(allocation_path),
            "model_manifest_sha256": _sha256(model_path / "manifest.json"),
            "model_track_id": model.manifest["model_track_id"],
            "data_path": model.manifest["data_path"],
            "data_sha256": model.manifest["data_sha256"],
            "algorithm": config["algorithm"],
            "supported_scenarios": sorted(problems),
            "unsupported_scenarios": catalog_frame[catalog_frame.status == "unsupported"][
                ["scenario_id", "reason"]
            ].to_dict("records"),
            "supported_objective_families": supported,
            "uncertainty": config["uncertainty"],
            "interpretation": (
                "Monte Carlo distributions are explicit sensitivity assumptions over a "
                "synthetic response model. They are not causal or calibrated joint probabilities."
            ),
            "environment": {
                "python": sys.version,
                "platform": platform.platform(),
                "numpy": np.__version__,
                "pandas": pd.__version__,
            },
        },
    )
    return root


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default="configs/robustness/phase6b_synthetic.json"
    )
    parser.add_argument("--output-root")
    return parser.parse_args()


def main():
    args = parse_args()
    root = run_robustness(
        Path(args.config), Path(args.output_root) if args.output_root else None
    )
    catalog = pd.read_csv(root / "scenario_catalog.csv")
    print(
        f"Robustness analysis complete: {root} "
        f"({sum(catalog.status == 'supported')} supported, "
        f"{sum(catalog.status == 'unsupported')} unsupported scenarios)"
    )


if __name__ == "__main__":
    main()
