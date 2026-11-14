from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from streamlit_app.components.ui import load_css  # noqa: E402
from streamlit_app.pages import (  # noqa: E402
    advisor,
    department_overview,
    evidence_assumptions,
    experiment_lab,
    resource_planner,
    strategy_comparison,
)


st.set_page_config(
    page_title="Beyond Ranking · Decision Studio",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
load_css()

st.sidebar.markdown("## Beyond Ranking")
st.sidebar.caption("Department Decision Studio")
st.sidebar.info("Public plus synthetic model fixture")

overview_page = st.Page(
    department_overview.render,
    title="Department Overview",
    icon=":material/dashboard:",
    default=True,
    url_path="overview",
)
planner_page = st.Page(
    resource_planner.render,
    title="Resource Planner",
    icon=":material/tune:",
    url_path="planner",
)
st.session_state["_planner_page"] = planner_page


navigation = st.navigation(
    {
        "Plan": [overview_page, planner_page],
        "Understand": [
            st.Page(advisor.render, title="Improvement Advisor", icon=":material/lightbulb:", url_path="advisor"),
            st.Page(strategy_comparison.render, title="Strategy Comparison", icon=":material/compare_arrows:", url_path="compare"),
        ],
        "Research & evidence": [
            st.Page(experiment_lab.render, title="Experiment Lab", icon=":material/science:", url_path="experiments"),
            st.Page(evidence_assumptions.render, title="Evidence & Assumptions", icon=":material/fact_check:", url_path="evidence"),
        ],
    },
    position="sidebar",
)

st.sidebar.divider()
st.sidebar.caption("Live optimizer service")
st.sidebar.code("127.0.0.1:8000", language=None)
st.sidebar.caption("All live candidates are independently revalidated by the canonical backend evaluator.")

navigation.run()
