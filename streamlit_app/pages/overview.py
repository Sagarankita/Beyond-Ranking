from __future__ import annotations

import streamlit as st

from streamlit_app.components.charts import allocation_figure, kpi_interval_figure
from streamlit_app.components.ui import (
    empty_state,
    evidence_banner,
    page_header,
    panel_heading,
    render_constraints,
    render_evidence_notes,
    render_metrics,
    render_provenance,
    render_resources,
)
from streamlit_app.data.adapters import adapt_overview, title_case
from streamlit_app.data.catalog import CATALOG_PATH
from streamlit_app.data.loaders import load_catalog, load_snapshot
from streamlit_app.data.types import OverviewSnapshot


@st.cache_data(show_spinner=False)
def _load_overview(snapshot_id: str, catalog_mtime_ns: int) -> OverviewSnapshot:
    del catalog_mtime_ns
    catalog = load_catalog()
    return adapt_overview(load_snapshot(snapshot_id, catalog))


def render() -> None:
    page_header(
        "Versioned saved outputs",
        "Evidence-aware allocation overview",
        "Compare a persisted reference allocation with saved recommendations. This app validates and renders artifacts; it cannot execute an optimizer.",
    )
    try:
        catalog = load_catalog()
        snapshot_labels = {snapshot.label: snapshot.id for snapshot in catalog.snapshots}
        selected_label = st.selectbox("Snapshot", options=list(snapshot_labels), key="overview-snapshot")
        snapshot_id = snapshot_labels[selected_label]
        with st.spinner("Validating saved artifacts…"):
            overview = _load_overview(snapshot_id, CATALOG_PATH.stat().st_mtime_ns)
    except Exception as exc:
        st.error(f"Artifact validation failed: {exc}", icon="🚨")
        return

    strategy = overview.default_strategy
    if overview.strategies:
        strategy = st.selectbox(
            "Saved strategy",
            options=overview.strategies,
            index=overview.strategies.index(overview.default_strategy) if overview.default_strategy in overview.strategies else 0,
            format_func=title_case,
            key=f"strategy-{overview.id}",
        )

    evidence_banner(overview)
    render_metrics(overview.base_metrics)
    st.divider()

    allocations = overview.allocations[overview.allocations["strategy"] == strategy] if strategy and not overview.allocations.empty else overview.allocations
    kpis = overview.kpis[overview.kpis["strategy"] == strategy] if strategy and not overview.kpis.empty else overview.kpis
    resources = overview.resources[overview.resources["strategy"] == strategy] if strategy and not overview.resources.empty else overview.resources
    constraints = overview.constraints[overview.constraints["strategy"] == strategy] if strategy and not overview.constraints.empty else overview.constraints

    allocation_column, resource_column = st.columns([1.65, 0.85], gap="large")
    with allocation_column:
        panel_heading(
            "Decision comparison",
            "Current vs recommended allocation",
            "Exact values come from the persisted reporting artifact; bars are normalized only for readable mixed-unit comparison.",
            "No allocation is recomputed in Streamlit. Select a saved strategy to change the artifact rows shown.",
        )
        if allocations.empty:
            empty_state("No empirical allocation recommendation", "The empirical evidence snapshot contains descriptive public evidence, not an intervention-response optimizer run.")
        else:
            st.plotly_chart(allocation_figure(allocations, title_case(strategy or "recommended")), width="stretch", config={"displayModeBar": False})
            st.caption("Bars are normalized within each decision; monetary and effort units are never compared on one numeric axis. Hover for exact values.")
    with resource_column:
        panel_heading(
            "Resource envelope",
            "Utilization",
            "Budget and faculty indicators use values and limits recorded in the same saved resource artifact.",
            "An absolute value is shown without a utilization bar when the artifact records no compatible capacity.",
        )
        if resources.empty:
            empty_state("No modeled utilization", "Resource utilization is unavailable without a saved optimizer allocation.")
        else:
            render_resources(resources)

    st.divider()
    kpi_column, constraint_column = st.columns([1.35, 0.85], gap="large")
    with kpi_column:
        panel_heading(
            "Model output",
            "KPI prediction intervals",
            "Current and recommended predictions use their persisted uncertainty intervals and evidence labels.",
            "These are model prediction intervals, not empirical confidence intervals for a causal intervention effect.",
        )
        if kpis.empty:
            empty_state("No empirical response intervals", "Observed public outcomes remain descriptive; synthetic model intervals are not imported into this evidence lane.")
        else:
            st.plotly_chart(kpi_interval_figure(kpis), width="stretch", config={"displayModeBar": False})
            st.caption("Each KPI is normalized only for layout. Hover for exact saved predictions and bounds.")
    with constraint_column:
        panel_heading(
            "Feasibility",
            "Constraint status",
            "Named residuals come directly from the saved evaluator output.",
            "The UI applies only the documented reporting threshold; it does not repair a candidate.",
        )
        if constraints.empty:
            empty_state("No allocation constraints", "There is no empirical candidate to test in this snapshot.")
        else:
            render_constraints(constraints)

    st.divider()
    panel_heading(
        "Claim support",
        "What this snapshot can—and cannot—say",
        f"{len(overview.source_files)} source files passed the committed schema and SHA-256 contract.",
    )
    render_evidence_notes(overview.evidence_notes)
    render_provenance(overview)
