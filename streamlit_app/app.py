from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from streamlit_app.components.ui import load_css  # noqa: E402
from streamlit_app.pages import overview, placeholders  # noqa: E402


st.set_page_config(
    page_title="Beyond Ranking · Decision Studio",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
load_css()

st.sidebar.markdown("## Beyond Ranking")
st.sidebar.caption("Decision Studio")
st.sidebar.success("Read-only artifact interface", icon="🔒")


def scenario_page() -> None:
    placeholders.render("scenario")


def algorithm_page() -> None:
    placeholders.render("algorithm")


def pareto_page() -> None:
    placeholders.render("pareto")


def robustness_page() -> None:
    placeholders.render("robustness")


def target_cost_page() -> None:
    placeholders.render("target")


def evidence_audit_page() -> None:
    placeholders.render("evidence")


navigation = st.navigation(
    {
        "Workspace": [
            st.Page(overview.render, title="Overview", icon=":material/dashboard:", default=True),
            st.Page(scenario_page, title="Scenario Studio", icon=":material/tune:"),
            st.Page(algorithm_page, title="Algorithm Lab", icon=":material/account_tree:"),
            st.Page(pareto_page, title="Pareto Explorer", icon=":material/scatter_plot:"),
            st.Page(robustness_page, title="Robustness Lab", icon=":material/shield:"),
            st.Page(target_cost_page, title="Target-Cost Explorer", icon=":material/target:"),
            st.Page(evidence_audit_page, title="Evidence & Audit", icon=":material/fact_check:"),
        ]
    },
    position="sidebar",
)

st.sidebar.divider()
st.sidebar.markdown("**Legacy artifact viewer**")
st.sidebar.caption("Run `make legacy-dashboard`, then open http://127.0.0.1:4173.")

navigation.run()
