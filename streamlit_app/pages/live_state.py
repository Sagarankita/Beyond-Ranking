from __future__ import annotations

from typing import Any

import streamlit as st

from streamlit_app.api.client import DashboardApiClient, DashboardApiError


def api_client() -> DashboardApiClient:
    return DashboardApiClient(st.session_state.get("br_api_url"))


def api_unavailable(exc: DashboardApiError) -> None:
    st.error(str(exc), icon=":material/cloud_off:")
    st.code("make frontend-api PYTHON=.venv/bin/python", language="bash")
    st.caption("Start the API in a second terminal, then reload this page. No demonstration values are substituted while it is unavailable.")


def selected_candidate() -> dict[str, Any] | None:
    candidates = st.session_state.get("br_candidates", [])
    selected_id = st.session_state.get("br_selected_candidate_id")
    return next((item for item in candidates if item["candidate_id"] == selected_id), None)
