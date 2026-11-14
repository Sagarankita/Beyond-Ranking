from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from streamlit_app.data.adapters import title_case


CURRENT_COLOR = "#b9c6c1"
RECOMMENDED_COLOR = "#14785b"
ACCENT_COLOR = "#d17a47"
REFERENCE_COLOR = "#94a39d"

OBJECTIVE_DESCRIPTIONS = {
    "research": "Research output and citation impact indicators.",
    "innovation": "Patent application and industry project indicators.",
    "student_development": "Student research participation, placements, and higher-study indicators.",
    "societal_contribution": "Open-access publication and outreach participation indicators.",
}


def allocation_figure(rows: pd.DataFrame, strategy_label: str) -> go.Figure:
    values = rows.copy()
    values["maximum"] = values[["current", "recommended"]].abs().max(axis=1).clip(lower=1)
    values["current_percent"] = values["current"].abs() / values["maximum"] * 100
    values["recommended_percent"] = values["recommended"].abs() / values["maximum"] * 100
    labels = values["variable"].map(title_case)
    figure = go.Figure()
    figure.add_bar(
        name="Current",
        x=values["current_percent"],
        y=labels,
        orientation="h",
        marker_color=CURRENT_COLOR,
        customdata=values[["current", "unit"]],
        hovertemplate="<b>%{y}</b><br>Current: %{customdata[0]:,.4g} %{customdata[1]}<extra></extra>",
    )
    figure.add_bar(
        name=strategy_label,
        x=values["recommended_percent"],
        y=labels,
        orientation="h",
        marker_color=RECOMMENDED_COLOR,
        customdata=values[["recommended", "difference", "unit"]],
        hovertemplate=(
            f"<b>%{{y}}</b><br>{strategy_label}: %{{customdata[0]:,.4g}} %{{customdata[2]}}"
            "<br>Difference: %{customdata[1]:+,.4g} %{customdata[2]}<extra></extra>"
        ),
    )
    figure.update_layout(
        barmode="group",
        height=max(330, len(values) * 42),
        margin=dict(l=8, r=12, t=40, b=12),
        legend=dict(orientation="h", y=1.08, x=0),
        xaxis=dict(visible=False, range=[0, 105]),
        yaxis=dict(autorange="reversed", title=None),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#33423e", size=11),
        hoverlabel=dict(bgcolor="#173330", font_color="white"),
    )
    return figure


def kpi_interval_figure(rows: pd.DataFrame) -> go.Figure:
    values = rows.copy()
    values["maximum"] = values[["current_upper", "recommended_upper", "current", "recommended"]].max(axis=1).clip(lower=1) * 1.05
    for prefix in ("current", "recommended"):
        values[f"{prefix}_percent"] = values[prefix] / values["maximum"] * 100
        values[f"{prefix}_plus"] = (values[f"{prefix}_upper"] - values[prefix]) / values["maximum"] * 100
        values[f"{prefix}_minus"] = (values[prefix] - values[f"{prefix}_lower"]) / values["maximum"] * 100
    labels = values["kpi"].map(title_case)
    figure = go.Figure()
    figure.add_scatter(
        name="Current prediction",
        mode="markers",
        x=values["current_percent"],
        y=labels,
        marker=dict(color=ACCENT_COLOR, size=9, symbol="circle"),
        error_x=dict(type="data", symmetric=False, array=values["current_plus"], arrayminus=values["current_minus"], color=ACCENT_COLOR, thickness=1.4),
        customdata=values[["current", "current_lower", "current_upper"]],
        hovertemplate="<b>%{y}</b><br>Current: %{customdata[0]:,.4g}<br>Interval: %{customdata[1]:,.4g}–%{customdata[2]:,.4g}<extra></extra>",
    )
    figure.add_scatter(
        name="Recommended prediction",
        mode="markers",
        x=values["recommended_percent"],
        y=labels,
        marker=dict(color=RECOMMENDED_COLOR, size=10, symbol="diamond"),
        error_x=dict(type="data", symmetric=False, array=values["recommended_plus"], arrayminus=values["recommended_minus"], color=RECOMMENDED_COLOR, thickness=2),
        customdata=values[["recommended", "recommended_lower", "recommended_upper", "evidence"]],
        hovertemplate="<b>%{y}</b><br>Recommended: %{customdata[0]:,.4g}<br>Interval: %{customdata[1]:,.4g}–%{customdata[2]:,.4g}<br>Evidence: %{customdata[3]}<extra></extra>",
    )
    figure.update_layout(
        height=max(290, len(values) * 43),
        margin=dict(l=8, r=16, t=40, b=12),
        legend=dict(orientation="h", y=1.08, x=0),
        xaxis=dict(visible=False, range=[0, 105]),
        yaxis=dict(autorange="reversed", title=None),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#33423e", size=11),
        hoverlabel=dict(bgcolor="#173330", font_color="white"),
    )
    return figure


def live_allocation_figure(rows: pd.DataFrame, unit: str) -> go.Figure:
    """Compare exact compatible-unit values without visual normalization."""
    values = rows[rows["unit"] == unit].copy()
    labels = values["variable"].map(title_case)
    figure = go.Figure()
    figure.add_bar(
        name="Reference",
        x=values["reference"],
        y=labels,
        orientation="h",
        marker_color=REFERENCE_COLOR,
        customdata=values[["unit"]],
        hovertemplate="<b>%{y}</b><br>Reference: %{x:,.4g} %{customdata[0]}<extra></extra>",
    )
    if "proposed" in values:
        figure.add_bar(
            name="Proposed",
            x=values["proposed"],
            y=labels,
            orientation="h",
            marker_color=RECOMMENDED_COLOR,
            customdata=values[["delta", "unit"]],
            hovertemplate=(
                "<b>%{y}</b><br>Proposed: %{x:,.4g} %{customdata[1]}"
                "<br>Change: %{customdata[0]:+,.4g} %{customdata[1]}<extra></extra>"
            ),
        )
    figure.update_layout(
        barmode="group",
        height=max(250, len(values) * 48 + 90),
        margin=dict(l=8, r=16, t=20, b=50),
        legend=dict(orientation="h", y=1.08, x=0),
        xaxis=dict(title=unit, rangemode="tozero", tickformat=",.3~s" if unit == "INR" else ",.3~g"),
        yaxis=dict(autorange="reversed", title=None),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#23312d", size=12),
        hoverlabel=dict(bgcolor="#173330", font_color="white"),
    )
    return figure


def objective_score_figure(candidate: dict) -> go.Figure:
    names = list(candidate["objectives"])
    values = [candidate["objectives"][name]["benefit"] for name in names]
    evidence = [candidate["objectives"][name]["evidence"] for name in names]
    figure = go.Figure(
        go.Bar(
            x=values,
            y=[title_case(name) for name in names],
            orientation="h",
            marker_color=RECOMMENDED_COLOR,
            customdata=evidence,
            hovertemplate=(
                "<b>%{y}</b><br>Modeled benefit: %{x:.3f}"
                "<br>Scale: normalized benefit [0, 1]"
                "<br>Evidence: %{customdata}<extra></extra>"
            ),
        )
    )
    figure.update_layout(
        height=300,
        margin=dict(l=8, r=16, t=12, b=48),
        xaxis=dict(title="Normalized modeled benefit [0, 1]", range=[0, 1]),
        yaxis=dict(autorange="reversed", title=None),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#23312d", size=12),
        hoverlabel=dict(bgcolor="#173330", font_color="white"),
    )
    return figure


def live_kpi_interval_figure(candidate: dict) -> go.Figure:
    names = list(candidate["kpis"])
    predictions = [candidate["kpis"][name]["prediction"] for name in names]
    lower = [candidate["kpis"][name]["lower"] for name in names]
    upper = [candidate["kpis"][name]["upper"] for name in names]
    figure = go.Figure(
        go.Scatter(
            x=predictions,
            y=[title_case(name) for name in names],
            mode="markers",
            marker=dict(color=RECOMMENDED_COLOR, size=10),
            error_x=dict(
                type="data",
                symmetric=False,
                array=[high - point for high, point in zip(upper, predictions, strict=True)],
                arrayminus=[point - low for point, low in zip(predictions, lower, strict=True)],
                color=RECOMMENDED_COLOR,
            ),
            customdata=list(zip(lower, upper, strict=True)),
            hovertemplate=(
                "<b>%{y}</b><br>Prediction: %{x:,.4g}"
                "<br>Stored interval: %{customdata[0]:,.4g} to %{customdata[1]:,.4g}<extra></extra>"
            ),
        )
    )
    figure.update_layout(
        height=max(330, len(names) * 42),
        margin=dict(l=8, r=16, t=12, b=48),
        xaxis=dict(title="KPI-specific modeled value"),
        yaxis=dict(autorange="reversed", title=None),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#23312d", size=12),
        hoverlabel=dict(bgcolor="#173330", font_color="white"),
    )
    return figure


def _component_hover(item: dict) -> str:
    components = item.get("components") or []
    if not components:
        return "Underlying KPI components unavailable"
    return "<br>".join(
        f"{title_case(component['kpi'])}: weight {float(component['weight']):.0%}"
        for component in components
    )


def recommendation_objective_figure(
    rows: list[dict], mode: str = "scores"
) -> go.Figure:
    if mode not in {"scores", "changes"}:
        raise ValueError("objective chart mode must be 'scores' or 'changes'")
    comparable = [
        item
        for item in rows
        if item.get("reference") is not None
        and item.get("proposed") is not None
        and item.get("difference") is not None
        and item.get("scale") == "normalized modeled benefit [0, 1]"
    ]
    if not comparable:
        figure = go.Figure()
        figure.add_annotation(
            text="Comparable reference and selected-strategy objective scores are unavailable.",
            showarrow=False,
            font=dict(color="#46534e", size=13),
        )
        figure.update_layout(
            height=240,
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        return figure

    labels = [title_case(item["name"]) for item in comparable]
    custom = [
        [
            float(item["difference"]),
            str(item.get("evidence") or "unsupported"),
            OBJECTIVE_DESCRIPTIONS.get(item["name"], "No objective description is available."),
            _component_hover(item),
            float(item["reference"]),
            float(item["proposed"]),
        ]
        for item in comparable
    ]
    figure = go.Figure()
    if mode == "scores":
        figure.add_bar(
            name="Configured reference",
            x=[item["reference"] for item in comparable],
            y=labels,
            orientation="h",
            marker_color=REFERENCE_COLOR,
            customdata=custom,
            hovertemplate=(
                "<b>%{y}</b><br>%{customdata[2]}<br>Reference score: %{x:.3f}"
                "<br>Higher displayed score is preferred"
                "<br>Components:<br>%{customdata[3]}"
                "<br>Evidence: %{customdata[1]}<extra></extra>"
            ),
        )
        figure.add_bar(
            name="Selected strategy",
            x=[item["proposed"] for item in comparable],
            y=labels,
            orientation="h",
            marker_color=RECOMMENDED_COLOR,
            customdata=custom,
            hovertemplate=(
                "<b>%{y}</b><br>%{customdata[2]}<br>Selected score: %{x:.3f}"
                "<br>Exact change: %{customdata[0]:+.6f} score points"
                "<br>Components:<br>%{customdata[3]}"
                "<br>Evidence: %{customdata[1]}<extra></extra>"
            ),
        )
        xaxis = dict(title="Displayed normalized modeled benefit [0, 1]", range=[0, 1])
        showlegend = True
        barmode = "group"
    else:
        changes = [float(item["difference"]) for item in comparable]
        maximum = max(max(abs(value) for value in changes) * 1.18, 0.05)
        colors = [
            RECOMMENDED_COLOR if value > 1e-12 else ("#b55d43" if value < -1e-12 else REFERENCE_COLOR)
            for value in changes
        ]
        figure.add_bar(
            name="Exact score-point change",
            x=changes,
            y=labels,
            orientation="h",
            marker_color=colors,
            customdata=custom,
            hovertemplate=(
                "<b>%{y}</b><br>%{customdata[2]}"
                "<br>Reference: %{customdata[4]:.6f}"
                "<br>Selected: %{customdata[5]:.6f}"
                "<br>Change: %{x:+.6f} score points"
                "<br>Components:<br>%{customdata[3]}"
                "<br>Evidence: %{customdata[1]}<extra></extra>"
            ),
        )
        figure.add_vline(x=0.0, line_color="#6f7d77", line_width=1)
        xaxis = dict(title="Exact change in normalized score points", range=[-maximum, maximum], zeroline=False)
        showlegend = False
        barmode = "relative"
    figure.update_layout(
        barmode=barmode,
        height=330,
        margin=dict(l=8, r=16, t=20, b=54),
        legend=dict(orientation="h", y=1.08, x=0),
        showlegend=showlegend,
        xaxis=xaxis,
        yaxis=dict(autorange="reversed", title=None),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#23312d", size=12),
        hoverlabel=dict(bgcolor="#173330", font_color="white"),
    )
    return figure


def sensitivity_objective_figure(result: dict) -> go.Figure:
    families = list(result["held_fixed"]["objectives"])
    baseline = {
        name: result["held_fixed"]["objectives"][name]
        - result["held_fixed"]["objective_changes_from_baseline"][name]
        for name in families
    }
    figure = go.Figure()
    series = [
        ("Baseline selected strategy", baseline, REFERENCE_COLOR),
        ("Held fixed under changed factor", result["held_fixed"]["objectives"], ACCENT_COLOR),
    ]
    if result.get("reoptimized"):
        series.append(("Reoptimized changed scenario", result["reoptimized"]["objectives"], RECOMMENDED_COLOR))
    for label, values, color in series:
        figure.add_bar(
            name=label,
            x=[values[name] for name in families],
            y=[title_case(name) for name in families],
            orientation="h",
            marker_color=color,
            hovertemplate=f"<b>%{{y}}</b><br>{label}: %{{x:.3f}}<extra></extra>",
        )
    figure.update_layout(
        barmode="group",
        height=360,
        margin=dict(l=8, r=16, t=20, b=52),
        legend=dict(orientation="h", y=1.14, x=0),
        xaxis=dict(title="Normalized modeled benefit [0, 1]", range=[0, 1]),
        yaxis=dict(autorange="reversed", title=None),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#23312d", size=12),
        hoverlabel=dict(bgcolor="#173330", font_color="white"),
    )
    return figure


def benchmark_distribution_figure(rows: list[dict], metric: str) -> go.Figure:
    values = pd.DataFrame(rows)
    figure = go.Figure()
    algorithms = sorted(values["algorithm"].dropna().unique())
    colors = ["#0a6b52", "#397f96", "#8d6b35", "#6d5f92", "#a55445", "#53645d"]
    for algorithm, color in zip(algorithms, colors, strict=True):
        subset = values[values["algorithm"] == algorithm]
        figure.add_trace(
            go.Box(
                name=algorithm.upper().replace("_", " "),
                y=subset[metric],
                marker_color=color,
                boxpoints="all",
                jitter=0.24,
                pointpos=0,
                customdata=subset[["seed"]],
                hovertemplate=(
                    f"<b>{algorithm.upper().replace('_', ' ')}</b>"
                    f"<br>{title_case(metric)}: %{{y:.5g}}"
                    "<br>Seed: %{customdata[0]}<extra></extra>"
                ),
            )
        )
    figure.update_layout(
        height=420,
        margin=dict(l=12, r=12, t=20, b=70),
        showlegend=False,
        xaxis=dict(title=None, tickangle=-20),
        yaxis=dict(title=title_case(metric), rangemode="tozero"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#23312d", size=12),
        hoverlabel=dict(bgcolor="#173330", font_color="white"),
    )
    return figure


def interval_calibration_figure(rows: list[dict]) -> go.Figure:
    values = pd.DataFrame(rows).sort_values("observed_coverage")
    labels = values["target"].map(title_case)
    figure = go.Figure()
    figure.add_bar(
        name="Observed synthetic-test coverage",
        x=values["observed_coverage"],
        y=labels,
        orientation="h",
        marker_color=RECOMMENDED_COLOR,
        customdata=values[["nominal_coverage", "calibration_count", "test_count"]],
        hovertemplate=(
            "<b>%{y}</b><br>Observed coverage: %{x:.1%}"
            "<br>Nominal coverage: %{customdata[0]:.1%}"
            "<br>Calibration records: %{customdata[1]}"
            "<br>Test records: %{customdata[2]}<extra></extra>"
        ),
    )
    figure.add_vline(
        x=float(values["nominal_coverage"].median()),
        line_dash="dash",
        line_color=ACCENT_COLOR,
        annotation_text="Nominal target",
        annotation_position="top left",
    )
    figure.update_layout(
        height=max(390, len(values) * 42),
        margin=dict(l=8, r=16, t=36, b=48),
        xaxis=dict(title="Coverage on synthetic generator-validation test records", range=[0, 1.05], tickformat=".0%"),
        yaxis=dict(title=None),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#23312d", size=12),
        hoverlabel=dict(bgcolor="#173330", font_color="white"),
    )
    return figure


def robustness_feasibility_figure(rows: list[dict], policy: str) -> go.Figure:
    values = pd.DataFrame(rows)
    values = values[values["policy"] == policy].copy()
    labels = values["assessed_scenario_id"].map(title_case)
    figure = go.Figure()
    figure.add_bar(
        name="Held fixed",
        x=labels,
        y=values["probability_feasible_fixed"],
        marker_color=ACCENT_COLOR,
        hovertemplate="<b>%{x}</b><br>Held-fixed feasibility frequency: %{y:.1%}<extra></extra>",
    )
    figure.add_bar(
        name="Reoptimized",
        x=labels,
        y=values["probability_feasible_reoptimized"],
        marker_color=RECOMMENDED_COLOR,
        hovertemplate="<b>%{x}</b><br>Reoptimized feasibility frequency: %{y:.1%}<extra></extra>",
    )
    figure.update_layout(
        barmode="group",
        height=390,
        margin=dict(l=8, r=16, t=24, b=95),
        legend=dict(orientation="h", y=1.1, x=0),
        xaxis=dict(title=None, tickangle=-25),
        yaxis=dict(title="Feasibility frequency across saved uncertainty draws", range=[0, 1.05], tickformat=".0%"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#23312d", size=12),
        hoverlabel=dict(bgcolor="#173330", font_color="white"),
    )
    return figure
