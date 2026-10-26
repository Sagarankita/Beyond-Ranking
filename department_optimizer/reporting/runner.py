"""Build a decision portfolio and report exclusively from saved validated artifacts."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from department_optimizer.allocation.problem import OBJECTIVE_FAMILIES


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write_json(path, payload):
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _read_inputs(config):
    robustness = Path(config["robustness_root"])
    benchmark = Path(config["benchmark_root"])
    paths = {
        "selected": robustness / "selected_strategies.csv",
        "candidates": robustness / "reoptimized_candidates.csv",
        "monte_carlo": robustness / "monte_carlo_summary.csv",
        "sensitivity": robustness / "assumption_sensitivity.csv",
        "scenario_catalog": robustness / "scenario_catalog.csv",
        "fixed_comparison": robustness / "fixed_vs_reoptimized_comparison.csv",
        "benchmark_summary": benchmark / "summary_median_iqr.csv",
        "benchmark_metrics": benchmark / "per_seed_metrics.csv",
        "benchmark_completion": benchmark / "completion.json",
        "reference": Path(config["reference_evaluation"]),
        "allocation": Path(config["allocation_config"]),
    }
    missing = [str(path) for path in paths.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"required saved report inputs are missing: {missing}")
    return paths


def _match_monte_carlo(row, monte_carlo, scenario, policy=None):
    subset = monte_carlo[
        (monte_carlo["assessment_mode"] == "reoptimized")
        & (monte_carlo["assessed_scenario_id"] == scenario)
        & (monte_carlo["assumption_id"] == "base")
    ]
    if policy is None:
        return None
    policy_rows = subset[subset["policy"] == policy]
    return policy_rows.iloc[0] if not policy_rows.empty else None


def select_portfolio(config, allocation_config, selected, candidates, monte_carlo, reference):
    """Apply declared post-optimization rules without reevaluating candidates."""
    scenario = config["portfolio_scenario"]
    variable_names = [item["name"] for item in allocation_config["decision_variables"]]
    selected_scenario = selected[
        (selected["scenario_id"] == scenario)
        & (selected["selection_status"] == "selected")
    ].copy()
    candidate_scenario = candidates[
        (candidates["scenario_id"] == scenario) & candidates["feasible"].astype(bool)
    ].drop_duplicates(subset=variable_names)
    if selected_scenario.empty or candidate_scenario.empty:
        raise RuntimeError(f"no saved feasible strategies for {scenario}")

    portfolio = []
    policy_names = ["balanced", "research_first", "innovation_first", "student_first"]
    for policy in policy_names:
        rows = selected_scenario[selected_scenario["policy"] == policy]
        if rows.empty:
            portfolio.append(
                {
                    "strategy": policy,
                    "selection_status": "missing_policy_selection",
                    "selection_rule": config["strategy_rules"][policy],
                }
            )
            continue
        row = rows.iloc[0].to_dict()
        row.update(
            strategy=policy,
            source_policy=policy,
            selection_rule=config["strategy_rules"][policy],
            knee_status="not_used",
        )
        mc = _match_monte_carlo(row, monte_carlo, scenario, policy)
        if mc is not None:
            row.update(
                probability_feasible=float(mc["probability_feasible"]),
                research_benefit_p10_downside=float(mc["research_benefit_p10_downside"]),
                papers_t1_p10_downside=float(mc["papers_t1_p10_downside"]),
                citation_percentile_avg_p10_downside=float(
                    mc["citation_percentile_avg_p10_downside"]
                ),
            )
        portfolio.append(row)

    robust = [
        row
        for row in portfolio
        if row.get("selection_status") == "selected"
        and row.get("probability_feasible", -1) >= float(config["robustness_threshold"])
    ]
    if robust:
        conservative_source = sorted(
            robust,
            key=lambda row: (-row["research_benefit_p10_downside"], row["cost"]),
        )[0]
        conservative = dict(conservative_source)
        conservative.update(
            strategy="conservative",
            source_policy=conservative_source["strategy"],
            selection_rule=config["strategy_rules"]["conservative"],
            knee_status="not_used",
            unsupported_preference_weight=0.0,
        )
    else:
        conservative = {
            "strategy": "conservative",
            "selection_status": "no_strategy_meets_robustness_threshold",
            "selection_rule": config["strategy_rules"]["conservative"],
        }
    portfolio.insert(0, conservative)

    supported = reference["evaluation"]["objective_supported"]
    supported_columns = [
        f"objective_benefit__{name}" for name in OBJECTIVE_FAMILIES if supported[name]
    ]
    varying = [
        column for column in supported_columns if candidate_scenario[column].nunique() > 1
    ]
    distances = np.zeros(len(candidate_scenario))
    for column in supported_columns:
        values = candidate_scenario[column].to_numpy(dtype=float)
        span = values.max() - values.min()
        if span > 1e-12:
            distances += ((values.max() - values) / span) ** 2
    compromise_source = candidate_scenario.assign(
        distance_to_supported_ideal=np.sqrt(distances)
    ).sort_values(["distance_to_supported_ideal", "cost"], kind="stable").iloc[0]
    compromise = compromise_source.to_dict()
    compromise.update(
        strategy="compromise",
        source_policy="supported_objective_ideal_distance",
        selection_status="selected",
        selection_rule=config["strategy_rules"]["compromise"],
        knee_status=(
            "available" if len(varying) >= 2
            else "unavailable_fewer_than_two_varying_supported_objectives"
        ),
        unsupported_preference_weight=0.0,
    )
    allocation_match = selected_scenario.copy()
    for name in variable_names:
        allocation_match = allocation_match[np.isclose(allocation_match[name], compromise[name])]
    policy = allocation_match.iloc[0]["policy"] if not allocation_match.empty else None
    mc = _match_monte_carlo(compromise, monte_carlo, scenario, policy)
    if mc is not None:
        compromise.update(
            probability_feasible=float(mc["probability_feasible"]),
            research_benefit_p10_downside=float(mc["research_benefit_p10_downside"]),
            papers_t1_p10_downside=float(mc["papers_t1_p10_downside"]),
            citation_percentile_avg_p10_downside=float(
                mc["citation_percentile_avg_p10_downside"]
            ),
        )
    portfolio.append(compromise)

    result = pd.DataFrame(portfolio)
    successful = result[result["selection_status"] == "selected"].copy()
    group_keys = {}
    for index, row in successful.iterrows():
        key = tuple(float(row[name]) for name in variable_names)
        if key not in group_keys:
            group_keys[key] = f"allocation_{len(group_keys) + 1}"
        result.loc[index, "allocation_group"] = group_keys[key]
    counts = result["allocation_group"].value_counts()
    result["duplicates_another_strategy"] = result["allocation_group"].map(counts).fillna(0) > 1
    return result


def _allocation_comparison(portfolio, allocation_config, reference):
    current = reference["evaluation"]["repaired"]
    variables = {item["name"]: item for item in allocation_config["decision_variables"]}
    rows = []
    for _, strategy in portfolio[portfolio.selection_status == "selected"].iterrows():
        for name, variable in variables.items():
            value = float(strategy[name])
            rows.append(
                {
                    "strategy": strategy["strategy"],
                    "allocation_group": strategy["allocation_group"],
                    "variable": name,
                    "unit": variable["unit"],
                    "current": float(current[name]),
                    "recommended": value,
                    "difference": value - float(current[name]),
                }
            )
    return pd.DataFrame(rows)


def _kpi_comparison(portfolio, reference):
    current = reference["evaluation"]
    rows = []
    for _, strategy in portfolio[portfolio.selection_status == "selected"].iterrows():
        for kpi, value in current["raw_kpis"].items():
            recommended = float(strategy[f"kpi__{kpi}"])
            rows.append(
                {
                    "strategy": strategy["strategy"],
                    "allocation_group": strategy["allocation_group"],
                    "kpi": kpi,
                    "current_prediction": value,
                    "current_lower": current["uncertainty"][kpi]["lower"],
                    "current_upper": current["uncertainty"][kpi]["upper"],
                    "recommended_prediction": recommended,
                    "recommended_lower": float(strategy[f"lower__{kpi}"]),
                    "recommended_upper": float(strategy[f"upper__{kpi}"]),
                    "predicted_difference": recommended - value,
                    "monte_carlo_p10_downside": strategy.get(f"{kpi}_p10_downside", np.nan),
                }
            )
    return pd.DataFrame(rows)


def _resource_utilization(portfolio, allocation_config, reference, scenario_catalog, scenario):
    catalog_row = scenario_catalog[scenario_catalog.scenario_id == scenario].iloc[0]
    budget = float(catalog_row.budget_limit)
    context = allocation_config["fixed_context"]
    faculty_capacity = float(allocation_config["faculty_time"]["capacity_fte"])

    def row(label, allocation, cost):
        research_fte = (
            float(context["faculty_phd"]) * float(allocation["frac_research_phd"])
            + float(context["faculty_other"]) * float(allocation["frac_research_other"])
        )
        return {
            "strategy": label,
            "cost": float(cost),
            "budget_limit": budget,
            "budget_utilization": float(cost) / budget,
            "budget_remaining": budget - float(cost),
            "research_fte": research_fte,
            "research_fte_capacity": faculty_capacity,
            "research_fte_utilization": research_fte / faculty_capacity,
        }

    current = reference["evaluation"]
    rows = [row("current_reference", current["repaired"], current["cost"])]
    for _, strategy in portfolio[portfolio.selection_status == "selected"].iterrows():
        rows.append(row(strategy["strategy"], strategy, strategy["cost"]))
    return pd.DataFrame(rows)


def _constraint_checks(portfolio, reference):
    rows = []
    for name, residual in reference["evaluation"]["constraint_residuals"].items():
        rows.append(
            {
                "strategy": "current_reference",
                "constraint": name,
                "residual": residual,
                "passed": float(residual) <= 1e-9,
            }
        )
    columns = [column for column in portfolio if column.startswith("constraint__")]
    for _, strategy in portfolio[portfolio.selection_status == "selected"].iterrows():
        for column in columns:
            residual = float(strategy[column])
            rows.append(
                {
                    "strategy": strategy["strategy"],
                    "constraint": column.removeprefix("constraint__"),
                    "residual": residual,
                    "passed": residual <= 1e-9,
                }
            )
    return pd.DataFrame(rows)


def _actions(allocation_comparison):
    rows = []
    verbs = {
        "research_budget": ("Increase", "Reduce", "Maintain"),
        "frac_research_phd": ("Increase", "Reduce", "Maintain"),
        "frac_research_other": ("Increase", "Reduce", "Maintain"),
        "centres_of_excellence_count": ("Add", "Remove", "Maintain"),
        "industry_collaboration_support_count": ("Add", "Remove", "Maintain"),
    }
    for _, item in allocation_comparison.iterrows():
        difference = float(item["difference"])
        increase, decrease, maintain = verbs[item["variable"]]
        if abs(difference) <= 1e-12:
            action = f"{maintain} {item['variable']} at {item['recommended']:g} {item['unit']}."
        elif item["variable"] == "research_budget":
            verb = increase if difference > 0 else decrease
            action = (
                f"{verb} research funding by INR {abs(difference):,.0f} "
                f"to INR {item['recommended']:,.0f}."
            )
        elif difference > 0:
            action = (
                f"{increase} {item['variable']} by {difference:g} {item['unit']} "
                f"to {item['recommended']:g}."
            )
        else:
            action = (
                f"{decrease} {item['variable']} by {abs(difference):g} {item['unit']} "
                f"to {item['recommended']:g}."
            )
        rows.append(
            {
                "strategy": item["strategy"],
                "variable": item["variable"],
                "action": action,
            }
        )
    return pd.DataFrame(rows)


def _algorithm_table(summary):
    wanted = summary[summary.metric.isin(["hypervolume", "igd", "spacing", "feasible_solution_rate", "runtime_seconds"])]
    rows = []
    for (algorithm, metric), group in wanted.groupby(["algorithm", "metric"]):
        item = group.iloc[0]
        rows.append(
            {
                "algorithm": algorithm,
                "metric": metric,
                "runs": int(item["observations"]),
                "median": item["median"],
                "q1": item["q1"],
                "q3": item["q3"],
                "interpretation": "higher_is_better" if metric in {"hypervolume", "feasible_solution_rate"} else "lower_is_better",
            }
        )
    return pd.DataFrame(rows)


def _svg_frame(width, height, body, title):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        '<rect width="100%" height="100%" fill="#ffffff"/>'
        f'<text x="{width/2}" y="28" text-anchor="middle" font-family="sans-serif" font-size="18" font-weight="bold">{html.escape(title)}</text>'
        + body
        + "</svg>\n"
    )


def _pareto_svg(path, candidates, portfolio, scenario):
    data = candidates[candidates.scenario_id == scenario]
    x = data["cost"].to_numpy(dtype=float) / 1_000_000
    y = data["objective_benefit__research"].to_numpy(dtype=float)
    width, height, margin = 720, 430, 65
    xmin, xmax = float(x.min()), float(x.max())
    ymin, ymax = float(y.min()), float(y.max())
    if xmax <= xmin: xmax = xmin + 1
    if ymax <= ymin: ymax = ymin + 1
    sx = lambda value: margin + (value - xmin) / (xmax - xmin) * (width - 2 * margin)
    sy = lambda value: height - margin - (value - ymin) / (ymax - ymin) * (height - 2 * margin)
    body = [
        f'<line x1="{margin}" y1="{height-margin}" x2="{width-margin}" y2="{height-margin}" stroke="#333"/>',
        f'<line x1="{margin}" y1="{margin}" x2="{margin}" y2="{height-margin}" stroke="#333"/>',
        f'<text x="{width/2}" y="{height-15}" text-anchor="middle" font-family="sans-serif" font-size="13">Cost (INR millions; reporting dimension)</text>',
        f'<text x="18" y="{height/2}" transform="rotate(-90 18 {height/2})" text-anchor="middle" font-family="sans-serif" font-size="13">Research benefit</text>',
    ]
    for xv, yv in zip(x, y):
        body.append(f'<circle cx="{sx(xv):.1f}" cy="{sy(yv):.1f}" r="4" fill="#4c78a8" opacity="0.55"/>')
    for _, row in portfolio[portfolio.selection_status == "selected"].drop_duplicates("allocation_group").iterrows():
        body.append(f'<circle cx="{sx(row.cost/1_000_000):.1f}" cy="{sy(row["objective_benefit__research"]):.1f}" r="8" fill="#e45756" stroke="#8b1a1a"/>')
        body.append(f'<text x="{sx(row.cost/1_000_000)+10:.1f}" y="{sy(row["objective_benefit__research"])-8:.1f}" font-family="sans-serif" font-size="11">{html.escape(row.allocation_group)}</text>')
    Path(path).write_text(_svg_frame(width, height, "".join(body), "Saved feasible candidates and selected portfolio"))


def _algorithm_svg(path, algorithm_table):
    data = algorithm_table[algorithm_table.metric == "hypervolume"].sort_values("median")
    width, height, left = 720, 400, 150
    maximum = float(data["median"].max()) or 1
    bar_height = 32
    body = []
    for position, (_, row) in enumerate(data.iterrows()):
        y = 55 + position * 50
        bar = float(row["median"]) / maximum * (width - left - 70)
        body.extend(
            [
                f'<text x="{left-10}" y="{y+21}" text-anchor="end" font-family="sans-serif" font-size="13">{html.escape(row.algorithm)}</text>',
                f'<rect x="{left}" y="{y}" width="{bar:.1f}" height="{bar_height}" fill="#59a14f"/>',
                f'<text x="{left+bar+7:.1f}" y="{y+21}" font-family="sans-serif" font-size="11">{row["median"]:.6f}</text>',
            ]
        )
    Path(path).write_text(_svg_frame(width, height, "".join(body), "Smoke benchmark median hypervolume (3 seeds)"))


def _scenario_svg(path, monte_carlo):
    data = monte_carlo[
        (monte_carlo.assessment_mode == "reoptimized")
        & (monte_carlo.assumption_id == "base")
        & (monte_carlo.policy == "balanced")
    ]
    width, height, left = 820, 430, 245
    body = []
    for position, (_, row) in enumerate(data.iterrows()):
        y = 55 + position * 63
        bar = float(row.probability_feasible) * (width - left - 80)
        body.extend(
            [
                f'<text x="{left-10}" y="{y+20}" text-anchor="end" font-family="sans-serif" font-size="12">{html.escape(row.assessed_scenario_id)}</text>',
                f'<rect x="{left}" y="{y}" width="{bar:.1f}" height="28" fill="#f28e2b"/>',
                f'<text x="{left+bar+8:.1f}" y="{y+19}" font-family="sans-serif" font-size="11">{row.probability_feasible:.3f}; papers p10 {row.papers_t1_p10_downside:.2f}</text>',
            ]
        )
    Path(path).write_text(_svg_frame(width, height, "".join(body), "Reoptimized feasibility and downside by scenario"))


def _markdown_table(frame, columns, formats=None):
    formats = formats or {}
    labels = [column.replace("_", " ").title() for column in columns]
    lines = ["| " + " | ".join(labels) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for _, row in frame.iterrows():
        values = []
        for column in columns:
            value = row[column]
            values.append(formats[column](value) if column in formats and pd.notna(value) else str(value))
        lines.append("| " + " | ".join(values) + " |")
    return lines


def _write_report(path, config, portfolio, allocations, kpis, resources, constraints, actions, algorithms, scenario_summary, sensitivity):
    unique = portfolio[portfolio.selection_status == "selected"].drop_duplicates("allocation_group")
    failed_constraints = constraints[~constraints.passed.astype(bool)]
    lines = [
        "# Department allocation strategy portfolio",
        "",
        "> **Synthetic methodological prototype.** The current allocation is illustrative, and modeled KPI changes are not causal estimates.",
        "",
        "## Decision summary",
        "",
        f"Six declared selection rules produced {len(unique)} unique allocation(s). Repeated labels are retained and explicitly linked through `allocation_group` rather than presented as independent choices.",
        "",
    ]
    portfolio_view = portfolio[["strategy", "selection_status", "allocation_group", "duplicates_another_strategy", "probability_feasible", "unsupported_preference_weight", "knee_status"]].copy()
    lines += _markdown_table(portfolio_view, list(portfolio_view.columns), {"probability_feasible": lambda x: f"{x:.3f}", "unsupported_preference_weight": lambda x: f"{x:.2f}"})
    lines += ["", "Declared selection rules:", ""]
    for _, strategy in portfolio.iterrows():
        lines.append(f"- **{strategy['strategy']}**: {strategy['selection_rule']}")
    lines += [
        "",
        "A Pareto knee cannot be identified because only one supported objective varies. The compromise rule therefore uses distance to the supported-objective ideal. Innovation-first and student-first carry 90% weight on unsupported objective families and cannot substantiate those policy labels.",
        "",
        "![Saved candidate trade-off](pareto_tradeoff.svg)",
        "",
        "## Current versus optimized allocation",
        "",
    ]
    allocation_unique = allocations[allocations.strategy == unique.iloc[0].strategy]
    lines += _markdown_table(allocation_unique, ["variable", "unit", "current", "recommended", "difference"], {"current": lambda x: f"{x:,.2f}", "recommended": lambda x: f"{x:,.2f}", "difference": lambda x: f"{x:,.2f}"})
    lines += ["", "Concrete actions for the unique recommendation:", ""]
    for action in actions[actions.strategy == unique.iloc[0].strategy].action:
        lines.append(f"- {action}")
    lines += ["", "## Predicted outcomes and resources", ""]
    kpi_unique = kpis[kpis.strategy == unique.iloc[0].strategy]
    lines += _markdown_table(kpi_unique, ["kpi", "current_prediction", "recommended_prediction", "predicted_difference", "recommended_lower", "recommended_upper", "monte_carlo_p10_downside"], {column: lambda x: f"{x:.4f}" for column in ["current_prediction", "recommended_prediction", "predicted_difference", "recommended_lower", "recommended_upper", "monte_carlo_p10_downside"]})
    lines += [""]
    resource_view = resources[resources.strategy.isin(["current_reference", unique.iloc[0].strategy])]
    lines += _markdown_table(resource_view, ["strategy", "cost", "budget_utilization", "research_fte", "research_fte_utilization"], {"cost": lambda x: f"INR {x:,.0f}", "budget_utilization": lambda x: f"{x:.1%}", "research_fte": lambda x: f"{x:.2f}", "research_fte_utilization": lambda x: f"{x:.1%}"})
    lines += [
        "",
        f"All saved current and selected-strategy constraint rows pass: {failed_constraints.empty}. Constraint residuals and utilization are exported separately for audit.",
        "",
        "## Scenario robustness",
        "",
        "![Scenario robustness](scenario_robustness.svg)",
        "",
    ]
    scenario_view = scenario_summary[(scenario_summary.policy == "balanced") & (scenario_summary.assumption_id == "base")]
    lines += _markdown_table(scenario_view, ["assessment_mode", "assessed_scenario_id", "probability_feasible", "papers_t1_mean", "papers_t1_p10_downside", "research_benefit_mean"], {column: lambda x: f"{x:.3f}" for column in ["probability_feasible", "papers_t1_mean", "papers_t1_p10_downside", "research_benefit_mean"]})
    lines += [
        "",
        "Held-fixed and reoptimized rows answer different questions: the former measures resilience of the base decision, while the latter permits adaptation. Low/base/high assumption results are available in `assumption_sensitivity.csv`; these are sensitivity cases rather than calibrated confidence levels.",
        "",
        "## Algorithm benchmark",
        "",
        "![Algorithm comparison](algorithm_comparison.svg)",
        "",
        "The algorithm table is a three-seed smoke benchmark with matched 100-candidate budgets. It supports integration checks and descriptive medians, not a best-algorithm claim.",
        "",
    ]
    hv = algorithms[algorithms.metric == "hypervolume"]
    lines += _markdown_table(hv, ["algorithm", "runs", "median", "q1", "q3"], {column: lambda x: f"{x:.6f}" for column in ["median", "q1", "q3"]})
    lines += [
        "",
        "## Method and evidence limits",
        "",
        "- The report reads saved outputs and does not implement or call a second scientific evaluator.",
        "- Only the research objective has a trained synthetic response model. Innovation, student, and societal benefits are unsupported zeros.",
        "- The illustrative current allocation is not an observed departmental baseline.",
        "- Prediction intervals and Monte Carlo assumptions do not establish causal intervention effects.",
        "- Patent and compute cost shocks remain unsupported because those decision variables are absent.",
        "- DEA remains a separate benchmarking analysis and is not applied as a causal multiplier.",
        "",
        "## Reproduction",
        "",
        "```bash",
        "make benchmark-smoke",
        "make robustness-smoke",
        "make strategy-report",
        "```",
        "",
        "The benchmark and robustness commands resume saved jobs. `make strategy-report` rebuilds this report from their validated artifacts.",
        "",
        "## Proposal traceability",
        "",
        "The portfolio supplies declared policy rules, baseline differences, predicted KPIs with uncertainty, constraint and resource checks, trade-off figures, algorithm summaries, scenario robustness, and reproducible commands. Empirical validation and unsupported KPI families remain open evidence gaps.",
    ]
    Path(path).write_text("\n".join(lines) + "\n")


def build_report(config_path, output_root=None):
    config_path = Path(config_path)
    config = json.loads(config_path.read_text())
    paths = _read_inputs(config)
    output = Path(output_root or config["output_root"])
    output.mkdir(parents=True, exist_ok=True)
    allocation_config = json.loads(paths["allocation"].read_text())
    reference = json.loads(paths["reference"].read_text())
    selected = pd.read_csv(paths["selected"])
    candidates = pd.read_csv(paths["candidates"])
    monte_carlo = pd.read_csv(paths["monte_carlo"])
    sensitivity = pd.read_csv(paths["sensitivity"])
    scenarios = pd.read_csv(paths["scenario_catalog"])
    benchmark_summary = pd.read_csv(paths["benchmark_summary"])

    portfolio = select_portfolio(
        config, allocation_config, selected, candidates, monte_carlo, reference
    )
    allocations = _allocation_comparison(portfolio, allocation_config, reference)
    kpis = _kpi_comparison(portfolio, reference)
    resources = _resource_utilization(
        portfolio, allocation_config, reference, scenarios, config["portfolio_scenario"]
    )
    constraints = _constraint_checks(portfolio, reference)
    actions = _actions(allocations)
    algorithms = _algorithm_table(benchmark_summary)
    scenario_summary = monte_carlo.copy()

    outputs = {
        "strategy_portfolio.csv": portfolio,
        "current_vs_strategy_allocations.csv": allocations,
        "current_vs_strategy_kpis.csv": kpis,
        "resource_utilization.csv": resources,
        "constraint_checks.csv": constraints,
        "department_actions.csv": actions,
        "algorithm_comparison.csv": algorithms,
        "scenario_robustness.csv": scenario_summary,
        "assumption_sensitivity.csv": sensitivity,
    }
    for name, frame in outputs.items():
        frame.to_csv(output / name, index=False)
    _pareto_svg(output / "pareto_tradeoff.svg", candidates, portfolio, config["portfolio_scenario"])
    _algorithm_svg(output / "algorithm_comparison.svg", algorithms)
    _scenario_svg(output / "scenario_robustness.svg", monte_carlo)
    _write_report(
        output / "report.md", config, portfolio, allocations, kpis, resources,
        constraints, actions, algorithms, scenario_summary, sensitivity,
    )
    traceability = pd.DataFrame(
        [
            ["policy portfolio", "strategy_portfolio.csv", "complete_with_unsupported_family_flags"],
            ["current comparison", "current_vs_strategy_allocations.csv", "illustrative_reference"],
            ["prediction uncertainty", "current_vs_strategy_kpis.csv", "synthetic_noncausal"],
            ["constraints and utilization", "constraint_checks.csv; resource_utilization.csv", "complete"],
            ["trade-off plots", "pareto_tradeoff.svg; scenario_robustness.svg", "one_supported_objective"],
            ["algorithm comparison", "algorithm_comparison.csv", "three_seed_smoke_only"],
            ["scenario robustness", "scenario_robustness.csv; assumption_sensitivity.csv", "complete_for_supported_inputs"],
        ],
        columns=["requirement", "artifact", "status"],
    )
    traceability.to_csv(output / "proposal_traceability.csv", index=False)
    _write_json(
        output / "manifest.json",
        {
            "report_id": config["report_id"],
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "evidence_status": config["evidence_status"],
            "reference_status": config["reference_status"],
            "config_path": str(config_path),
            "config_sha256": _sha256(config_path),
            "source_artifacts": {
                name: {"path": str(path), "sha256": _sha256(path)}
                for name, path in paths.items()
            },
            "selection_rules": config["strategy_rules"],
            "portfolio_scenario": config["portfolio_scenario"],
            "robustness_threshold": config["robustness_threshold"],
            "unique_selected_allocations": int(
                portfolio[portfolio.selection_status == "selected"]["allocation_group"].nunique()
            ),
            "environment": {
                "python": sys.version,
                "platform": platform.platform(),
                "numpy": np.__version__,
                "pandas": pd.__version__,
            },
        },
    )
    return output


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default="configs/reporting/phase7_synthetic.json"
    )
    parser.add_argument("--output-root")
    return parser.parse_args()


def main():
    args = parse_args()
    output = build_report(
        Path(args.config), Path(args.output_root) if args.output_root else None
    )
    portfolio = pd.read_csv(output / "strategy_portfolio.csv")
    unique = portfolio[portfolio.selection_status == "selected"].allocation_group.nunique()
    print(f"Strategy report complete: {output} ({unique} unique allocation(s))")


if __name__ == "__main__":
    main()
