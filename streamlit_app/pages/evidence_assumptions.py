from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from streamlit_app.api.client import DashboardApiError
from streamlit_app.components.charts import (
    interval_calibration_figure,
    robustness_feasibility_figure,
)
from streamlit_app.components.ui import page_header, panel_heading
from streamlit_app.data.adapters import title_case
from streamlit_app.pages.live_state import api_client, api_unavailable


def _render_evidence_map(defaults: dict, evidence: dict) -> None:
    public_dea = evidence["public_dea"]
    st.error(
        f"Public DEA blocked: {public_dea['complete_dmus']} complete comparable public DMUs "
        f"against {public_dea['required_dmus']} required. {public_dea['reason']}"
    )
    synthetic_dea = evidence["synthetic_dea"]
    st.warning(
        f"Synthetic DEA fixture: {synthetic_dea['successful_solves']} optimal solves across "
        f"{synthetic_dea['dmu_count']} synthetic units. This tests the method only and is not "
        "an observed institutional efficiency ranking."
    )

    panel_heading(
        "Input evidence register",
        "Units, support and provenance",
        "Decision-variable provenance comes from the validated allocation configuration.",
    )
    rows = []
    for variable in defaults["decision_variables"]:
        rows.append(
            {
                "Variable": title_case(variable["name"]),
                "Unit": variable["unit"],
                "Bounds": f"{variable['lower']:,.4g} to {variable['upper']:,.4g}",
                "Increment": f"{variable['increment']:,.4g}",
                "Evidence category": variable["provenance"],
                "Scenario editable": "No",
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption(
        "Supported scenario edits are budget limit, faculty total, and cost multipliers for existing monetary decisions."
    )

    with st.expander("Public source register"):
        sources = pd.DataFrame(evidence["sources"])
        sources["Source"] = sources["title"]
        sources["Scope"] = sources["scope"].map(title_case)
        sources["Access date"] = sources["access_date"]
        sources["Snapshot verified"] = sources["snapshot_exists"].map(
            lambda value: "Yes" if value else "No"
        )
        st.dataframe(
            sources[["Source", "authority", "Scope", "document_period", "Access date", "Snapshot verified", "sha256"]].rename(
                columns={
                    "authority": "Authority",
                    "document_period": "Period",
                    "sha256": "Snapshot SHA-256",
                }
            ),
            hide_index=True,
            width="stretch",
        )

    with st.expander("Data dictionary"):
        dictionary = pd.DataFrame(evidence["data_dictionary"])
        dictionary["Field"] = dictionary["field"].map(title_case)
        st.dataframe(
            dictionary[["Field", "unit", "type", "role", "objective_family", "description"]].rename(
                columns={
                    "unit": "Unit",
                    "type": "Type",
                    "role": "Role",
                    "objective_family": "Objective family",
                    "description": "Definition",
                }
            ),
            hide_index=True,
            width="stretch",
        )


def _render_kpi_models(evidence: dict) -> None:
    st.warning(
        "These models validate recovery of calibrated synthetic relationships. They are scenario-model outputs, not causal VJTI forecasts."
    )
    registry = pd.DataFrame(evidence["kpi_registry"])
    modeled = registry[registry["synthetic_model_status"] == "trained_generator_validation"]
    targets = sorted(modeled["kpi"].unique())
    target = st.selectbox("KPI", targets, format_func=title_case, key="evidence_kpi")
    selected_model = evidence["selected_models"][target]
    interval = next(item for item in evidence["interval_calibration"] if item["target"] == target)
    target_row = modeled[modeled["kpi"] == target].iloc[0]
    cards = st.columns(4)
    cards[0].metric("Selected model", selected_model.title())
    cards[1].metric("Synthetic share", f"{target_row['synthetic_share']:.0%}")
    cards[2].metric("Observed interval coverage", f"{interval['observed_coverage']:.1%}")
    cards[3].metric("Nominal interval target", f"{interval['nominal_coverage']:.0%}")

    metrics = pd.DataFrame(evidence["model_test_metrics"])
    comparison = metrics[metrics["target"] == target].copy()
    comparison["Model"] = comparison["model"].str.title()
    st.dataframe(
        comparison[["Model", "mae", "rmse", "validation_type"]].rename(
            columns={"mae": "Test MAE", "rmse": "Test RMSE", "validation_type": "Validation"}
        ),
        hide_index=True,
        width="stretch",
        column_config={
            "Test MAE": st.column_config.NumberColumn(format="%.4g"),
            "Test RMSE": st.column_config.NumberColumn(format="%.4g"),
        },
    )
    st.caption(
        "MAE and RMSE compare candidate models on held-out synthetic generator-validation records. They do not measure observed policy performance."
    )

    support = evidence["training_support_by_target"][target]
    with st.expander("Training support ranges"):
        support_rows = [
            {
                "Feature": title_case(name),
                "Minimum": values["minimum"],
                "Maximum": values["maximum"],
            }
            for name, values in support.items()
        ]
        st.dataframe(pd.DataFrame(support_rows), hide_index=True, width="stretch")
        st.caption("Recommendations outside these generator-training ranges are flagged by the evaluator.")

    panel_heading(
        "Interval calibration",
        "Nine saved KPI checks",
        "Coverage is measured on the synthetic generator-validation test split.",
    )
    st.plotly_chart(
        interval_calibration_figure(evidence["interval_calibration"]),
        width="stretch",
        config={"displayModeBar": False},
    )


def _render_robustness(evidence: dict) -> None:
    robustness = evidence["robustness"]
    st.warning(
        "Synthetic robustness fixture. It does not estimate real-world causal effects or VJTI policy outcomes."
    )
    rows = robustness["fixed_vs_reoptimized"]
    policies = sorted({item["policy"] for item in rows})
    policy = st.selectbox(
        "Saved strategy policy",
        policies,
        format_func=title_case,
        key="robustness_policy",
    )
    st.plotly_chart(
        robustness_feasibility_figure(rows, policy),
        width="stretch",
        config={"displayModeBar": False},
    )
    st.info(robustness["interpretation"])
    selected = pd.DataFrame([item for item in rows if item["policy"] == policy])
    selected["Scenario"] = selected["assessed_scenario_id"].map(title_case)
    st.dataframe(
        selected[
            [
                "Scenario",
                "probability_feasible_fixed",
                "probability_feasible_reoptimized",
                "delta_reoptimized_minus_fixed__probability_feasible",
                "draws_fixed",
            ]
        ].rename(
            columns={
                "probability_feasible_fixed": "Held-fixed feasibility frequency",
                "probability_feasible_reoptimized": "Reoptimized feasibility frequency",
                "delta_reoptimized_minus_fixed__probability_feasible": "Difference",
                "draws_fixed": "Uncertainty draws",
            }
        ),
        hide_index=True,
        width="stretch",
        column_config={
            "Held-fixed feasibility frequency": st.column_config.NumberColumn(format="%.3f"),
            "Reoptimized feasibility frequency": st.column_config.NumberColumn(format="%.3f"),
            "Difference": st.column_config.NumberColumn(format="%+.3f"),
        },
    )


def _render_reproduction(defaults: dict, evidence: dict) -> None:
    checks = pd.DataFrame(evidence["audit_checks"])
    counts = checks["status"].value_counts().to_dict()
    cards = st.columns(3)
    cards[0].metric("Audit checks", str(len(checks)))
    cards[1].metric("Passed", str(counts.get("pass", 0)))
    cards[2].metric("Evidence gaps", str(counts.get("evidence_gap", 0)))
    st.dataframe(
        checks[["check", "category", "status", "evidence", "detail"]].rename(
            columns={
                "check": "Check",
                "category": "Category",
                "status": "Status",
                "evidence": "Evidence",
                "detail": "Detail",
            }
        ),
        hide_index=True,
        width="stretch",
    )
    panel_heading("Core assumptions", "Claim boundary", defaults["claim_boundary"])
    st.markdown(
        "- Reference allocation is configured scenario data, not verified current spending.\n"
        "- KPI relationships are public-calibrated plus synthetic and do not prove causal effects.\n"
        "- Only feasible candidates independently rechecked by the canonical evaluator are displayed.\n"
        "- Cross-scenario candidate comparisons require an explicit normalization contract."
    )
    st.caption(f"Config SHA-256: `{defaults['config_sha256']}`")
    st.caption(f"Model manifest SHA-256: `{defaults['model_manifest_sha256']}`")

    provenance = {
        "evidence_summary": evidence,
        "config_sha256": defaults["config_sha256"],
        "model_manifest_sha256": defaults["model_manifest_sha256"],
    }
    st.download_button(
        "Download evidence and audit provenance",
        json.dumps(provenance, indent=2, sort_keys=True),
        file_name="beyond-ranking-evidence-provenance.json",
        mime="application/json",
        width="stretch",
    )

    status = st.session_state.get("br_run_status")
    candidates = st.session_state.get("br_candidates", [])
    if status:
        st.download_button(
            "Download browser-session run provenance",
            json.dumps({"run": status, "candidates": candidates}, indent=2, sort_keys=True),
            file_name=f"run-{status['run_id']}-provenance.json",
            mime="application/json",
            width="stretch",
        )


def render() -> None:
    page_header(
        "Traceable inputs and limits",
        "Evidence & Assumptions",
        "Inspect sources, model support, robustness modes, audit checks, and downloadable provenance.",
    )
    try:
        client = api_client()
        defaults = client.defaults()
        evidence = client.evidence()
    except DashboardApiError as exc:
        api_unavailable(exc)
        return

    evidence_tab, model_tab, robustness_tab, reproduction_tab = st.tabs(
        ["Evidence map", "KPI models", "Robustness", "Reproduction audit"]
    )
    with evidence_tab:
        _render_evidence_map(defaults, evidence)
    with model_tab:
        _render_kpi_models(evidence)
    with robustness_tab:
        _render_robustness(evidence)
    with reproduction_tab:
        _render_reproduction(defaults, evidence)
