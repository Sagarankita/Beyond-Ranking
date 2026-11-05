from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from streamlit_app.data.adapters import title_case
from streamlit_app.data.loaders import load_artifact
from streamlit_app.data.types import EvidenceClass, EvidenceNote, Metric, OverviewSnapshot


def load_css() -> None:
    css_path = __import__("pathlib").Path(__file__).resolve().parents[1] / "styles" / "app.css"
    st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def page_header(eyebrow: str, title: str, description: str) -> None:
    st.markdown(
        f"""
        <section class="br-hero">
          <span>{html.escape(eyebrow)}</span>
          <h1>{html.escape(title)}</h1>
          <p>{html.escape(description)}</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def evidence_banner(snapshot: OverviewSnapshot) -> None:
    css_class = {
        EvidenceClass.SYNTHETIC: "synthetic",
        EvidenceClass.MIXED: "mixed",
        EvidenceClass.EMPIRICAL: "empirical",
    }[snapshot.evidence_class]
    st.markdown(
        f"""
        <section class="br-evidence br-evidence--{css_class}">
          <strong>{html.escape(snapshot.evidence_label)}</strong>
          <p>{html.escape(snapshot.claim_boundary)}</p>
          <code>{html.escape(snapshot.version)}</code>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_metrics(metrics: list[Metric]) -> None:
    columns = st.columns(len(metrics))
    for column, metric in zip(columns, metrics, strict=True):
        with column:
            st.metric(metric.label, metric.value, help=metric.detail)
            st.caption(metric.detail)


def panel_heading(eyebrow: str, title: str, description: str, help_text: str = "") -> None:
    st.markdown(f"<span class='br-overline'>{html.escape(eyebrow)}</span>", unsafe_allow_html=True)
    st.subheader(title, help=help_text or None)
    st.caption(description)


def empty_state(title: str, body: str) -> None:
    st.markdown(
        f"<div class='br-empty'><strong>{html.escape(title)}</strong><p>{html.escape(body)}</p></div>",
        unsafe_allow_html=True,
    )


def format_value(value: float, unit: str) -> str:
    if unit == "INR":
        if abs(value) >= 10_000_000:
            return f"₹{value / 10_000_000:.2f} Cr"
        if abs(value) >= 100_000:
            return f"₹{value / 100_000:.2f} L"
        return f"₹{value:,.0f}"
    if unit == "FTE":
        return f"{value:,.1f} FTE"
    return f"{value:,.4g} {unit}".strip()


def render_resources(rows: pd.DataFrame) -> None:
    for row in rows.to_dict("records"):
        left, right = st.columns([3, 2])
        left.markdown(f"**{row['label']}**")
        right.markdown(f"<div class='br-value'>{format_value(float(row['value']), row['unit'])}</div>", unsafe_allow_html=True)
        limit = float(row["limit"])
        if limit > 0:
            ratio = float(row["value"]) / limit
            st.progress(min(max(ratio, 0.0), 1.0), text=f"{ratio * 100:.1f}% of {format_value(limit, row['unit'])}")
        else:
            st.caption("Saved absolute allocation; no compatible capacity is recorded in this artifact.")


def render_constraints(rows: pd.DataFrame) -> None:
    passed = int(rows["passed"].sum())
    failed = len(rows) - passed
    status = "Feasible" if failed == 0 else f"{failed} failed"
    st.metric("Named constraints passed", f"{passed} / {len(rows)}", status)
    display = rows.sort_values("residual", ascending=False).head(8).copy()
    display["Constraint"] = display["constraint"].map(title_case)
    display["Residual"] = display["residual"].map(lambda value: f"{float(value):.2e}")
    display["Status"] = display["passed"].map({True: "Passed", False: "Failed"})
    st.dataframe(display[["Constraint", "Residual", "Status"]], hide_index=True, width="stretch")
    st.caption("Residual ≤ 1×10⁻⁹ is the persisted reporting pass rule; the UI does not reevaluate or repair a candidate.")


def render_evidence_notes(notes: list[EvidenceNote]) -> None:
    columns = st.columns(2)
    for index, note in enumerate(notes[:8]):
        with columns[index % 2]:
            st.markdown(
                f"""
                <article class="br-note br-note--{html.escape(note.status)}">
                  <span>{html.escape(note.status)}</span>
                  <strong>{html.escape(note.title)}</strong>
                  <p>{html.escape(note.body)}</p>
                </article>
                """,
                unsafe_allow_html=True,
            )


def render_provenance(snapshot: OverviewSnapshot) -> None:
    with st.expander("Artifact provenance and validated downloads"):
        st.caption("Downloads are the exact bytes validated and rendered for this snapshot.")
        for file in snapshot.source_files:
            artifact = load_artifact(file)
            left, right = st.columns([4, 1])
            with left:
                st.markdown(f"**{title_case(file.id)}**  ")
                st.caption(f"{file.source_path} · SHA-256 {file.sha256[:16]}… · {file.bytes:,} bytes")
            with right:
                st.download_button(
                    "Download",
                    artifact.raw,
                    file_name=file.source_path.rsplit("/", 1)[-1],
                    mime="text/csv" if file.format == "csv" else "application/json",
                    key=f"download-{snapshot.id}-{file.id}",
                    width="stretch",
                )
