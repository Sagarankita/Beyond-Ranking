from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from department_optimizer.public_allocation.problem import FAMILIES, VJTIPublicAllocationProblem


PROFILE_RULES = {
    "balanced": "Equal weight across research, innovation, student development, and societal contribution.",
    "research_focused": "Highest weighted modeled benefit with 55% weight on research and 15% on each other family.",
    "innovation_focused": "Highest weighted modeled benefit with 55% weight on innovation and 15% on each other family.",
    "student_focused": "Highest weighted modeled benefit with 55% weight on student development and 15% on each other family.",
    "robust": "Highest equal-weight benefit among candidates that separately pass the evaluator's conservative service checks.",
}


def _stable_id(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _profile_weights(experiment: Mapping[str, Any]) -> dict[str, list[float]]:
    configured = experiment["policy_preferences"]
    return {
        "balanced": list(configured["balanced"]),
        "research_focused": list(configured["research_first"]),
        "innovation_focused": list(configured["innovation_first"]),
        "student_focused": list(configured["student_first"]),
        "robust": list(configured["balanced"]),
    }


def _support_warnings(result) -> list[dict[str, Any]]:
    flags = result.support_flags
    warnings: list[dict[str, Any]] = []
    if flags.get("out_of_model_support"):
        warnings.append(
            {
                "code": "out_of_model_support",
                "message": "One or more model features are outside the stored training-support range.",
                "features": list(flags.get("out_of_support_features", [])),
                "rule": flags.get("extrapolation_rule"),
            }
        )
    warnings.append(
        {
            "code": "synthetic_non_causal",
            "message": "Modeled public-calibrated plus synthetic relationships do not establish causal effects.",
            "features": [],
        }
    )
    return warnings


def _constraint_status(margin: float, tolerance: float) -> str:
    if margin < -tolerance:
        return "violated"
    if abs(margin) <= tolerance:
        return "binding"
    return "satisfied"


def _constraint_evidence(problem: VJTIPublicAllocationProblem, result) -> list[dict[str, Any]]:
    config = problem.config
    allocation = result.repaired
    items: list[dict[str, Any]] = []

    def append(name: str, margin: float, unit: str, tolerance: float = 1e-9) -> None:
        items.append(
            {
                "name": name,
                "status": _constraint_status(float(margin), tolerance),
                "margin": float(margin),
                "unit": unit,
                "evaluator_residual": float(result.constraint_residuals[name]),
                "normalized_residual": float(result.normalized_constraint_violations[name]),
            }
        )

    append("budget", result.budget_remaining, "INR", 1e-6)
    allocated_effort = sum(
        allocation[name]
        for name in (
            "research_faculty_effort",
            "student_support_faculty_effort",
            "service_faculty_effort",
        )
    )
    available_effort = (
        config["fixed_context"]["faculty_total"]
        - config["service_commitments"]["minimum_teaching_fte"]
    )
    append(
        "faculty_effort_conservation",
        available_effort - allocated_effort,
        "annual FTE",
    )
    for variable_name, minimum_name in (
        ("student_support_faculty_effort", "minimum_student_support_fte"),
        ("service_faculty_effort", "minimum_service_fte"),
    ):
        append(
            f"service_floor__{variable_name}",
            allocation[variable_name] - config["service_commitments"][minimum_name],
            "annual FTE",
        )
    variables = {item["name"]: item for item in config["decision_variables"]}
    for dependency in config.get("dependencies", []):
        required = allocation[dependency["count_variable"]] * dependency["minimum_funding_per_unit"]
        funding_name = dependency["funding_variable"]
        append(
            f"dependency__{dependency['name']}",
            allocation[funding_name] - required,
            variables[funding_name]["unit"],
            1e-6,
        )
    for service in config.get("conservative_kpi_services", []):
        kpi = service["kpi"]
        append(
            f"service_kpi__{kpi}",
            result.intervals[kpi]["lower"] - service["minimum_lower_bound"],
            "KPI-specific modeled value",
        )
    return items


def _decision_changes(problem: VJTIPublicAllocationProblem, reference, proposed) -> list[dict[str, Any]]:
    reference_costs = problem.cost_components(reference.repaired)
    proposed_costs = problem.cost_components(proposed.repaired)
    rows = []
    for variable in problem.variables:
        name = variable["name"]
        before = float(reference.repaired[name])
        after = float(proposed.repaired[name])
        delta = after - before
        tolerance = max(float(variable["increment"]) * 1e-6, 1e-9)
        action = "retain" if abs(delta) <= tolerance else ("increase" if delta > 0 else "decrease")
        rows.append(
            {
                "variable": name,
                "action": action,
                "before": before,
                "after": after,
                "delta": delta,
                "unit": variable["unit"],
                "budget_effect": float(proposed_costs[name] - reference_costs[name])
                if variable["cost_mode"] != "non_monetary"
                else None,
                "cost_mode": variable["cost_mode"],
                "provenance": variable["provenance"],
            }
        )
    return rows


def _faculty_utilization(problem: VJTIPublicAllocationProblem, allocation: Mapping[str, float]) -> dict[str, float]:
    teaching = float(problem.config["service_commitments"]["minimum_teaching_fte"])
    controllable = sum(
        float(allocation[name])
        for name in (
            "research_faculty_effort",
            "student_support_faculty_effort",
            "service_faculty_effort",
        )
    )
    total = float(problem.config["fixed_context"]["faculty_total"])
    used = teaching + controllable
    return {"used": used, "available": total, "headroom": total - used, "unit": "annual FTE"}


def _objective_deltas(problem, reference, proposed) -> list[dict[str, Any]]:
    rows = []
    for family in FAMILIES:
        configuration = problem.config["objective_families"].get(family)
        reference_components = {
            item["kpi"]: item for item in reference.score_components.get(family, [])
        }
        proposed_components = {
            item["kpi"]: item for item in proposed.score_components.get(family, [])
        }
        components = []
        for item in (configuration or {}).get("components", []):
            kpi = item["kpi"]
            before = reference_components.get(kpi)
            after = proposed_components.get(kpi)
            components.append(
                {
                    "kpi": kpi,
                    "weight": float(item["weight"]),
                    "normalization_minimum": float(item["normalization"]["minimum"]),
                    "normalization_maximum": float(item["normalization"]["maximum"]),
                    "reference_raw_value": float(before["raw_value"]) if before else None,
                    "proposed_raw_value": float(after["raw_value"]) if after else None,
                    "reference_normalized_value": float(before["normalized_value"]) if before else None,
                    "proposed_normalized_value": float(after["normalized_value"]) if after else None,
                    "proposed_weighted_benefit": float(after["weighted_benefit"]) if after else None,
                    "evidence": str(
                        (after or before or {}).get(
                            "evidence_label", item.get("evidence_label", "unsupported")
                        )
                    ),
                }
            )
        reference_value = float(reference.objective_benefits[family])
        proposed_value = float(proposed.objective_benefits[family])
        rows.append(
            {
                "name": family,
                "reference": reference_value,
                "proposed": proposed_value,
                "difference": proposed_value - reference_value,
                "scale": "normalized modeled benefit [0, 1]",
                "display_direction": "higher_is_preferred",
                "optimizer_direction": "minimize_negative_benefit",
                "bounded": True,
                "evidence": proposed.objective_evidence[family],
                "components": components,
            }
        )
    return rows


def _explanation(profile: str, changes, objective_deltas, constraints, warnings) -> dict[str, Any]:
    changed = [item for item in changes if item["action"] != "retain"]
    increases = [item for item in objective_deltas if item["difference"] > 1e-12]
    decreases = [item for item in objective_deltas if item["difference"] < -1e-12]
    binding = [item for item in constraints if item["status"] == "binding"]
    return {
        "what_changes": (
            [f"{len(changed)} of {len(changes)} controllable decisions change from the configured reference."]
            if changed
            else ["All controllable decisions match the configured reference allocation."]
        ),
        "why": [
            f"This candidate maximizes the documented {profile.replace('_', ' ')} weighted-utility rule within this run's feasible archive."
        ],
        "tradeoffs": [
            f"{len(increases)} objective families are higher and {len(decreases)} are lower than the modeled reference on the normalized benefit scale."
        ],
        "uncertainty": [item["message"] for item in warnings]
        + ([f"{len(binding)} named constraints are binding at the displayed tolerance."] if binding else []),
    }


def build_recommendations(
    *,
    run_status: Mapping[str, Any],
    candidates: list[dict[str, Any]],
    problem: VJTIPublicAllocationProblem,
    experiment_config: Mapping[str, Any],
) -> dict[str, Any]:
    reference_allocation = problem.config.get("reference_allocation")
    if not reference_allocation:
        return {
            "status": "no_supported_recommendation",
            "reason": "The scenario has no configured reference allocation.",
            "run_id": run_status["run_id"],
            "scenario_hash": run_status["scenario_hash"],
            "profile_results": [],
            "recommendations": [],
        }
    pool = [
        item
        for item in candidates
        if item.get("revalidated") is True
        and item.get("feasible") is True
        and item.get("run_id") == run_status["run_id"]
        and item.get("scenario_hash") == run_status["scenario_hash"]
    ]
    if not pool:
        return {
            "status": "no_supported_recommendation",
            "reason": "No independently revalidated feasible archive candidate is available.",
            "run_id": run_status["run_id"],
            "scenario_hash": run_status["scenario_hash"],
            "profile_results": [],
            "recommendations": [],
        }

    reference = problem.evaluate_fixed(reference_allocation)
    weights_by_profile = _profile_weights(experiment_config)
    first_profile_for_candidate: dict[str, str] = {}
    profile_results = []
    recommendations = []
    for profile, weights in weights_by_profile.items():
        eligible = [item for item in pool if item.get("robust_feasible") is True] if profile == "robust" else pool
        if not eligible:
            profile_results.append(
                {
                    "profile": profile,
                    "status": "unsupported",
                    "reason": "No candidate separately passes the evaluator's conservative service checks.",
                    "selection_rule": PROFILE_RULES[profile],
                }
            )
            continue
        ranked = sorted(
            eligible,
            key=lambda item: (
                -sum(
                    float(weight) * float(item["objectives"][family]["benefit"])
                    for weight, family in zip(weights, FAMILIES, strict=True)
                ),
                item["candidate_id"],
            ),
        )
        selected = ranked[0]
        weighted_utility = sum(
            float(weight) * float(selected["objectives"][family]["benefit"])
            for weight, family in zip(weights, FAMILIES, strict=True)
        )
        duplicate_of = first_profile_for_candidate.get(selected["candidate_id"])
        first_profile_for_candidate.setdefault(selected["candidate_id"], profile)
        proposed = problem.evaluate_fixed(selected["decisions"])
        if not proposed.feasible:
            continue
        changes = _decision_changes(problem, reference, proposed)
        objective_deltas = _objective_deltas(problem, reference, proposed)
        constraints = _constraint_evidence(problem, proposed)
        warnings = _support_warnings(proposed)
        recommendation_id = _stable_id(
            {
                "run_id": run_status["run_id"],
                "scenario_hash": run_status["scenario_hash"],
                "profile": profile,
                "candidate_id": selected["candidate_id"],
                "schema": 1,
            }
        )
        recommendation = {
            "recommendation_id": recommendation_id,
            "scenario_id": run_status["scenario_hash"],
            "candidate_id": selected["candidate_id"],
            "source_run_id": run_status["run_id"],
            "profile": profile,
            "selection_rule": PROFILE_RULES[profile],
            "profile_weights": dict(zip(FAMILIES, weights, strict=True)),
            "weighted_utility": float(weighted_utility),
            "duplicate_of_profile": duplicate_of,
            "reference_label": "configured reference scenario",
            "decision_changes": changes,
            "budget": {
                "reference": float(reference.total_cost),
                "proposed": float(proposed.total_cost),
                "delta": float(proposed.total_cost - reference.total_cost),
                "limit": float(problem.config["budget_limit"]),
                "headroom": float(proposed.budget_remaining),
                "unit": "INR",
            },
            "faculty": {
                "reference": _faculty_utilization(problem, reference.repaired),
                "proposed": _faculty_utilization(problem, proposed.repaired),
            },
            "objective_deltas": objective_deltas,
            "constraint_evidence": constraints,
            "support_warnings": warnings,
            "uncertainty": [
                {
                    "kpi": name,
                    "prediction": float(proposed.raw_kpis[name]),
                    "lower": float(proposed.intervals[name]["lower"]),
                    "upper": float(proposed.intervals[name]["upper"]),
                    "validation_type": proposed.intervals[name]["validation_type"],
                }
                for name in sorted(proposed.raw_kpis)
            ],
            "evidence_class": problem.config["evidence_status"],
            "nominal_feasible": bool(proposed.feasible),
            "robust_feasible": bool(proposed.robust_feasible),
            "robustness_definition": "Conservative service interval checks in the evaluator; not a Monte Carlo robustness probability.",
            "data_dependencies": {
                "scenario_hash": run_status.get("scenario_hash"),
                "evaluator": "VJTIPublicAllocationProblem",
            },
        }
        recommendation["explanation"] = _explanation(
            profile, changes, objective_deltas, constraints, warnings
        )
        recommendations.append(recommendation)
        profile_results.append(
            {
                "profile": profile,
                "status": "duplicate" if duplicate_of else "selected",
                "candidate_id": selected["candidate_id"],
                "recommendation_id": recommendation_id,
                "duplicate_of_profile": duplicate_of,
                "selection_rule": PROFILE_RULES[profile],
                "weighted_utility": float(weighted_utility),
            }
        )
    return {
        "status": "supported" if recommendations else "no_supported_recommendation",
        "reason": None if recommendations else "No profile produced a supported feasible recommendation.",
        "run_id": run_status["run_id"],
        "scenario_hash": run_status["scenario_hash"],
        "reference_label": "configured reference scenario",
        "profile_results": profile_results,
        "recommendations": recommendations,
    }
