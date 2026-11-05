from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from streamlit_app.components.ui import page_header


@dataclass(frozen=True)
class Placeholder:
    eyebrow: str
    title: str
    phase: str
    description: str
    planned: tuple[str, ...]


PAGES = {
    "scenario": Placeholder("Configure and execute", "Scenario Studio", "Prompt 2", "A guided, backend-generated scenario editor and genuine optimizer submission flow will live here.", ("Allowlisted datasets and configurations", "Backend-defined decision variables and constraints", "Durable episodes and run history")),
    "algorithm": Placeholder("Compare methods", "Algorithm Lab", "Prompt 3", "Authentic per-seed benchmark distributions and compatible run comparisons will be added without inventing convergence history.", ("Median and IQR leaderboard", "Per-seed metric distributions", "Valid Wilcoxon/Holm results where available")),
    "pareto": Placeholder("Inspect trade-offs", "Pareto Explorer", "Prompt 3", "Saved and newly generated candidates will link to exact archived rows, allocations, intervals, and constraints.", ("Selectable supported axes", "Exact candidate provenance", "Pin up to three candidates")),
    "robustness": Placeholder("Stress assumptions", "Robustness Lab", "Prompt 4", "Saved assessment, fixed-allocation stress tests, and reoptimization will remain distinct backend-backed operations.", ("Feasibility probabilities", "Saved percentile summaries", "Comparable assumption sensitivity")),
    "target": Placeholder("Reverse optimization", "Target-Cost Explorer", "Prompt 4", "The existing target-cost workflow will expose genuine solver status, supported targets, and verified recommendations.", ("Backend-supported target definitions", "Minimum modeled cost", "Honest infeasible and unsupported states")),
    "evidence": Placeholder("Trace and verify", "Evidence & Audit", "Prompt 5", "A presentation-friendly audit surface will expose configs, hashes, seeds, accounting, and original artifacts.", ("Evidence-lane provenance", "Evaluation accounting", "Downloadable verified artifacts")),
}


def render(page_id: str) -> None:
    page = PAGES[page_id]
    page_header(page.eyebrow, page.title, page.description)
    st.info(f"{page.phase} · not executable yet", icon="ℹ️")
    st.subheader("Planned capabilities")
    for item in page.planned:
        st.markdown(f"- {item}")
    st.warning("No control on this page starts backend work. Execution will be added only through a validated Python workflow in the corresponding phase.", icon="⚠️")
