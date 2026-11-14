from __future__ import annotations

from typing import Any, Mapping

from streamlit_app.data.adapters import title_case


def _value(value: float, unit: str) -> str:
    if unit == "INR":
        return f"INR {value:,.0f}"
    return f"{value:,.4g} {unit}"


def build_professor_summary(
    *,
    run_status: Mapping[str, Any],
    recommendation: Mapping[str, Any],
    sensitivity: Mapping[str, Any] | None = None,
) -> str:
    """Build a portable, deterministic Markdown summary from structured backend facts."""
    budget = recommendation["budget"]
    faculty = recommendation["faculty"]["proposed"]
    lines = [
        "# Beyond Ranking decision-support summary",
        "",
        "> Public-calibrated plus synthetic scenario output. This is not a policy directive or causal impact estimate.",
        "",
        "## Scenario and reproduction",
        "",
        f"- Run ID: `{run_status['run_id']}`",
        f"- Scenario hash: `{run_status['scenario_hash']}`",
        f"- Algorithm: {str(run_status['algorithm']).upper()}",
        f"- Seed: {run_status['seed']}",
        f"- Candidate evaluation budget: {run_status['evaluation_budget']}",
        f"- Candidate ID: `{recommendation['candidate_id']}`",
        f"- Recommendation ID: `{recommendation['recommendation_id']}`",
        f"- Evaluator: {recommendation['data_dependencies']['evaluator']}",
        "",
        "## Inputs and selected option",
        "",
        f"- Decision profile: {title_case(recommendation['profile'])}",
        f"- Available budget: {_value(budget['limit'], 'INR')}",
        f"- Proposed cost: {_value(budget['proposed'], 'INR')}",
        f"- Budget headroom: {_value(budget['headroom'], 'INR')}",
        f"- Available faculty capacity: {_value(faculty['available'], 'annual FTE')}",
        f"- Proposed controllable faculty use: {_value(faculty['used'], 'annual FTE')}",
        f"- Nominal feasibility: {'passed' if recommendation['nominal_feasible'] else 'failed'}",
        f"- Conservative-service feasibility: {'passed' if recommendation['robust_feasible'] else 'failed'}",
        f"- Selection rule: {recommendation['selection_rule']}",
        "",
        "## Proposed allocation changes",
        "",
        "| Activity | Action | Reference | Proposed | Change | Budget effect |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for item in recommendation["decision_changes"]:
        budget_effect = (
            "Not monetary"
            if item["budget_effect"] is None
            else _value(item["budget_effect"], "INR")
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    title_case(item["variable"]),
                    title_case(item["action"]),
                    _value(item["before"], item["unit"]),
                    _value(item["after"], item["unit"]),
                    _value(item["delta"], item["unit"]),
                    budget_effect,
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Modeled objective trade-offs",
            "",
            "| Objective family | Reference | Proposed | Difference | Scale |",
            "| --- | ---: | ---: | ---: | --- |",
        ]
    )
    for item in recommendation["objective_deltas"]:
        lines.append(
            f"| {title_case(item['name'])} | {item['reference']:.4f} | "
            f"{item['proposed']:.4f} | {item['difference']:+.4f} | {item['scale']} |"
        )

    lines.extend(["", "## Uncertainty and assumptions", ""])
    for warning in recommendation["support_warnings"]:
        lines.append(f"- {warning['message']}")
    lines.append("- Stored KPI intervals describe model uncertainty and are not causal policy-effect intervals.")
    lines.append("- Reference values are configured scenario values, not verified current spending.")
    lines.append("- Numerical values and feasibility come from structured backend fields, not generated prose.")

    lines.extend(["", "## Evidence and traceability", ""])
    lines.append(f"- Evidence class: `{recommendation['evidence_class']}`")
    lines.append(f"- Source run: `{recommendation['source_run_id']}`")
    lines.append(f"- Scenario dependency: `{recommendation['data_dependencies']['scenario_hash']}`")

    if sensitivity and sensitivity.get("status") == "complete":
        lines.extend(
            [
                "",
                "## Controlled factor diagnostic",
                "",
                f"- Factor: {title_case(sensitivity['factor'])}",
                f"- Change: {sensitivity['before']:,.4g} to {sensitivity['after']:,.4g} {sensitivity['unit']}",
                f"- Held fixed without repair: {'feasible' if sensitivity['held_fixed']['feasible'] else 'infeasible'}",
                f"- Reoptimized option: {'available' if sensitivity.get('reoptimized') else 'not supported'}",
                f"- Interpretation: {sensitivity['interpretation']}",
            ]
        )

    lines.extend(
        [
            "",
            "## Reproduce",
            "",
            "Start the API and Streamlit application using the repository README, then submit the same algorithm, seed, evaluation budget, and scenario inputs. Stable run and scenario identities allow the saved result to be traced.",
            "",
        ]
    )
    return "\n".join(lines)
