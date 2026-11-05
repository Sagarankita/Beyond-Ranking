from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from streamlit_app.data.adapters import title_case


CURRENT_COLOR = "#b9c6c1"
RECOMMENDED_COLOR = "#14785b"
ACCENT_COLOR = "#d17a47"


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
