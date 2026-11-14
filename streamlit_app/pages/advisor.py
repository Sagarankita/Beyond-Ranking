from __future__ import annotations

import html
import json
import math
from typing import Any

import pandas as pd
import streamlit as st

from streamlit_app.api.client import DashboardApiError
from streamlit_app.components.charts import (
    recommendation_objective_figure,
    sensitivity_objective_figure,
)
from streamlit_app.components.ui import empty_state, format_value, page_header, panel_heading
from streamlit_app.data.adapters import title_case
from streamlit_app.pages.live_state import api_client, api_unavailable
from streamlit_app.reporting import build_professor_summary


PROFILE_LABELS = {
    "balanced": "Balanced compromise",
    "research_focused": "Research focused",
    "innovation_focused": "Innovation focused",
    "student_focused": "Student focused",
    "robust": "Conservative-service feasible",
}

OBJECTIVE_MEANINGS = {
    "research": "Q1 publication and normalized citation-impact indicators.",
    "innovation": "Patent-application and industry-project indicators.",
    "student_development": "Student research, placement, and higher-study indicators.",
    "societal_contribution": "Open-access publication and outreach indicators.",
}

OBJECTIVE_BY_VARIABLE = {
    "research_seed_funding": "research",
    "conference_support": "research",
    "research_faculty_effort": "research",
    "research_assistant_count": "research",
    "compute_capacity_units": "research",
    "patent_ip_support": "innovation",
    "industry_collaboration_funding": "innovation",
    "student_research_funding": "student_development",
    "student_support_faculty_effort": "student_development",
    "open_access_funding": "societal_contribution",
    "outreach_sdg_funding": "societal_contribution",
    "service_faculty_effort": "societal_contribution",
}

CONSTRAINTS_BY_VARIABLE = {
    "research_seed_funding": ("budget", "dependency__compute_research_support"),
    "conference_support": ("budget",),
    "patent_ip_support": ("budget",),
    "industry_collaboration_funding": ("budget",),
    "student_research_funding": ("budget", "dependency__ra_student_support"),
    "open_access_funding": ("budget",),
    "outreach_sdg_funding": ("budget",),
    "research_faculty_effort": ("faculty_effort_conservation",),
    "student_support_faculty_effort": (
        "faculty_effort_conservation",
        "service_floor__student_support_faculty_effort",
    ),
    "service_faculty_effort": (
        "faculty_effort_conservation",
        "service_floor__service_faculty_effort",
    ),
    "research_assistant_count": ("budget", "dependency__ra_student_support"),
    "compute_capacity_units": ("budget", "dependency__compute_research_support"),
}


def _format_allocation(value: float, unit: str) -> str:
    if unit == "INR":
        return format_value(value, unit)
    if unit == "annual FTE":
        return f"{value:,.2f} FTE"
    if unit == "headcount":
        return f"{value:,.0f} people"
    if unit == "configured compute unit":
        return f"{value:,.0f} units"
    return format_value(value, unit)


def _direction_text(difference: float) -> str:
    if difference > 1e-12:
        return "higher"
    if difference < -1e-12:
        return "lower"
    return "unchanged"


def _constraint_sentence(item: dict[str, Any]) -> str:
    name = title_case(item["name"])
    status = title_case(item["status"])
    margin = float(item["margin"])
    unit = str(item["unit"])
    formatted = _format_allocation(margin, unit) if unit != "KPI-specific modeled value" else f"{margin:,.3g} modeled units"
    return f"{name}: {status}, margin {formatted}."


def build_action_cards(
    recommendation: dict[str, Any], *, limit: int = 5
) -> list[dict[str, Any]]:
    """Select and explain the largest verified actions without evaluating anything."""
    budget_limit = max(float(recommendation.get("budget", {}).get("limit", 0.0)), 1.0)
    objectives = {
        item["name"]: item for item in recommendation.get("objective_deltas", [])
    }
    constraints = {
        item["name"]: item for item in recommendation.get("constraint_evidence", [])
    }
    uncertainty = recommendation.get("uncertainty") or []
    support_warnings = recommendation.get("support_warnings") or []
    changed = []
    for item in recommendation.get("decision_changes", []):
        if item.get("action") == "retain" or math.isclose(
            float(item.get("delta", 0.0)), 0.0, rel_tol=0.0, abs_tol=1e-12
        ):
            continue
        before = float(item["before"])
        after = float(item["after"])
        delta = float(item["delta"])
        budget_effect = item.get("budget_effect")
        if budget_effect is not None:
            impact_score = abs(float(budget_effect)) / budget_limit
        else:
            impact_score = abs(delta) / max(abs(before), abs(after), 1.0)
        percentage = delta / before * 100.0 if not math.isclose(before, 0.0, abs_tol=1e-12) else None
        objective_name = OBJECTIVE_BY_VARIABLE.get(str(item["variable"]))
        objective = objectives.get(objective_name)
        if objective:
            direction = _direction_text(float(objective["difference"]))
            explanation = (
                f"This action is part of the deterministic {recommendation['profile'].replace('_', ' ')} option. "
                f"Its related modeled {title_case(objective_name)} benefit is {direction} than the reference "
                f"by {abs(float(objective['difference'])):.3f} on the stored normalized scale."
            )
            evidence = str(objective.get("evidence") or "Evidence label unavailable")
        else:
            explanation = (
                "This action comes from the selected feasible candidate. No action-specific objective mapping "
                "is available, so no outcome rationale is inferred."
            )
            evidence = "Objective evidence unavailable"
        related_constraints = [
            constraints[name]
            for name in CONSTRAINTS_BY_VARIABLE.get(str(item["variable"]), ())
            if name in constraints
        ]
        negative = min(
            recommendation.get("objective_deltas", []),
            key=lambda row: float(row["difference"]),
            default=None,
        )
        if negative and float(negative["difference"]) < -1e-12:
            tradeoff = (
                f"Option-level trade-off: modeled {title_case(negative['name'])} benefit is lower by "
                f"{abs(float(negative['difference'])):.3f} on the normalized scale."
            )
        else:
            tradeoff = "No modeled objective family is lower than the reference in the stored comparison."
        if not uncertainty:
            warning = "No stored KPI interval evidence is available for this option."
        elif support_warnings:
            warning = str(support_warnings[0]["message"])
        else:
            warning = "Stored KPI intervals describe model uncertainty, not causal policy effects."
        changed.append(
            {
                **item,
                "before_display": _format_allocation(before, str(item["unit"])),
                "after_display": _format_allocation(after, str(item["unit"])),
                "delta_display": _format_allocation(abs(delta), str(item["unit"])),
                "percentage_change": percentage,
                "impact_score": impact_score,
                "objective_name": objective_name,
                "explanation": explanation,
                "evidence": evidence,
                "constraints": [_constraint_sentence(row) for row in related_constraints],
                "tradeoff": tradeoff,
                "uncertainty_warning": warning,
            }
        )
    return sorted(
        changed,
        key=lambda item: (-float(item["impact_score"]), str(item["variable"])),
    )[: max(0, min(int(limit), 5))]


def objective_interpretation_example(rows: list[dict[str, Any]]) -> str | None:
    comparable = [
        item
        for item in rows
        if item.get("reference") is not None
        and item.get("proposed") is not None
        and item.get("difference") is not None
        and item.get("scale") == "normalized modeled benefit [0, 1]"
    ]
    if not comparable:
        return None
    item = max(comparable, key=lambda row: abs(float(row["difference"])))
    direction = "increases" if float(item["difference"]) > 0 else (
        "decreases" if float(item["difference"]) < 0 else "does not change"
    )
    return (
        f"In this option, {title_case(item['name'])} {direction} from "
        f"{float(item['reference']):.3f} to {float(item['proposed']):.3f}, an exact change of "
        f"{float(item['difference']):+.6f} normalized score points. This is a modeled indicator change, "
        "not a measured outcome change or causal effect."
    )


def _render_objective_explainability(recommendation: dict[str, Any]) -> None:
    rows = recommendation.get("objective_deltas") or []
    st.markdown("#### What the four objective scores mean")
    st.write(
        "The chart displays the evaluator's modeled benefit for each objective family. Each underlying KPI is mapped "
        "between its configured minimum and maximum, clipped to 0 through 1, and combined using the stored component weights. "
        "Because the weights sum to one, the displayed family score is bounded from 0 to 1."
    )
    st.caption(
        "Higher displayed scores are preferred. Internally, the optimizer minimizes the negative of each displayed benefit, "
        "so a lower internal objective value means the same thing. Scores are indicators on a common numeric range, but the "
        "four families represent different concepts and are not raw KPI values."
    )
    columns = st.columns(2)
    for index, (name, meaning) in enumerate(OBJECTIVE_MEANINGS.items()):
        columns[index % 2].markdown(f"**{title_case(name)}:** {meaning}")

    if not recommendation.get("nominal_feasible", False):
        st.error("This candidate is infeasible. Its objective scores are not presented as a supported recommendation.")
    comparable = [
        item
        for item in rows
        if item.get("scale") == "normalized modeled benefit [0, 1]"
        and item.get("reference") is not None
        and item.get("proposed") is not None
    ]
    if len(comparable) != len(rows) or not comparable:
        st.warning(
            "Some objective rows lack a comparable reference or the expected bounded scale. Only comparable rows are charted."
        )
    unsupported = [item["name"] for item in comparable if item.get("evidence") in {None, "unsupported"}]
    if unsupported:
        st.warning("Unsupported objective evidence: " + ", ".join(title_case(name) for name in unsupported))

    view = st.radio(
        "Objective chart view",
        options=["Objective Scores", "Score Changes"],
        horizontal=True,
        key=f"objective-view-{recommendation['recommendation_id']}",
    )
    mode = "scores" if view == "Objective Scores" else "changes"
    st.plotly_chart(
        recommendation_objective_figure(rows, mode=mode),
        width="stretch",
        config={"displayModeBar": False},
    )
    if mode == "changes":
        st.caption(
            "Green bars are positive score-point changes, red bars are negative, and gray means unchanged. "
            "A positive modeled change is not proof of real-world improvement."
        )
    else:
        st.caption(
            "Main-chart values are rounded to three decimals. Hover shows component weights and exact comparison context."
        )

    st.markdown("**How to interpret this chart**")
    example = objective_interpretation_example(rows)
    if example:
        st.info(example)
    else:
        st.info("No real computed reference comparison is available for this option.")
    st.caption(
        "These are modeled public-calibrated plus synthetic indicators. They are not directly observed departmental outcomes or empirical evidence of allocation effectiveness."
    )


def _recommendation_for_profile(package: dict[str, Any], profile: str) -> dict[str, Any] | None:
    profile_result = next(
        (
            item
            for item in package["profile_results"]
            if item["profile"] == profile and item["status"] in {"selected", "duplicate"}
        ),
        None,
    )
    if not profile_result:
        return None
    return next(
        item
        for item in package["recommendations"]
        if item["recommendation_id"] == profile_result["recommendation_id"]
    )


def _render_recommended_changes(recommendation: dict[str, Any]) -> None:
    cards = build_action_cards(recommendation)
    all_changes = [
        item
        for item in recommendation.get("decision_changes", [])
        if item.get("action") != "retain"
    ]
    increases = sum(item.get("action") == "increase" for item in all_changes)
    decreases = sum(item.get("action") == "decrease" for item in all_changes)
    retained = len(recommendation.get("decision_changes", [])) - len(all_changes)
    st.markdown("## Recommended Changes")
    if not all_changes:
        st.info(
            "This strategy retains every configured reference allocation. No action is presented as new work."
        )
        return
    st.markdown(
        f"""
        <section class="br-action-summary">
          <div><strong>{len(all_changes)}</strong><span>decisions change</span></div>
          <div><strong>{increases}</strong><span>increase</span></div>
          <div><strong>{decreases}</strong><span>decrease</span></div>
          <div><strong>{retained}</strong><span>stay unchanged</span></div>
        </section>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        f"Showing the {len(cards)} largest meaningful changes from the configured reference. "
        "Monetary actions are ranked by budget effect; non-monetary actions are ranked by relative allocation change."
    )
    for index, card in enumerate(cards):
        direction = str(card["action"])
        icon = {"increase": "↑", "decrease": "↓", "retain": "•"}.get(direction, "•")
        percentage = (
            f" ({float(card['percentage_change']):+.1f}%)"
            if card["percentage_change"] is not None
            else " (percentage not defined from zero)"
        )
        constraints = "".join(
            f"<li>{html.escape(sentence)}</li>" for sentence in card["constraints"]
        ) or "<li>No action-specific named constraint was mapped.</li>"
        st.markdown(
            f"""
                <article class="br-action-card br-action-card--{html.escape(direction)}">
                  <header>
                    <div>
                      <span class="br-action-index">Action {index + 1}</span>
                      <h3>{html.escape(title_case(card['variable']))}</h3>
                    </div>
                    <span class="br-action-direction br-action-direction--{html.escape(direction)}">
                      {icon} {html.escape(title_case(direction))}
                    </span>
                  </header>
                  <div class="br-action-values">
                    <div><span>Reference</span><strong>{html.escape(card['before_display'])}</strong></div>
                    <div class="br-action-arrow">→</div>
                    <div><span>Proposed</span><strong>{html.escape(card['after_display'])}</strong></div>
                  </div>
                  <p class="br-action-delta">{icon} {html.escape(card['delta_display'])}{html.escape(percentage)}</p>
                  <p>{html.escape(card['explanation'])}</p>
                  <div class="br-action-detail"><strong>Constraint check</strong><ul>{constraints}</ul></div>
                  <div class="br-action-detail"><strong>Trade-off</strong><p>{html.escape(card['tradeoff'])}</p></div>
                  <div class="br-action-warning">ⓘ {html.escape(card['uncertainty_warning'])}</div>
                  <footer>Evidence: {html.escape(card['evidence'])}</footer>
                </article>
            """,
            unsafe_allow_html=True,
        )
    if len(all_changes) < 3:
        st.info(
            f"Only {len(all_changes)} meaningful allocation change(s) exist in this candidate, so no extra actions are invented to fill the card layout."
        )


def _display_changes(recommendation: dict[str, Any]) -> None:
    changed_only = st.toggle("Show changed decisions only", value=True)
    rows = recommendation["decision_changes"]
    if changed_only:
        rows = [item for item in rows if item["action"] != "retain"]
    table = pd.DataFrame(rows)
    if table.empty:
        st.info("This candidate retains every configured reference decision.")
        return
    table["Activity"] = table["variable"].map(title_case)
    table["Action"] = table["action"].map(title_case)
    table["Budget effect"] = table.apply(
        lambda row: "Not monetary"
        if pd.isna(row["budget_effect"])
        else format_value(float(row["budget_effect"]), "INR"),
        axis=1,
    )
    st.dataframe(
        table[["Activity", "Action", "before", "after", "delta", "unit", "Budget effect"]].rename(
            columns={"before": "Reference", "after": "Option", "delta": "Change", "unit": "Unit"}
        ),
        hide_index=True,
        width="stretch",
    )
    st.caption("Reference means the configured scenario allocation. It is not labelled as observed or current spending.")


def _render_explanation_wording(client, recommendation: dict[str, Any]) -> None:
    try:
        capability = client.explanation_status()
    except DashboardApiError as exc:
        st.warning(f"Explanation status unavailable: {exc}")
        return
    ai_available = capability["enabled"] and capability["provider_configured"]
    options = ["Rule-based explanation"]
    if ai_available:
        options.append("AI-written wording")
    mode = st.radio(
        "Explanation wording",
        options,
        horizontal=True,
        key=f"explanation-mode-{recommendation['recommendation_id']}",
    )
    if mode == "Rule-based explanation":
        st.markdown("**Rule-based explanation**")
        st.write(recommendation["explanation"]["why"][0])
        st.caption("Generated deterministically from the selection rule. No external provider call is made.")
        if not ai_available:
            st.info("AI-written wording is unavailable or disabled. The complete Advisor remains functional in rule-based mode.")
        return

    st.info(
        capability["provider_disclosure"]
        + " The provider cannot change the selected candidate, amounts, actions, charts, or feasibility."
    )
    cache_key = f"br_explanation_{recommendation['recommendation_id']}"
    if st.button(
        "Explain in plain language",
        type="secondary",
        key=f"explain-{recommendation['recommendation_id']}",
        width="stretch",
    ):
        try:
            with st.spinner("Requesting grounded wording from Groq"):
                st.session_state[cache_key] = client.explain(
                    recommendation["source_run_id"], recommendation["recommendation_id"]
                )
        except DashboardApiError as exc:
            st.error(f"{exc.code}: {exc}")
    result = st.session_state.get(cache_key)
    if not result:
        st.caption("No provider request has been made for this recommendation in this browser session.")
        return
    output = result["output"]
    if result["mode"] == "ai_written":
        st.success("AI-written wording of verified model output. This is not independent evidence or expert approval.")
    else:
        st.warning(
            "The provider output was unavailable or rejected. Rule-based wording is shown instead. "
            f"Fallback: {title_case(result['audit']['fallback_cause'])}."
        )
    st.markdown(f"#### {output['headline']}")
    st.write(output["plain_language_summary"])
    st.markdown("**Why this option**")
    for item in output["why_this_option"]:
        st.write(f"- {item}")
    st.markdown("**Trade-offs**")
    for item in output["tradeoffs"]:
        st.write(f"- {item}")
    st.markdown("**Assumptions and caveats**")
    for item in output["assumptions_and_caveats"]:
        st.write(f"- {item}")
    with st.expander("Explanation audit"):
        st.json(
            {
                "mode": result["mode"],
                "cache_hit": result["cache_hit"],
                "fact_packet_hash": result["fact_packet_hash"],
                "audit": result["audit"],
                "selection_unchanged": result["selection_unchanged"],
                "structured_facts_remain_authoritative": result[
                    "structured_facts_remain_authoritative"
                ],
            }
        )


def _render_recommendation(recommendation: dict[str, Any]) -> None:
    duplicate = recommendation.get("duplicate_of_profile")
    if duplicate:
        st.info(
            f"This profile selects the same candidate as {PROFILE_LABELS[duplicate]}. "
            "The interface does not present it as a distinct strategy."
        )
    _render_recommended_changes(recommendation)

    st.markdown("### Option at a glance")
    top = st.columns(4)
    budget = recommendation["budget"]
    proposed_faculty = recommendation["faculty"]["proposed"]
    top[0].metric("Proposed cost", format_value(budget["proposed"], "INR"))
    top[1].metric("Budget headroom", format_value(budget["headroom"], "INR"))
    top[2].metric(
        "Faculty headroom",
        f"{proposed_faculty['headroom']:.2f} FTE",
        help="Available annual FTE minus teaching floor and controllable faculty allocations",
    )
    top[3].metric(
        "Feasibility",
        "Nominal passed" if recommendation["nominal_feasible"] else "Nominal failed",
        help="Conservative-service feasibility is reported separately in technical evidence.",
    )

    with st.expander("Why was this strategy selected?", expanded=True):
        st.write(
            "The reporting layer applied a deterministic preference rule to the independently revalidated feasible archive. "
            "It did not ask the language model to choose a strategy."
        )
        st.markdown(f"**Selection rule:** {recommendation['selection_rule']}")
        weights = recommendation.get("profile_weights", {})
        if weights:
            st.caption(
                "Profile weights: "
                + ", ".join(
                    f"{title_case(name)} {float(value):.0%}"
                    for name, value in weights.items()
                )
            )
        st.caption(
            f"Weighted utility within this run's feasible archive: {recommendation['weighted_utility']:.4f}. "
            "Candidate IDs provide deterministic tie-breaking."
        )
        if duplicate:
            st.info(
                f"The {PROFILE_LABELS[recommendation['profile']]} rule and {PROFILE_LABELS[duplicate]} rule select the same candidate."
            )
        _render_objective_explainability(recommendation)

    with st.expander("Modeled trade-offs and uncertainty"):
        for sentence in recommendation["explanation"]["tradeoffs"]:
            st.write(sentence)
        if not recommendation.get("objective_deltas"):
            st.warning("No objective comparison evidence is available for this option.")
        objective_rows = pd.DataFrame(recommendation["objective_deltas"])
        if not objective_rows.empty:
            objective_rows["Objective"] = objective_rows["name"].map(title_case)
            st.dataframe(
                objective_rows[["Objective", "reference", "proposed", "difference", "scale", "evidence"]].rename(
                    columns={"reference": "Reference", "proposed": "Option", "difference": "Change", "scale": "Scale", "evidence": "Evidence"}
                ),
                hide_index=True,
                width="stretch",
            )
            component_rows = []
            for objective in recommendation["objective_deltas"]:
                for component in objective.get("components", []):
                    component_rows.append(
                        {
                            "Objective": title_case(objective["name"]),
                            "KPI component": title_case(component["kpi"]),
                            "Weight": component["weight"],
                            "Normalization minimum": component["normalization_minimum"],
                            "Normalization maximum": component["normalization_maximum"],
                            "Reference raw KPI": component["reference_raw_value"],
                            "Selected raw KPI": component["proposed_raw_value"],
                            "Reference normalized": component["reference_normalized_value"],
                            "Selected normalized": component["proposed_normalized_value"],
                            "Evidence": component["evidence"],
                        }
                    )
            if component_rows:
                st.markdown("**Exact objective component details**")
                st.dataframe(pd.DataFrame(component_rows), hide_index=True, width="stretch")
            else:
                st.warning("Underlying KPI component metadata is unavailable.")
        for warning in recommendation["support_warnings"]:
            if warning["code"] == "out_of_model_support":
                st.warning(warning["message"] + " " + ", ".join(warning["features"]))
            else:
                st.info(warning["message"])
        st.caption("KPI intervals are stored model intervals. They do not quantify causal policy effects.")
        intervals = pd.DataFrame(recommendation["uncertainty"])
        if intervals.empty:
            st.warning("No stored KPI interval evidence is available for this option.")
        else:
            intervals["KPI"] = intervals["kpi"].map(title_case)
            st.dataframe(
                intervals[["KPI", "prediction", "lower", "upper", "validation_type"]].rename(
                    columns={"prediction": "Prediction", "lower": "Lower", "upper": "Upper", "validation_type": "Validation"}
                ),
                hide_index=True,
                width="stretch",
            )

    with st.expander("Detailed allocation table"):
        for sentence in recommendation["explanation"]["what_changes"]:
            st.write(sentence)
        _display_changes(recommendation)

    with st.expander("Technical constraints and identifiers"):
        st.markdown("**Named constraint margins**")
        constraints = pd.DataFrame(recommendation["constraint_evidence"])
        if constraints.empty:
            st.warning("No named constraint evidence is available.")
        else:
            constraints["Constraint"] = constraints["name"].map(title_case)
            constraints["Status"] = constraints["status"].map(title_case)
            st.dataframe(
                constraints[["Constraint", "Status", "margin", "unit", "evaluator_residual", "normalized_residual"]].rename(
                    columns={"margin": "Margin", "unit": "Unit", "evaluator_residual": "Evaluator residual", "normalized_residual": "Normalized residual"}
                ),
                hide_index=True,
                width="stretch",
            )
        st.caption("A zero evaluator residual means no violation. Binding status is shown only where an exact signed margin is available.")
        nominal, robust = st.columns(2)
        nominal.metric("Nominal feasibility", "Passed" if recommendation["nominal_feasible"] else "Failed")
        robust.metric("Conservative-service feasibility", "Passed" if recommendation["robust_feasible"] else "Failed")
        st.caption(recommendation["robustness_definition"])
        st.code(recommendation["recommendation_id"])

    st.download_button(
        "Download recommendation facts",
        json.dumps(recommendation, indent=2, sort_keys=True),
        file_name=f"recommendation-{recommendation['recommendation_id']}.json",
        mime="application/json",
        width="stretch",
    )


def _render_sensitivity(client, status: dict[str, Any], recommendation: dict[str, Any]) -> None:
    st.divider()
    panel_heading(
        "Controlled factor diagnostic",
        "Test one factor",
        "Runs the same algorithm, seed, and evaluation budget after changing exactly one supported scenario factor.",
    )
    factor = st.selectbox(
        "Factor",
        options=["budget_limit", "faculty_total"],
        format_func=lambda value: "Available budget" if value == "budget_limit" else "Faculty capacity",
        key="advisor_sensitivity_factor",
    )
    before = recommendation["budget"]["limit"] if factor == "budget_limit" else recommendation["faculty"]["proposed"]["available"]
    display_divisor = 10_000_000 if factor == "budget_limit" else 1
    label = "Test budget (₹ crore)" if factor == "budget_limit" else "Test faculty capacity (annual FTE)"
    default_value = before / display_divisor + (0.1 if factor == "budget_limit" else 1.0)
    with st.form("advisor_sensitivity_form"):
        new_display_value = st.number_input(
            label,
            min_value=0.1,
            value=float(default_value),
            step=0.1 if factor == "budget_limit" else 0.25,
        )
        run_sensitivity = st.form_submit_button("Run controlled sensitivity", type="primary", width="stretch")
    if run_sensitivity:
        new_value = float(new_display_value) * display_divisor
        try:
            context = client.create_sensitivity(status["run_id"], factor, new_value, recommendation["profile"])
            changed = context["run_status"]
            progress = st.status("Sensitivity reoptimization started", expanded=True)
            if changed["status"] in {"queued", "running"}:
                changed = client.wait_for_run(
                    changed["run_id"],
                    on_status=lambda item: progress.update(label=f"Sensitivity phase: {title_case(item['phase'])}", state="running"),
                )
            result = client.sensitivity_result(status["run_id"], changed["run_id"])
            st.session_state["br_sensitivity_result"] = result
            progress.update(
                label="Sensitivity case complete" if result["status"] == "complete" else f"Sensitivity {result['status']}",
                state="complete" if result["status"] == "complete" else "error",
                expanded=False,
            )
        except DashboardApiError as exc:
            st.error(f"{exc.code}: {exc}")

    result = st.session_state.get("br_sensitivity_result")
    if not result or result.get("baseline_run_id") != status["run_id"]:
        st.info("No controlled factor case has been run for this recommendation yet.")
        return
    if result["status"] != "complete":
        st.warning(f"Sensitivity run status: {result['status']}")
        return

    st.success(
        f"Tested {title_case(result['factor'])}: {result['before']:,.4g} to {result['after']:,.4g} {result['unit']} "
        f"using the same {result['algorithm'].upper()}, seed {result['seed']}, and {result['evaluation_budget']} evaluations."
    )
    held_fixed, reoptimized = st.columns(2)
    held_fixed.metric("Held fixed, no repair", "Feasible" if result["held_fixed"]["feasible"] else "Infeasible", help="The original selected allocation evaluated unchanged under the new factor.")
    reoptimized.metric("Reoptimized scenario", "Feasible option found" if result.get("reoptimized") else "No supported option", help="A new search using the same algorithm, seed, and evaluation budget.")
    if result.get("reoptimized"):
        st.plotly_chart(sensitivity_objective_figure(result), width="stretch", config={"displayModeBar": False})
    else:
        st.warning("The changed scenario produced no supported feasible recommendation for this profile.")
    st.caption(result["interpretation"])
    with st.expander("Sensitivity provenance"):
        st.json(result)


def render() -> None:
    page_header(
        "Grounded decision options",
        "Department Improvement Advisor",
        "Trace a deterministic strategy from a revalidated candidate through exact actions, modeled trade-offs, constraints, and uncertainty.",
    )
    status = st.session_state.get("br_run_status")
    if not status or status.get("status") != "complete":
        empty_state(
            "No supported recommendation",
            "Complete a Resource Planner run first. The Advisor never generates advice without a completed run and a revalidated feasible candidate.",
        )
        return
    try:
        client = api_client()
        package = client.recommendations(status["run_id"])
    except DashboardApiError as exc:
        api_unavailable(exc)
        return

    if package["status"] != "supported":
        empty_state("No supported recommendation", package.get("reason") or "No eligible candidate is available.")
        return

    st.warning("Decision-support option from a public-calibrated plus synthetic model. It is not a policy directive or causal impact claim.")
    profile_rows = [item for item in package["profile_results"] if item["status"] != "unsupported"]
    available_profiles = [item["profile"] for item in profile_rows]
    profile = st.selectbox("Decision profile", available_profiles, format_func=PROFILE_LABELS.get, key="advisor_profile")
    recommendation = _recommendation_for_profile(package, profile)
    if recommendation is None:
        empty_state("No supported recommendation", "The selected profile has no eligible conservative-service feasible candidate.")
        return

    st.session_state["br_selected_candidate_id"] = recommendation["candidate_id"]
    st.caption(
        f"Run `{recommendation['source_run_id']}` · candidate `{recommendation['candidate_id']}` · recommendation `{recommendation['recommendation_id']}`"
    )
    _render_recommendation(recommendation)
    with st.expander("Explain in plain language (optional)"):
        _render_explanation_wording(client, recommendation)
    _render_sensitivity(client, status, recommendation)
    summary = build_professor_summary(
        run_status=status,
        recommendation=recommendation,
        sensitivity=st.session_state.get("br_sensitivity_result"),
    )
    st.download_button(
        "Download professor-facing decision summary",
        summary,
        file_name=f"decision-summary-{recommendation['recommendation_id']}.md",
        mime="text/markdown",
        width="stretch",
    )
