from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from streamlit_app.components.charts import (
    live_allocation_figure,
    live_kpi_interval_figure,
    objective_score_figure,
)
from streamlit_app.components.ui import empty_state, format_value, panel_heading
from streamlit_app.data.adapters import title_case


EFFORT_VARIABLES = (
    "research_faculty_effort",
    "student_support_faculty_effort",
    "service_faculty_effort",
)


def allocation_rows(defaults: dict[str, Any], candidate: dict[str, Any] | None) -> pd.DataFrame:
    config = defaults["config"]
    units = {item["name"]: item["unit"] for item in config["decision_variables"]}
    reference = config["reference_allocation"]
    proposed = candidate["decisions"] if candidate else reference
    return pd.DataFrame(
        [
            {
                "variable": name,
                "unit": units[name],
                "reference": float(reference[name]),
                "proposed": float(proposed[name]),
                "delta": float(proposed[name]) - float(reference[name]),
            }
            for name in reference
        ]
    )


def candidate_label(candidate: dict[str, Any], index: int) -> str:
    objective_values = candidate["objectives"]
    strongest = max(objective_values, key=lambda name: objective_values[name]["benefit"])
    return f"Strategy {index + 1} · {title_case(strongest)} emphasis · {candidate['candidate_id'][:8]}"


def render_evidence_strip(scenario_hash: str | None = None) -> None:
    identifier = f" · scenario {scenario_hash[:10]}" if scenario_hash else ""
    st.markdown(
        """
        <section class="br-evidence br-evidence--mixed">
          <strong>Public plus synthetic scenario</strong>
          <p>Modeled allocation fixture. Results are not causal estimates or observed VJTI spending.</p>
          <code>%s</code>
        </section>
        """ % identifier,
        unsafe_allow_html=True,
    )


def render_reference_and_candidate(
    validation: dict[str, Any],
    candidate: dict[str, Any] | None,
    *,
    show_kpis: bool = True,
) -> None:
    config = validation["config"]
    rows = allocation_rows(validation, candidate)
    budget_limit = float(config["budget_limit"])
    reference_assessment = validation["reference_assessment"]
    total_cost = float(candidate["total_cost"] if candidate else reference_assessment["total_cost"])
    remaining = float(candidate["budget_remaining"] if candidate else reference_assessment["budget_remaining"])
    decisions = candidate["decisions"] if candidate else config["reference_allocation"]
    teaching_floor = float(config["service_commitments"]["minimum_teaching_fte"])
    faculty_used = teaching_floor + sum(float(decisions[name]) for name in EFFORT_VARIABLES)
    faculty_total = float(config["fixed_context"]["faculty_total"])

    metric_columns = st.columns(4)
    metric_columns[0].metric("Available budget", format_value(budget_limit, "INR"), help="Validated scenario limit")
    metric_columns[1].metric("Allocated", format_value(total_cost, "INR"), help="Evaluator total cost")
    metric_columns[2].metric("Budget headroom", format_value(remaining, "INR"), help="Available budget minus evaluator total cost")
    metric_columns[3].metric(
        "Faculty capacity",
        f"{faculty_used:.2f} / {faculty_total:.2f} FTE",
        help="Teaching floor plus the three controllable faculty-effort decisions",
    )
    feasible = bool(candidate["feasible"]) if candidate else bool(reference_assessment["feasible_without_repair"])
    status_label = "Selected strategy" if candidate else "Reference scenario"
    if feasible:
        st.success(f"{status_label} is feasible · {len(config['decision_variables'])} active decision variables")
    else:
        st.warning(f"{status_label} is not feasible without repair · {len(config['decision_variables'])} active decision variables")

    resource_left, resource_right = st.columns(2, gap="large")
    with resource_left:
        st.caption(f"Budget utilization · {total_cost / budget_limit * 100:.1f}%")
        st.progress(min(total_cost / budget_limit, 1.0))
    with resource_right:
        st.caption(f"Faculty utilization · {faculty_used / faculty_total * 100:.1f}%")
        st.progress(min(faculty_used / faculty_total, 1.0))

    monetary, effort, counts = st.tabs(["Monetary allocation", "Faculty effort", "Counts and capacity"])
    unit_panels = ((monetary, "INR"), (effort, "annual FTE"))
    for panel, unit in unit_panels:
        with panel:
            st.plotly_chart(live_allocation_figure(rows, unit), width="stretch", config={"displayModeBar": False})
    with counts:
        for unit in ("headcount", "configured compute unit"):
            st.plotly_chart(live_allocation_figure(rows, unit), width="stretch", config={"displayModeBar": False})
    st.caption("Every chart uses exact values on a compatible-unit axis. Reference means the configured scenario allocation, not observed current spending.")

    if candidate is None:
        empty_state(
            "No optimized strategy selected",
            "The reference scenario is shown above. Open Resource Planner to validate inputs and run an approved optimizer.",
        )
        return

    objective_column, constraint_column = st.columns([1.15, 0.85], gap="large")
    with objective_column:
        panel_heading(
            "Modeled trade-offs",
            "Objective-family scores",
            "All four axes use the evaluator's explicitly defined normalized benefit scale from 0 to 1.",
        )
        st.plotly_chart(objective_score_figure(candidate), width="stretch", config={"displayModeBar": False})
    with constraint_column:
        panel_heading(
            "Independent revalidation",
            "Feasibility summary",
            "Candidate values were rechecked by the canonical evaluator after optimization.",
        )
        failed = [name for name, value in candidate["constraints"].items() if not value["satisfied"]]
        st.metric("Named constraints", f"{len(candidate['constraints']) - len(failed)} / {len(candidate['constraints'])} passed")
        st.metric("Robust feasibility", "Passed" if candidate["robust_feasible"] else "Not established")
        st.metric("Normalized violation", f"{candidate['normalized_violation']:.3g}")
        if failed:
            st.error("Failed: " + ", ".join(title_case(name) for name in failed))
        else:
            st.success("All named feasibility checks passed.")

    if show_kpis:
        panel_heading(
            "Stored model uncertainty",
            "KPI predictions and intervals",
            "KPI units differ, so the axis is not a cross-KPI comparison. Hover for exact stored bounds.",
        )
        st.plotly_chart(live_kpi_interval_figure(candidate), width="stretch", config={"displayModeBar": False})
        st.caption("Intervals come from the persisted model output. They do not establish causal intervention effects.")


def manifest_download(run_status: dict[str, Any], candidate: dict[str, Any]) -> None:
    payload = {
        "run": run_status,
        "selected_candidate": candidate,
        "notice": "Modeled public-calibrated plus synthetic scenario, not a causal effect estimate.",
    }
    st.download_button(
        "Download selected strategy record",
        json.dumps(payload, indent=2, sort_keys=True),
        file_name=f"strategy-{candidate['candidate_id']}.json",
        mime="application/json",
        width="stretch",
    )
