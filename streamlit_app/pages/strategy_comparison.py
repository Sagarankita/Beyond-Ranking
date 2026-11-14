from __future__ import annotations

import pandas as pd
import streamlit as st

from streamlit_app.api.client import DashboardApiError
from streamlit_app.components.charts import live_allocation_figure
from streamlit_app.components.live import allocation_rows, candidate_label, render_evidence_strip
from streamlit_app.components.ui import empty_state, format_value, page_header, panel_heading
from streamlit_app.data.adapters import title_case
from streamlit_app.pages.live_state import api_client, api_unavailable
from streamlit_app.pages.advisor import PROFILE_LABELS


def render() -> None:
    page_header(
        "Comparable feasible alternatives",
        "Strategy Comparison",
        "Compare two revalidated candidates from the same scenario and run. Values are never normalized across incompatible units.",
    )
    candidates = st.session_state.get("br_candidates", [])
    status = st.session_state.get("br_run_status")
    validation = st.session_state.get("br_validation")
    if not candidates or not status or not validation:
        empty_state("No comparable live strategies", "Run Resource Planner first. This page does not manufacture strategy labels or values.")
        return
    if len(candidates) < 2:
        empty_state("Only one unique strategy is available", "The current archive contains one feasible candidate, so a pairwise comparison would be misleading.")
        return

    render_evidence_strip(status["scenario_hash"])
    try:
        client = api_client()
        recommendation_package = client.recommendations(status["run_id"])
    except DashboardApiError as exc:
        api_unavailable(exc)
        return
    profile_rows = pd.DataFrame(recommendation_package.get("profile_results", []))
    if not profile_rows.empty:
        profile_rows["Profile"] = profile_rows["profile"].map(PROFILE_LABELS)
        profile_rows["Selection"] = profile_rows["status"].map(title_case)
        profile_rows["Candidate"] = profile_rows.get("candidate_id", pd.Series(dtype=str)).fillna("Not supported")
        profile_rows["Same as"] = profile_rows.get("duplicate_of_profile", pd.Series(dtype=str)).fillna("").map(
            lambda value: PROFILE_LABELS.get(value, value)
        )
        with st.expander("Deterministic profile selections", expanded=True):
            st.dataframe(
                profile_rows[["Profile", "Selection", "Candidate", "Same as"]],
                hide_index=True,
                width="stretch",
            )
            st.caption("Several profiles may select the same actual archive candidate. Duplicate selections are disclosed rather than relabelled as distinct strategies.")
    labels = {item["candidate_id"]: candidate_label(item, index) for index, item in enumerate(candidates)}
    first_column, second_column = st.columns(2)
    first = first_column.selectbox("Reference strategy", list(labels), format_func=labels.get, index=0)
    second = second_column.selectbox("Alternative strategy", list(labels), format_func=labels.get, index=1)
    if first == second:
        st.info("Choose two different strategies to calculate deltas.")
        return

    try:
        comparison = client.comparison(status["run_id"], first, second)
    except DashboardApiError as exc:
        api_unavailable(exc)
        return
    first_record = next(item for item in candidates if item["candidate_id"] == first)
    second_record = next(item for item in candidates if item["candidate_id"] == second)

    metrics = st.columns(3)
    metrics[0].metric("Cost change", format_value(comparison["cost_delta"], "INR"))
    metrics[1].metric("Headroom change", format_value(comparison["budget_remaining_delta"], "INR"))
    metrics[2].metric("Scenario match", "Verified", help=comparison["scenario_hash"])

    feasibility_columns = st.columns(2)
    for column, label, record in (
        (feasibility_columns[0], "Reference strategy", first_record),
        (feasibility_columns[1], "Alternative strategy", second_record),
    ):
        with column:
            failed = sum(not item["satisfied"] for item in record["constraints"].values())
            st.markdown(f"**{label}**")
            st.caption(
                f"Nominal feasibility: {'passed' if record['feasible'] else 'failed'} · "
                f"Conservative-service feasibility: {'passed' if record['robust_feasible'] else 'failed'} · "
                f"Named violations: {failed}"
            )

    panel_heading("Decision deltas", "Alternative minus reference", "Exact changes from the backend comparison endpoint.")
    decision_table = pd.DataFrame(comparison["decision_deltas"])
    decision_table["Decision"] = decision_table["name"].map(title_case)
    st.dataframe(
        decision_table[["Decision", "first", "second", "delta", "unit"]].rename(
            columns={"first": "Reference", "second": "Alternative", "delta": "Change", "unit": "Unit"}
        ),
        hide_index=True,
        width="stretch",
    )

    rows = allocation_rows(validation, second_record)
    rows["reference"] = rows["variable"].map(first_record["decisions"])
    rows["delta"] = rows["proposed"] - rows["reference"]
    for title, unit in (("Money", "INR"), ("Faculty effort", "annual FTE"), ("Headcount", "headcount"), ("Compute capacity", "configured compute unit")):
        with st.expander(title, expanded=unit in {"INR", "annual FTE"}):
            st.plotly_chart(live_allocation_figure(rows, unit), width="stretch", config={"displayModeBar": False})

    panel_heading("Objective trade-offs", "Modeled benefit changes", "All values use the defined normalized benefit scale [0, 1]. Positive means the alternative is higher on that modeled objective.")
    objective_table = pd.DataFrame(comparison["objective_deltas"])
    objective_table["Objective"] = objective_table["name"].map(title_case)
    st.dataframe(
        objective_table[["Objective", "first_benefit", "second_benefit", "delta", "scale"]].rename(
            columns={"first_benefit": "Reference", "second_benefit": "Alternative", "delta": "Change", "scale": "Scale"}
        ),
        hide_index=True,
        width="stretch",
    )
