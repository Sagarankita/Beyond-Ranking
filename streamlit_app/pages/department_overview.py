from __future__ import annotations

import streamlit as st

from streamlit_app.api.client import DashboardApiError
from streamlit_app.components.live import render_evidence_strip, render_reference_and_candidate
from streamlit_app.components.ui import page_header, panel_heading
from streamlit_app.pages.live_state import api_client, api_unavailable, selected_candidate


def render() -> None:
    page_header(
        "Department decision support",
        "Department Overview",
        "Review the validated reference scenario and the strategy selected from your latest live optimization run.",
    )
    try:
        client = api_client()
        defaults = client.defaults()
        validation = client.validate(defaults["defaults"])
    except DashboardApiError as exc:
        api_unavailable(exc)
        return

    if not validation.get("valid"):
        st.error("The backend default scenario did not pass validation.")
        st.json(validation.get("field_errors", {}))
        return

    candidate = selected_candidate()
    status = st.session_state.get("br_run_status")
    render_evidence_strip(validation.get("scenario_hash"))

    top_left, top_right = st.columns([3, 1])
    with top_left:
        if candidate:
            st.success(f"Selected revalidated strategy · {candidate['candidate_id']}")
        else:
            st.info("Showing the configured reference scenario. Run Resource Planner to create and select an alternative.")
    with top_right:
        if st.button("Plan resource changes", type="primary", width="stretch"):
            st.switch_page(st.session_state["_planner_page"])

    if status:
        with st.expander("Latest run identity"):
            st.code(status["run_id"])
            st.caption(
                f"{status['algorithm'].upper()} · seed {status['seed']} · "
                f"{status['evaluation_budget']} candidate evaluations · {status['status']}"
            )

    render_reference_and_candidate(validation, candidate)

    st.divider()
    panel_heading(
        "Interpretation boundary",
        "What this view means",
        "Reference values come from the versioned configuration. Proposed values come from a feasible archive candidate independently rechecked by VJTIPublicAllocationProblem.",
    )
    st.caption("This screen does not describe observed current accounts and does not claim that allocation changes cause the modeled KPI changes.")
