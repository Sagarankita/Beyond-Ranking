"""Execute Prompt 17 and regenerate its report strictly from saved artifacts."""

from __future__ import annotations

import copy
import hashlib
import json
import platform
import time
from pathlib import Path

import numpy as np
import pandas as pd

from department_optimizer.allocation import (
    CanonicalNSGA2Adapter,
    MOEADAdapter,
    MOPSOAdapter,
    NSGA3Adapter,
    RandomSearchAdapter,
    RionAllocationAdapter,
)
from department_optimizer.benchmark.metrics import hypervolume, igd, nondominated, spacing
from department_optimizer.public_allocation.problem import FAMILIES, VJTIPublicAllocationProblem


def _json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=float) + "\n", encoding="utf-8")


def _sha256(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolve(repo: Path, value: str):
    path = Path(value)
    return path if path.is_absolute() else repo / path


def _algorithm(name, parameters, seed):
    classes = {
        "nsga2": CanonicalNSGA2Adapter,
        "nsga3": NSGA3Adapter,
        "moead": MOEADAdapter,
        "mopso": MOPSOAdapter,
        "rion": RionAllocationAdapter,
        "random_search": RandomSearchAdapter,
    }
    return classes[name](seed=seed, **parameters)


def _scenario_config(base, scenario):
    config = copy.deepcopy(base)
    config["budget_limit"] = float(scenario.get("budget_limit", config["budget_limit"]))
    if "faculty_total" in scenario:
        config["fixed_context"]["faculty_total"] = float(scenario["faculty_total"])
    multipliers = scenario.get("cost_multiplier", {})
    for variable in config["decision_variables"]:
        if variable["name"] in multipliers:
            variable["cost_multiplier"] = float(multipliers[variable["name"]])
    return config


def _run_one(root, group, algorithm_name, parameters, seed, problem, budget):
    run_root = root / "runs" / group / algorithm_name / f"seed_{seed}"
    run_root.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    try:
        result = _algorithm(algorithm_name, parameters, seed).run(problem)
        result.population.to_csv(run_root / "population.csv", index=False)
        result.archive.to_csv(run_root / "archive.csv", index=False)
        accounting = dict(result.accounting)
        accounting["expected_candidate_evaluations"] = int(budget)
        accounting["matched_budget"] = accounting["candidate_evaluations_total"] == budget
        _json(run_root / "accounting.json", accounting)
        status = {
            "status": "complete",
            "algorithm": algorithm_name,
            "seed": seed,
            "runtime_seconds": time.perf_counter() - started,
            "population_rows": len(result.population),
            "archive_rows": len(result.archive),
            "archive_state": "valid" if len(result.archive) else "no_match_no_feasible_nondominated",
        }
    except Exception as exc:  # failure artifacts are required outputs
        status = {
            "status": "failed",
            "algorithm": algorithm_name,
            "seed": seed,
            "runtime_seconds": time.perf_counter() - started,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    _json(run_root / "status.json", status)
    return status


def _read_runs(root, group):
    records = []
    for status_path in sorted((root / "runs" / group).glob("*/seed_*/status.json")):
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["status_artifact"] = status_path.relative_to(root).as_posix()
        records.append(status)
    return records


def _comparison_metrics(root, runs, objective_columns):
    frames = []
    for status in runs:
        if status["status"] != "complete":
            continue
        archive_path = root / status["status_artifact"].replace("status.json", "archive.csv")
        frame = pd.read_csv(archive_path)
        if len(frame):
            frames.append(frame[objective_columns])
    pooled = np.vstack([frame.to_numpy(float) for frame in frames]) if frames else np.empty((0, 4))
    reference_front = nondominated(pooled)
    rows = []
    for status in runs:
        row = {key: status.get(key) for key in ("algorithm", "seed", "status", "runtime_seconds")}
        row["status_artifact"] = status["status_artifact"]
        if status["status"] == "complete":
            archive_path = root / status["status_artifact"].replace("status.json", "archive.csv")
            population_path = root / status["status_artifact"].replace("status.json", "population.csv")
            archive, population = pd.read_csv(archive_path), pd.read_csv(population_path)
            points = archive[objective_columns].to_numpy(float) if len(archive) else np.empty((0, 4))
            row.update(
                archive_size=len(archive),
                feasible_solution_rate=float(population["feasible"].mean()),
                hypervolume=hypervolume(points, np.full(4, 0.05)),
                igd=igd(points, reference_front),
                spacing=spacing(points),
                accounting_artifact=status["status_artifact"].replace("status.json", "accounting.json"),
            )
        rows.append(row)
    metrics = pd.DataFrame(rows)
    metrics.to_csv(root / "algorithm_metrics.csv", index=False)
    summary = metrics[metrics.status == "complete"].groupby("algorithm", as_index=False).agg(
        runs=("seed", "count"), hypervolume_median=("hypervolume", "median"),
        igd_median=("igd", "median"), spacing_median=("spacing", "median"),
        feasible_rate_mean=("feasible_solution_rate", "mean"), runtime_seconds_median=("runtime_seconds", "median"),
    )
    summary.to_csv(root / "algorithm_summary.csv", index=False)
    pd.DataFrame(reference_front, columns=objective_columns).to_csv(root / "pooled_reference_front.csv", index=False)
    return metrics


def _flatten_strategy(strategy_id, strategy_type, scenario, result, source_artifact):
    common = {
        "strategy_id": strategy_id,
        "strategy_type": strategy_type,
        "scenario": scenario,
        "source_artifact": source_artifact,
        "feasible": result.feasible,
        "normalized_violation": result.normalized_violation,
        "total_cost": result.total_cost,
        "budget_remaining": result.budget_remaining,
        "out_of_support": result.support_flags["out_of_support"],
        "out_of_support_features": ",".join(result.support_flags["out_of_support_features"]),
    }
    allocations = [{**common, "decision": name, "value": value} for name, value in result.repaired.items()]
    kpis = [{**common, "kpi": name, "prediction": value,
             "lower": result.intervals[name]["lower"], "upper": result.intervals[name]["upper"]}
            for name, value in result.raw_kpis.items()]
    objectives = [{**common, "objective": name, "benefit": result.objective_benefits[name],
                   "score": result.objective_scores[name], "evidence": result.objective_evidence[name],
                   "synthetic_coverage": result.synthetic_coverage[name]}
                  for name in FAMILIES]
    constraints = [{**common, "constraint": name, "residual": value,
                    "normalized_residual": result.normalized_constraint_violations[name]}
                   for name, value in result.constraint_residuals.items()]
    return allocations, kpis, objectives, constraints


def _select_portfolio(root, base_config, model_root, preferences):
    problem = VJTIPublicAllocationProblem(base_config, model_root)
    allocations, kpis, objectives, constraints, log = [], [], [], [], []
    baseline = problem.evaluate_fixed(base_config["reference_allocation"])
    parts = _flatten_strategy("current", "held_fixed_current", "base", baseline,
                              "configs/public_allocation/vjti_four_family_v1.json")
    for target, values in zip((allocations, kpis, objectives, constraints), parts):
        target.extend(values)
    archives = []
    for path in sorted((root / "runs" / "comparison").glob("*/seed_*/archive.csv")):
        frame = pd.read_csv(path)
        if len(frame):
            frame["_source"] = path.relative_to(root).as_posix()
            frame["_row"] = np.arange(len(frame))
            archives.append(frame)
    pool = pd.concat(archives, ignore_index=True) if archives else pd.DataFrame()
    selected_keys = {}
    for policy, weights in preferences.items():
        if pool.empty:
            log.append({"policy": policy, "result": "no_match", "reason": "all saved comparison archives empty"})
            continue
        utility = sum(float(weight) * pool[f"objective_benefit__{family}"] for weight, family in zip(weights, FAMILIES))
        index = int(utility.idxmax())
        row = pool.loc[index]
        key = tuple(float(row[name]) for name in problem.variable_names)
        duplicate_of = selected_keys.get(key)
        selected_keys.setdefault(key, policy)
        source = f"{row['_source']}#row={int(row['_row'])}"
        strategy_id = f"policy_{policy}"
        result = problem.evaluate_fixed({name: row[name] for name in problem.variable_names})
        parts = _flatten_strategy(strategy_id, "policy_selection", "base", result, source)
        for target, values in zip((allocations, kpis, objectives, constraints), parts):
            target.extend(values)
        log.append({"policy": policy, "result": "duplicate" if duplicate_of else "selected",
                    "duplicate_of": duplicate_of or "", "strategy_id": strategy_id,
                    "source_artifact": source, "weighted_utility": float(utility.loc[index])})
    return allocations, kpis, objectives, constraints, log


def _scenario_strategies(root, scenarios, base_config, model_root, seed):
    tables = [[], [], [], []]
    log = []
    balanced = np.full(4, 0.25)
    for scenario in scenarios:
        name = scenario["name"]
        problem = VJTIPublicAllocationProblem(_scenario_config(base_config, scenario), model_root)
        fixed = problem.evaluate_fixed(base_config["reference_allocation"])
        parts = _flatten_strategy(f"{name}__held_fixed", "held_fixed", name, fixed,
                                  "configs/public_allocation/vjti_four_family_v1.json")
        for target, values in zip(tables, parts):
            target.extend(values)
        archive_path = root / "runs" / f"scenario_{name}" / "nsga2" / f"seed_{seed}" / "archive.csv"
        if not archive_path.exists() or not len(pd.read_csv(archive_path)):
            log.append({"policy": "balanced", "scenario": name, "result": "no_match",
                        "reason": "saved reoptimization archive empty", "source_artifact": archive_path.relative_to(root).as_posix()})
            continue
        archive = pd.read_csv(archive_path)
        utility = sum(weight * archive[f"objective_benefit__{family}"] for weight, family in zip(balanced, FAMILIES))
        index = int(utility.idxmax())
        candidate = {decision: archive.loc[index, decision] for decision in problem.variable_names}
        result = problem.evaluate_fixed(candidate)
        source = f"{archive_path.relative_to(root).as_posix()}#row={index}"
        parts = _flatten_strategy(f"{name}__reoptimized", "scenario_reoptimization", name, result, source)
        for target, values in zip(tables, parts):
            target.extend(values)
        log.append({"policy": "balanced", "scenario": name, "result": "selected",
                    "strategy_id": f"{name}__reoptimized", "source_artifact": source,
                    "weighted_utility": float(utility.loc[index])})
    return (*tables, log)


def _uncertainty(root, base_config, strategy_kpis, strategy_objectives, settings):
    kpi_names = sorted(strategy_kpis.kpi.unique())
    rng = np.random.default_rng(int(settings["seed"]))
    draws = rng.standard_normal((int(settings["draws"]), len(kpi_names)))
    pd.DataFrame(draws, columns=kpi_names).to_csv(root / "common_uncertainty_draws.csv", index_label="draw_id")
    current = strategy_objectives[strategy_objectives.strategy_id == "current"].benefit.sum()
    rows = []
    quantile = float(settings["normal_interval_quantile"])
    for strategy_id, frame in strategy_kpis.groupby("strategy_id"):
        objective_frame = strategy_objectives[strategy_objectives.strategy_id == strategy_id]
        deterministic_ok = bool(frame.feasible.iloc[0])
        samples = {}
        for column, kpi in enumerate(kpi_names):
            item = frame[frame.kpi == kpi].iloc[0]
            sigma = (item.upper - item.lower) / (2 * quantile)
            samples[kpi] = np.maximum(0.0, item.prediction + sigma * draws[:, column])
        service_ok = (samples["placements"] >= 75) & (samples["outreach_participants"] >= 15)
        benefit_draws = np.zeros(len(draws))
        for family, details in base_config["objective_families"].items():
            family_draws = np.zeros(len(draws))
            for component in details["components"]:
                bounds = component["normalization"]
                normalized = np.clip((samples[component["kpi"]] - bounds["minimum"]) /
                                     (bounds["maximum"] - bounds["minimum"]), 0, 1)
                family_draws += component["weight"] * normalized
            benefit_draws += family_draws
        rows.append({
            "strategy_id": strategy_id,
            "draw_artifact": "common_uncertainty_draws.csv",
            "draws": len(draws),
            "deterministic_resource_feasible": deterministic_ok,
            "feasibility_probability": float(np.mean(service_ok) if deterministic_ok else 0.0),
            "downside_probability_below_current_total_benefit": float(np.mean(benefit_draws < current)),
            "total_benefit_p05": float(np.quantile(benefit_draws, 0.05)),
            "total_benefit_p50": float(np.quantile(benefit_draws, 0.50)),
            "total_benefit_p95": float(np.quantile(benefit_draws, 0.95)),
        })
    pd.DataFrame(rows).to_csv(root / "strategy_uncertainty.csv", index=False)


def _public_only(root, public_root):
    public = pd.read_csv(public_root / "public_only.csv")
    values = {row.field: float(row.value) for row in public.itertuples() if row.field in {"placements", "higher_studies", "eligible_students", "graduating_students"}}
    rows = []
    for denominator in ("eligible_students", "graduating_students"):
        for outcome in ("placements", "higher_studies"):
            rows.append({"analysis_track": "public_only_descriptive", "outcome": outcome,
                         "denominator": denominator, "numerator": values[outcome],
                         "denominator_value": values[denominator], "rate": values[outcome] / values[denominator],
                         "source_artifact": "artifacts/public_data/vjti_ceit_v1/public_only.csv",
                         "causal_claim": False})
    pd.DataFrame(rows).to_csv(root / "public_only_sensitivity.csv", index=False)


def _svg(root, objectives):
    pivot = objectives.pivot(index="strategy_id", columns="objective", values="benefit").reset_index()
    width, height = 760, 460
    circles = []
    for index, row in pivot.iterrows():
        x = 70 + 620 * float(row.research)
        y = 390 - 320 * float(row.student_development)
        circles.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#2563eb"><title>{row.strategy_id}</title></circle>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="white"/><text x="20" y="25" font-family="sans-serif" font-size="17">Research vs student-development predicted benefit</text>
<line x1="70" y1="390" x2="690" y2="390" stroke="#111"/><line x1="70" y1="390" x2="70" y2="70" stroke="#111"/>
<text x="300" y="435" font-family="sans-serif" font-size="13">Research benefit (0–1)</text><text x="18" y="250" transform="rotate(-90 18 250)" font-family="sans-serif" font-size="13">Student-development benefit (0–1)</text>
{''.join(circles)}</svg>'''
    (root / "tradeoff_research_student.svg").write_text(svg, encoding="utf-8")
    totals = objectives.groupby("strategy_id", as_index=False).agg(
        total_benefit=("benefit", "sum"), total_cost=("total_cost", "first")
    )
    points = []
    for row in totals.itertuples():
        x = 70 + 620 * (float(row.total_cost) - 20_000_000) / 25_000_000
        y = 390 - 80 * float(row.total_benefit)
        points.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#059669"><title>{row.strategy_id}</title></circle>')
    cost_svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="white"/><text x="20" y="25" font-family="sans-serif" font-size="17">Cost vs total predicted benefit</text>
<line x1="70" y1="390" x2="690" y2="390" stroke="#111"/><line x1="70" y1="390" x2="70" y2="70" stroke="#111"/>
<text x="300" y="435" font-family="sans-serif" font-size="13">Total cost (INR)</text><text x="18" y="250" transform="rotate(-90 18 250)" font-family="sans-serif" font-size="13">Total benefit</text>
{''.join(points)}</svg>'''
    (root / "tradeoff_cost_benefit.svg").write_text(cost_svg, encoding="utf-8")


def _actions_and_resources(root, base_config):
    allocations = pd.read_csv(root / "strategy_allocations.csv")
    current = allocations[allocations.strategy_id == "current"].set_index("decision").value
    actions = allocations.copy()
    actions["current_value"] = actions.decision.map(current)
    actions["delta_from_current"] = actions.value - actions.current_value
    actions["action"] = np.where(
        np.isclose(actions.delta_from_current, 0), "hold",
        np.where(actions.delta_from_current > 0, "increase", "decrease"),
    )
    actions.to_csv(root / "current_vs_strategy_actions.csv", index=False)
    effort_names = set(base_config["effort_decisions"])
    rows = []
    for strategy_id, frame in allocations.groupby("strategy_id"):
        first = frame.iloc[0]
        effort = frame[frame.decision.isin(effort_names)].value.sum()
        rows.append({
            "strategy_id": strategy_id, "strategy_type": first.strategy_type,
            "scenario": first.scenario, "total_cost": first.total_cost,
            "budget_remaining": first.budget_remaining,
            "allocated_faculty_fte": effort,
            "resource_feasible": first.feasible,
            "constraint_artifact": "strategy_constraints.csv",
        })
    pd.DataFrame(rows).to_csv(root / "strategy_resource_summary.csv", index=False)


def _checks(root, config, comparison_runs, metrics):
    rows = []
    expected = len(config["algorithms"]) * len(config["comparison_seeds"])
    rows.append(("declared_comparison_runs_complete", len(comparison_runs) == expected and all(x["status"] == "complete" for x in comparison_runs), f"{len(comparison_runs)}/{expected}"))
    accounting_ok = True
    for status in comparison_runs:
        if status["status"] != "complete":
            accounting_ok = False
            continue
        accounting = json.loads((root / status["status_artifact"].replace("status.json", "accounting.json")).read_text())
        accounting_ok &= accounting["candidate_evaluations_total"] == config["matched_candidate_evaluations"]
    rows.append(("matched_accounting_independently_checked", accounting_ok, str(config["matched_candidate_evaluations"])))
    independent_ok = True
    for row in metrics[metrics.status == "complete"].itertuples():
        archive = pd.read_csv(root / row.status_artifact.replace("status.json", "archive.csv"))
        points = archive[[f"objective__{name}" for name in FAMILIES]].to_numpy(float) if len(archive) else np.empty((0, 4))
        independent_ok &= np.isclose(hypervolume(points, np.full(4, 0.05)), row.hypervolume, equal_nan=True)
    rows.append(("metrics_independently_recomputed", independent_ok, "hypervolume from saved archives"))
    objectives = pd.read_csv(root / "strategy_objectives.csv")
    rows.append(("synthetic_coverage_complete", objectives.groupby("strategy_id").objective.nunique().eq(4).all(), "four rows per strategy"))
    allocations = pd.read_csv(root / "strategy_allocations.csv")
    recommendations = allocations[allocations.strategy_type.isin(["policy_selection", "scenario_reoptimization"])]
    rows.append(("recommendations_feasible", bool(recommendations.feasible.all()), "saved evaluator results"))
    rows.append(("support_warning_visible", "out_of_support" in recommendations.columns and "out_of_support_features" in recommendations.columns, "columns retained"))
    checks = pd.DataFrame(rows, columns=["check", "passed", "detail"])
    checks.to_csv(root / "independent_checks.csv", index=False)
    return bool(checks.passed.all())


def build_report_from_artifacts(output_root):
    """Read only saved CSV/JSON artifacts; never invoke the evaluator."""
    root = Path(output_root)
    summary = pd.read_csv(root / "algorithm_summary.csv")
    allocations = pd.read_csv(root / "strategy_allocations.csv")
    objectives = pd.read_csv(root / "strategy_objectives.csv")
    uncertainty = pd.read_csv(root / "strategy_uncertainty.csv")
    checks = pd.read_csv(root / "independent_checks.csv")
    selection = pd.read_csv(root / "strategy_selection_log.csv")
    manifest = json.loads((root / "experiment_manifest.json").read_text())
    recommendation_ids = allocations[allocations.strategy_type.isin(["policy_selection", "scenario_reoptimization"])].strategy_id.unique()
    lines = [
        "# VJTI public-plus-synthetic experiment report", "",
        f"Protocol `{manifest['analysis_id']}` was frozen before pilot. Final comparison: **{manifest['completed_comparison_runs']}/{manifest['declared_comparison_runs']} complete**; matched budget **{manifest['matched_candidate_evaluations']}** per run (`algorithm_metrics.csv`, run accounting JSON).", "",
        "## Evidence boundary", "",
        manifest["claims"]["prediction"], manifest["claims"]["causal"], manifest["claims"]["dea"], "",
        "Public-only placement/higher-study denominator sensitivity is isolated in `public_only_sensitivity.csv`; all allocation recommendations are mixed public-plus-synthetic scenario results.", "",
        "## Algorithm comparison", "",
        "| Algorithm | Runs | Median HV | Median IGD | Mean feasible rate |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in summary.itertuples():
        lines.append(f"| {row.algorithm} | {row.runs} | {row.hypervolume_median:.6f} | {row.igd_median:.6f} | {row.feasible_rate_mean:.3f} |")
    lines += ["", "Values come from `algorithm_summary.csv`; the pooled comparison front is `pooled_reference_front.csv`.", "",
              "## Portfolio and scenarios", "",
              f"The artifact portfolio contains **{allocations.strategy_id.nunique()} strategies**, including current, supported policy preferences, and held-fixed/reoptimized scenario pairs. **{len(recommendation_ids)} recommendation records** are retained. Duplicate and no-match outcomes remain in `strategy_selection_log.csv` (rows: " + str(len(selection)) + ").", "",
              "Allocations and concrete increase/decrease/hold actions: `strategy_allocations.csv` and `current_vs_strategy_actions.csv`; KPI intervals: `strategy_kpis.csv`; constraints/resources: `strategy_constraints.csv` and `strategy_resource_summary.csv`; objective evidence and synthetic coverage: `strategy_objectives.csv`; uncertainty: `strategy_uncertainty.csv` using `common_uncertainty_draws.csv`.", "",
              "Every recommendation row carries feasibility and model-support fields. An out-of-support recommendation is a visible warning, not validation. Held-fixed results are evaluated without repair; scenario reoptimization is separately labeled.", "",
              "## Uncertainty and context", "",
              f"Common draws were applied to **{len(uncertainty)} strategies**. Downside means total predicted benefit below the saved current-strategy threshold; feasibility combines deterministic resource feasibility with uncertain service KPI thresholds (`strategy_uncertainty.csv`).", "",
              "DEA context is copied in `dea_context.json` and remains a calibrated synthetic method fixture. Prediction intervals quantify model/scenario uncertainty; they do not identify causal impact.", "",
              "![Research/student trade-off](tradeoff_research_student.svg)", "",
              "![Cost/benefit trade-off](tradeoff_cost_benefit.svg)", "",
              "## Independent checks", ""]
    for row in checks.itertuples():
        lines.append(f"- {'PASS' if row.passed else 'FAIL'} — `{row.check}`: {row.detail}")
    lines += ["", "The manifest hashes every report input. Rebuilding this report reads saved artifacts only."]
    (root / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return root / "report.md"


def run_public_experiments(config_path):
    config_path = Path(config_path).resolve()
    repo = config_path.parents[2]
    config = json.loads(config_path.read_text(encoding="utf-8"))
    allocation_path = _resolve(repo, config["allocation_config"])
    model_root = _resolve(repo, config["prompt15_root"])
    public_root = _resolve(repo, config["prompt14_root"])
    root = _resolve(repo, config["output_root"])
    root.mkdir(parents=True, exist_ok=True)
    base_config = json.loads(allocation_path.read_text(encoding="utf-8"))
    base_problem = VJTIPublicAllocationProblem(base_config, model_root)
    budget = int(config["matched_candidate_evaluations"])

    # Pilot uses the already-frozen final parameters; its outputs are excluded from final metrics.
    for name, parameters in config["algorithms"].items():
        _run_one(root, "pilot", name, parameters, int(config["pilot_seed"]), base_problem, budget)
    _json(root / "pilot/protocol_decision.json", {
        "decision": "no_change_allowed_or_made_after_pilot", "config_sha256": _sha256(config_path),
        "pilot_purpose": "execution and artifact-contract check only; no performance-based tuning",
    })

    for seed in config["comparison_seeds"]:
        for name, parameters in config["algorithms"].items():
            _run_one(root, "comparison", name, parameters, int(seed), base_problem, budget)
    scenario_seed = int(config["comparison_seeds"][0])
    for scenario in config["scenarios"]:
        problem = VJTIPublicAllocationProblem(_scenario_config(base_config, scenario), model_root)
        _run_one(root, f"scenario_{scenario['name']}", "nsga2", config["algorithms"]["nsga2"], scenario_seed, problem, budget)

    comparison_runs = _read_runs(root, "comparison")
    objective_columns = [f"objective__{name}" for name in FAMILIES]
    metrics = _comparison_metrics(root, comparison_runs, objective_columns)
    first = _select_portfolio(root, base_config, model_root, config["policy_preferences"])
    second = _scenario_strategies(root, config["scenarios"], base_config, model_root, scenario_seed)
    filenames = ("strategy_allocations.csv", "strategy_kpis.csv", "strategy_objectives.csv", "strategy_constraints.csv")
    for filename, base_rows, scenario_rows in zip(filenames, first[:4], second[:4]):
        pd.DataFrame(base_rows + scenario_rows).to_csv(root / filename, index=False)
    pd.DataFrame(first[4] + second[4]).to_csv(root / "strategy_selection_log.csv", index=False)
    strategy_kpis = pd.read_csv(root / "strategy_kpis.csv")
    strategy_objectives = pd.read_csv(root / "strategy_objectives.csv")
    _actions_and_resources(root, base_config)
    _uncertainty(root, base_config, strategy_kpis, strategy_objectives, config["uncertainty"])
    _public_only(root, public_root)
    _svg(root, strategy_objectives)
    (root / "dea_context.json").write_text((model_root / "dea_summary.json").read_text(encoding="utf-8"), encoding="utf-8")
    checks_passed = _checks(root, config, comparison_runs, metrics)

    declared = len(config["algorithms"]) * len(config["comparison_seeds"])
    manifest = {
        "analysis_id": config["analysis_id"], "protocol_status": config["protocol_status"],
        "config_sha256": _sha256(config_path), "allocation_config_sha256": _sha256(allocation_path),
        "model_manifest_sha256": _sha256(model_root / "model_manifest.json"),
        "public_manifest_sha256": _sha256(public_root / "manifest.json"),
        "matched_candidate_evaluations": budget, "declared_comparison_runs": declared,
        "completed_comparison_runs": sum(item["status"] == "complete" for item in comparison_runs),
        "scenario_count": len(config["scenarios"]), "common_uncertainty_seed": config["uncertainty"]["seed"],
        "claims": config["claims"], "python": platform.python_version(), "platform": platform.platform(),
        "checks_passed": checks_passed,
    }
    _json(root / "experiment_manifest.json", manifest)
    build_report_from_artifacts(root)
    manifest["artifact_hashes"] = {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in sorted(root.glob("*")) if path.is_file() and path.name not in {"experiment_manifest.json", "report.md"}
    }
    _json(root / "experiment_manifest.json", manifest)
    build_report_from_artifacts(root)
    return {"output_root": str(root), "checks_passed": checks_passed,
            "completed_comparison_runs": manifest["completed_comparison_runs"], "declared_comparison_runs": declared}
