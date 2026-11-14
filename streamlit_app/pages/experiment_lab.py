from __future__ import annotations

import pandas as pd
import streamlit as st

from streamlit_app.api.client import DashboardApiError
from streamlit_app.components.charts import benchmark_distribution_figure
from streamlit_app.components.ui import page_header, panel_heading
from streamlit_app.data.adapters import title_case
from streamlit_app.pages.live_state import api_client, api_unavailable


METRIC_LABELS = {
    "hypervolume": "Hypervolume",
    "igd": "Inverted generational distance",
    "spacing": "Spacing",
    "feasible_solution_rate": "Feasible candidate proportion",
    "archive_size": "Archive size",
    "runtime_seconds": "Runtime",
}


def _summary_table(benchmark: dict, metric: str) -> pd.DataFrame:
    values = pd.DataFrame(benchmark["summary"])
    values = values[values["metric"] == metric].copy()
    values["Algorithm"] = values["algorithm"].str.upper().str.replace("_", " ")
    values["Median"] = values["median"]
    values["Q1"] = values["q1"]
    values["Q3"] = values["q3"]
    values["Runs"] = values["observations"].astype(int)
    return values[["Algorithm", "Median", "Q1", "Q3", "Runs"]]


def _render_distributions(benchmark: dict) -> None:
    metric = st.selectbox(
        "Metric",
        list(METRIC_LABELS),
        format_func=METRIC_LABELS.get,
        key="experiment_metric",
    )
    definition = benchmark["metric_definitions"][metric]
    direction_label = {
        "higher": "Higher values are preferred within this saved benchmark.",
        "lower": "Lower values are preferred within this saved benchmark.",
        "context": "Interpret this with quality and feasibility measures; larger is not automatically better.",
    }[definition["direction"]]
    st.caption(f"{definition['description']} {direction_label}")
    st.plotly_chart(
        benchmark_distribution_figure(benchmark["per_seed_metrics"], metric),
        width="stretch",
        config={"displayModeBar": False},
    )
    st.dataframe(
        _summary_table(benchmark, metric),
        hide_index=True,
        width="stretch",
        column_config={
            "Median": st.column_config.NumberColumn(format="%.5g"),
            "Q1": st.column_config.NumberColumn(format="%.5g"),
            "Q3": st.column_config.NumberColumn(format="%.5g"),
        },
    )
    st.caption("Boxes summarize 25 matched seeds. Individual points are saved per-seed results.")


def _render_statistics(benchmark: dict) -> None:
    tests = pd.DataFrame(benchmark["statistical_tests"])
    performed = tests[tests["status"] == "performed"].copy()
    metrics = sorted(performed["metric"].dropna().unique())
    metric = st.selectbox(
        "Paired comparison metric",
        metrics,
        format_func=lambda value: METRIC_LABELS.get(value, title_case(value)),
        key="statistics_metric",
    )
    selected = performed[performed["metric"] == metric].copy()
    selected["Comparison"] = (
        selected["algorithm_first"].str.upper().str.replace("_", " ")
        + " vs "
        + selected["algorithm_second"].str.upper().str.replace("_", " ")
    )
    selected["Holm result"] = selected["holm_adjusted_p_value"].apply(
        lambda value: "Adjusted p ≤ 0.05" if value <= 0.05 else "No adjusted evidence at 0.05"
    )
    st.dataframe(
        selected[
            [
                "Comparison",
                "paired_runs",
                "p_value",
                "holm_adjusted_p_value",
                "rank_biserial",
                "Holm result",
            ]
        ].rename(
            columns={
                "paired_runs": "Paired seeds",
                "p_value": "Wilcoxon p",
                "holm_adjusted_p_value": "Holm-adjusted p",
                "rank_biserial": "Rank-biserial effect",
            }
        ),
        hide_index=True,
        width="stretch",
        column_config={
            "Wilcoxon p": st.column_config.NumberColumn(format="%.4g"),
            "Holm-adjusted p": st.column_config.NumberColumn(format="%.4g"),
            "Rank-biserial effect": st.column_config.NumberColumn(format="%+.3f"),
        },
    )
    st.info(
        "The paired Wilcoxon test compares matched seeds without assuming normal differences. "
        "Holm adjustment controls family-wise error across the saved pairwise tests. The sign of "
        "rank-biserial effect is oriented to the first named algorithm; metric direction still matters."
    )
    st.caption("A non-significant adjusted result is not proof that two algorithms are equivalent.")


def _render_algorithms(benchmark: dict) -> None:
    st.write("These descriptions summarize implemented mechanisms, not recorded runtime traces.")
    columns = st.columns(2)
    for index, algorithm in enumerate(benchmark["algorithms"]):
        with columns[index % 2]:
            with st.expander(algorithm.upper().replace("_", " ")):
                st.write(benchmark["algorithm_explanations"][algorithm])
                if algorithm == "rion":
                    st.caption(
                        "The optional native OpenMP backend was not built in the reported workspace. "
                        "Saved results use the available implementation recorded by the benchmark artifacts."
                    )


def render() -> None:
    page_header(
        "Saved research evidence",
        "Experiment Lab",
        "Inspect the completed synthetic method benchmark without mixing it with live planning runs.",
    )
    try:
        benchmark = api_client().benchmark()
    except DashboardApiError as exc:
        api_unavailable(exc)
        return

    st.warning(benchmark["claim_boundary"])
    columns = st.columns(4)
    columns[0].metric("Completed jobs", f"{benchmark['complete_jobs']} / {benchmark['configured_jobs']}")
    columns[1].metric("Algorithms", str(len(benchmark["algorithms"])))
    columns[2].metric("Matched seeds", str(len(benchmark["seeds"])))
    columns[3].metric("Evaluations per job", str(benchmark["evaluation_budget"]))

    panel_heading(
        "Completed benchmark",
        "Six methods across matched seeds",
        "Choose a metric to see saved runs, distribution summaries, and supported paired statistics.",
    )
    distribution_tab, statistics_tab, behavior_tab = st.tabs(
        ["Performance distributions", "Paired statistics", "How the methods search"]
    )
    with distribution_tab:
        _render_distributions(benchmark)
    with statistics_tab:
        _render_statistics(benchmark)
    with behavior_tab:
        _render_algorithms(benchmark)

    with st.expander("Benchmark provenance"):
        st.json(
            {
                "benchmark_id": benchmark["benchmark_id"],
                "evidence_class": benchmark["evidence_class"],
                "seeds": benchmark["seeds"],
                "evaluation_budget": benchmark["evaluation_budget"],
                "metrics_path": benchmark["metrics_path"],
                "statistics_path": benchmark["statistics_path"],
                "native_rion_openmp_built": benchmark["native_rion_openmp_built"],
            }
        )

    panel_heading(
        "Current interactive run",
        "Not a benchmark result",
        "One live run uses one seed and 16 evaluations. It is never appended to the completed 25-seed study.",
    )
    status = st.session_state.get("br_run_status")
    if status:
        st.json(
            {
                key: status.get(key)
                for key in (
                    "run_id",
                    "algorithm",
                    "seed",
                    "evaluation_budget",
                    "status",
                    "feasible_candidate_count",
                )
            }
        )
    else:
        st.caption("No interactive run has been started in this browser session.")
