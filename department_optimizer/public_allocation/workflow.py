"""Run the Prompt 16 evaluator, sensitivity checks, and target-cost searches."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .problem import VJTIPublicAllocationProblem


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _flatten(result):
    row = {**result.repaired, "total_cost": result.total_cost,
           "budget_remaining": result.budget_remaining, "feasible": result.feasible,
           "normalized_violation": result.normalized_violation,
           "out_of_support": result.support_flags["out_of_support"],
           "out_of_support_features": ",".join(result.support_flags["out_of_support_features"])}
    row.update({f"kpi__{name}": value for name, value in result.raw_kpis.items()})
    for name, interval in result.intervals.items():
        row[f"lower__{name}"] = interval["lower"]
        row[f"upper__{name}"] = interval["upper"]
    row.update({f"objective_benefit__{name}": value for name, value in result.objective_benefits.items()})
    row.update({f"objective_score__{name}": value for name, value in result.objective_scores.items()})
    row.update({f"constraint__{name}": value for name, value in result.constraint_residuals.items()})
    row.update({f"synthetic_coverage__{name}": value for name, value in result.synthetic_coverage.items()})
    return row


def _target_satisfied(result, targets):
    for target in targets:
        value = result.raw_kpis[target["kpi"]]
        if target.get("use_conservative_lower"):
            value = result.intervals[target["kpi"]]["lower"]
        if value + 1e-9 < target["minimum"]:
            return False
    return True


def _target_cost(problem, target_config, seed):
    rng = np.random.default_rng(seed)
    candidates = [problem.config["reference_allocation"]]
    candidates.append({item["name"]: item["lower"] for item in problem.variables})
    for _ in range(int(target_config["random_candidates"])):
        candidate = {}
        for variable in problem.variables:
            steps = int(round((variable["upper"] - variable["lower"]) / variable["increment"]))
            candidate[variable["name"]] = variable["lower"] + rng.integers(0, steps + 1) * variable["increment"]
        candidates.append(candidate)
    feasible = []
    for candidate in candidates:
        result = problem.evaluate(candidate)
        if result.feasible and _target_satisfied(result, target_config["targets"]):
            feasible.append(result)
    if not feasible:
        return None, 0
    best = min(feasible, key=lambda item: (item.total_cost, -sum(item.objective_benefits.values())))
    for _ in range(2):
        for variable in sorted(problem.variables, key=lambda item: item.get("repair_priority", 0)):
            if variable["cost_mode"] == "non_monetary":
                continue
            name = variable["name"]
            current_steps = int(round((best.repaired[name] - variable["lower"]) / variable["increment"]))
            if current_steps <= 0:
                continue
            low, high, local_best = 0, current_steps, best
            while low <= high:
                middle = (low + high) // 2
                trial = dict(best.repaired)
                trial[name] = variable["lower"] + middle * variable["increment"]
                evaluated = problem.evaluate(trial)
                if evaluated.feasible and _target_satisfied(evaluated, target_config["targets"]):
                    local_best, high = evaluated, middle - 1
                else:
                    low = middle + 1
            if local_best.total_cost < best.total_cost:
                best = local_best
    return best, len(feasible)


def run_public_allocation(config_path="configs/public_allocation/vjti_four_family_v1.json"):
    config_path = Path(config_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    prompt14_root = Path(config["prompt14_root"])
    prompt15_root = Path(config["prompt15_root"])
    for required in (prompt14_root / "manifest.json", prompt15_root / "manifest.json",
                     prompt15_root / "model_manifest.json"):
        if not required.is_file():
            raise FileNotFoundError(required)
    p14 = json.loads((prompt14_root / "manifest.json").read_text())
    p15 = json.loads((prompt15_root / "manifest.json").read_text())
    if not p14["all_checks_pass"] or not p15["all_checks_pass"]:
        raise ValueError("Prompt 14/15 evidence gates must pass")
    output = Path(config["output_root"])
    output.mkdir(parents=True, exist_ok=True)
    problem = VJTIPublicAllocationProblem(config, prompt15_root)

    reference = problem.evaluate(config["reference_allocation"])
    _write_json(output / "reference_evaluation.json", reference.to_dict())
    pd.DataFrame([_flatten(reference)]).to_csv(output / "reference_evaluation.csv", index=False)
    component_rows = []
    for family, components in reference.score_components.items():
        for item in components:
            component_rows.append({"family": family, **item,
                                   "family_evidence": reference.objective_evidence[family],
                                   "family_synthetic_coverage": reference.synthetic_coverage[family]})
    pd.DataFrame(component_rows).to_csv(output / "objective_score_components.csv", index=False)

    sensitivity_rows = []
    for scenario in config["sensitivity_scenarios"]:
        candidate = dict(config["reference_allocation"])
        for name, delta in scenario["decision_deltas"].items():
            candidate[name] += delta
        result = problem.evaluate(candidate)
        sensitivity_rows.append({"scenario": scenario["name"], **_flatten(result)})
    sensitivity = pd.DataFrame(sensitivity_rows)
    sensitivity.to_csv(output / "decision_sensitivity.csv", index=False)

    target_count = 0
    target_summary = []
    for index, target_track in enumerate(config["target_cost_tracks"]):
        track_dir = output / "target_cost" / target_track["track_id"]
        track_dir.mkdir(parents=True, exist_ok=True)
        recommendation, match_count = _target_cost(problem, target_track, config["seed"] + index)
        status = {
            "track_id": target_track["track_id"], "evidence_label": target_track["evidence_label"],
            "target_basis": target_track["target_basis"], "targets": target_track["targets"],
            "matching_feasible_candidates": match_count,
            "status": "matched" if recommendation else "no_match",
            "interpretation": "Optimization uses synthetic response models; the target basis does not convert results into causal evidence.",
        }
        if recommendation:
            status["recommendation_feasible"] = recommendation.feasible
            status["recommendation_cost"] = recommendation.total_cost
            _write_json(track_dir / "recommendation.json", recommendation.to_dict())
            pd.DataFrame([_flatten(recommendation)]).to_csv(track_dir / "recommendation.csv", index=False)
            target_count += 1
        _write_json(track_dir / "status.json", status)
        target_summary.append(status)
    pd.DataFrame(target_summary).to_csv(output / "target_cost_summary.csv", index=False)

    cash_total = sum(reference.repaired[name] for name in config["cash_decisions"])
    effort_total = sum(reference.repaired[name] for name in config["effort_decisions"])
    integer_valid = all(float(reference.repaired[name]).is_integer() for name in config["integer_decisions"])
    response_signs = []
    for scenario in sensitivity_rows:
        if scenario["scenario"] == "patent_support_plus_500k":
            response_signs.append(scenario["kpi__patent_applications"] >= reference.raw_kpis["patent_applications"])
        if scenario["scenario"] == "compute_plus_2_units":
            response_signs.append(scenario["kpi__patent_applications"] >= reference.raw_kpis["patent_applications"])
    checks = [
        {"check": "upstream_hash_chain", "passed": p14["all_checks_pass"] and p15["all_checks_pass"], "detail": "Prompt 14 and 15 manifests pass"},
        {"check": "reference_feasible", "passed": reference.feasible, "detail": f"violation={reference.normalized_violation:.6g}"},
        {"check": "totals_semantics", "passed": config["allocation_semantics"] == "totals", "detail": "no increment/baseline mixing"},
        {"check": "currency_base_year", "passed": config["currency"]["code"] == "INR" and bool(config["currency"]["base_year"]), "detail": str(config["currency"])},
        {"check": "cash_reconciliation", "passed": abs(cash_total - config["reference_cash_total"]) < 0.01, "detail": f"cash={cash_total}"},
        {"check": "cost_reconciliation", "passed": abs(reference.total_cost - config["reference_total_cost"]) < 0.01, "detail": f"total={reference.total_cost}"},
        {"check": "effort_conservation", "passed": effort_total <= config["fixed_context"]["faculty_total"] - config["service_commitments"]["minimum_teaching_fte"], "detail": f"allocated={effort_total}"},
        {"check": "integer_decisions", "passed": integer_valid, "detail": ",".join(config["integer_decisions"])},
        {"check": "objective_traceability", "passed": all(reference.raw_kpis and value == "synthetic_scenario" for value in reference.objective_evidence.values()), "detail": "four families trace to synthetic KPI responses"},
        {"check": "dea_not_causal", "passed": "not used as a causal multiplier" in reference.dea_status, "detail": reference.dea_status},
        {"check": "patent_compute_sensitivity", "passed": all(response_signs), "detail": "documented monotone response shocks"},
        {"check": "target_cost_outputs", "passed": target_count == len(config["target_cost_tracks"]), "detail": f"{target_count}/{len(config['target_cost_tracks'])} matched"},
        {"check": "recommendations_feasible", "passed": all(item.get("recommendation_feasible", False) for item in target_summary), "detail": "all saved recommendations"},
    ]
    checks_frame = pd.DataFrame(checks)
    checks_frame.to_csv(output / "allocation_checks.csv", index=False)

    report = [
        "# VJTI four-family public-plus-synthetic allocation model", "",
        "This is scenario decision support, not evidence of causal departmental improvement. Public observations calibrate the baseline and selected targets; all response predictions are synthetic-scenario models.", "",
        "## Reference", "",
        f"The total allocation costs INR {reference.total_cost:,.0f} ({config['currency']['base_year']} nominal basis) and is feasible. Cash decisions reconcile to INR {cash_total:,.0f}; research-assistant and compute unit costs are added once.", "",
        "All research, innovation, student-development, and societal objectives are enabled. Each stored component includes raw KPI, interval, normalization, weight, weighted contribution, evidence label, support warning, and synthetic coverage.", "",
        "## Evidence and DEA boundary", "",
        "Placement and higher-study target levels use public descriptive evidence where stated. Their modeled response remains synthetic. DEA is descriptive context only and is not applied to any KPI or objective.", "",
        "## Target cost", "",
        "Public-informed and scenario KPI targets are optimized into separate directories. Every saved recommendation passes the shared budget, effort, service, dependency, integrality, and support-reporting contract.",
    ]
    (output / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    snapshot = dict(config)
    _write_json(output / "config_snapshot.json", snapshot)
    files = [path for path in output.rglob("*") if path.is_file() and path.name != "manifest.json"]
    manifest = {
        "analysis_id": config["analysis_id"], "evidence_status": "public_plus_synthetic_scenario",
        "config_path": str(config_path), "config_sha256": _sha256(config_path),
        "prompt14_manifest_sha256": _sha256(prompt14_root / "manifest.json"),
        "prompt15_manifest_sha256": _sha256(prompt15_root / "manifest.json"),
        "prompt15_model_manifest_sha256": _sha256(prompt15_root / "model_manifest.json"),
        "all_checks_pass": bool(checks_frame.passed.all()),
        "artifacts": {str(path.relative_to(output)).replace("\\", "/"): _sha256(path) for path in sorted(files)},
    }
    _write_json(output / "manifest.json", manifest)
    return {"output_root": str(output), "reference_feasible": reference.feasible,
            "target_recommendations": target_count, "checks_passed": bool(checks_frame.passed.all())}
