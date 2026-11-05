from __future__ import annotations

from typing import Any

import pandas as pd

from .contracts import finite_number, parse_boolean
from .types import EvidenceClass, EvidenceNote, LoadedSnapshot, Metric, OverviewSnapshot


def title_case(value: str) -> str:
    return " ".join(
        word.capitalize()
        for word in value.removeprefix("policy_").replace("__", " · ").replace("_", " ").split()
    )


def _frame(snapshot: LoadedSnapshot, artifact_id: str) -> pd.DataFrame:
    frame = snapshot.artifacts[artifact_id].rows
    if frame is None:
        return pd.DataFrame()
    return frame.copy()


def _json_object(snapshot: LoadedSnapshot, artifact_id: str) -> dict[str, Any]:
    value = snapshot.artifacts[artifact_id].json
    return value if isinstance(value, dict) else {}


def _synthetic(snapshot: LoadedSnapshot) -> OverviewSnapshot:
    allocation_rows = _frame(snapshot, "allocations")
    kpi_rows = _frame(snapshot, "kpis")
    resource_rows = _frame(snapshot, "resources")
    constraint_rows = _frame(snapshot, "constraints")
    portfolio_rows = _frame(snapshot, "portfolio")
    manifest = _json_object(snapshot, "manifest")
    strategies = list(dict.fromkeys(allocation_rows["strategy"].tolist()))

    allocations = pd.DataFrame(
        {
            "strategy": allocation_rows["strategy"],
            "variable": allocation_rows["variable"],
            "unit": allocation_rows["unit"],
            "current": allocation_rows["current"].map(lambda value: finite_number(value, "allocation current")),
            "recommended": allocation_rows["recommended"].map(lambda value: finite_number(value, "allocation recommended")),
            "difference": allocation_rows["difference"].map(lambda value: finite_number(value, "allocation difference")),
        }
    )
    kpis = pd.DataFrame(
        {
            "strategy": kpi_rows["strategy"],
            "kpi": kpi_rows["kpi"],
            "current": kpi_rows["current_prediction"].map(lambda value: finite_number(value, "current KPI prediction")),
            "current_lower": kpi_rows["current_lower"].map(lambda value: finite_number(value, "current KPI lower interval")),
            "current_upper": kpi_rows["current_upper"].map(lambda value: finite_number(value, "current KPI upper interval")),
            "recommended": kpi_rows["recommended_prediction"].map(lambda value: finite_number(value, "recommended KPI prediction")),
            "recommended_lower": kpi_rows["recommended_lower"].map(lambda value: finite_number(value, "recommended KPI lower interval")),
            "recommended_upper": kpi_rows["recommended_upper"].map(lambda value: finite_number(value, "recommended KPI upper interval")),
            "evidence": "synthetic_method_fixture",
        }
    )
    resources = pd.DataFrame(
        [
            item
            for row in resource_rows.to_dict("records")
            for item in (
                {
                    "strategy": row["strategy"],
                    "label": "Budget",
                    "value": finite_number(row["cost"], "resource cost"),
                    "limit": finite_number(row["budget_limit"], "budget limit"),
                    "unit": "INR",
                },
                {
                    "strategy": row["strategy"],
                    "label": "Research faculty effort",
                    "value": finite_number(row["research_fte"], "research FTE"),
                    "limit": finite_number(row["research_fte_capacity"], "research FTE capacity"),
                    "unit": "FTE",
                },
            )
        ]
    )
    constraints = pd.DataFrame(
        [
            {
                "strategy": row["strategy"],
                "constraint": row["constraint"],
                "residual": finite_number(row["residual"], "constraint residual"),
                "passed": parse_boolean(row["passed"]),
            }
            for row in constraint_rows.to_dict("records")
        ]
    )
    selected = portfolio_rows[portfolio_rows["selection_status"] == "selected"]
    unique_allocations = int(selected["allocation_group"].replace("", pd.NA).nunique())
    report_id = str(manifest.get("report_id", snapshot.definition.version))

    return OverviewSnapshot(
        id=snapshot.definition.id,
        label=snapshot.definition.label,
        version=snapshot.definition.version,
        evidence_class=snapshot.definition.evidence_class,
        evidence_label=snapshot.definition.evidence_label,
        claim_boundary=snapshot.definition.claim_boundary,
        strategies=strategies,
        default_strategy="balanced" if "balanced" in strategies else (strategies[0] if strategies else None),
        allocations=allocations,
        kpis=kpis,
        resources=resources,
        constraints=constraints,
        base_metrics=[
            Metric("Saved strategies", str(len(strategies)), "Post-optimization portfolio views"),
            Metric("Unique allocations", str(unique_allocations), "Several strategy labels may share one allocation", "warning" if unique_allocations <= 1 else "default"),
            Metric("Supported objectives", "1 / 4", "Research only in this fixture", "warning"),
            Metric("Artifact version", "v1", report_id),
        ],
        evidence_notes=[
            EvidenceNote("Research objective", "Supported within this synthetic method fixture by the saved response model and reporting definitions.", "synthetic"),
            EvidenceNote("Innovation, student and societal objectives", "Unsupported zero-score dimensions in this fixture; the Overview does not chart them as meaningful outcomes.", "unsupported"),
            EvidenceNote("Institutional interpretation", "The reference allocation is illustrative and the predicted changes are not observed or causal effects.", "unsupported"),
        ],
        source_files=snapshot.definition.files,
    )


def _mixed(snapshot: LoadedSnapshot) -> OverviewSnapshot:
    allocation_rows = _frame(snapshot, "allocations")
    kpi_rows = _frame(snapshot, "kpis")
    resource_rows = _frame(snapshot, "resources")
    constraint_rows = _frame(snapshot, "constraints")
    evidence_rows = _frame(snapshot, "evidence")
    manifest = _json_object(snapshot, "manifest")
    policy_rows = allocation_rows[allocation_rows["strategy_type"] == "policy_selection"]
    strategies = list(dict.fromkeys(policy_rows["strategy_id"].tolist()))
    current_values = {
        row["decision"]: finite_number(row["value"], "current decision")
        for row in allocation_rows[allocation_rows["strategy_id"] == "current"].to_dict("records")
    }
    current_kpis = {
        row["kpi"]: row
        for row in kpi_rows[kpi_rows["strategy_id"] == "current"].to_dict("records")
    }
    evidence_by_kpi = dict(zip(evidence_rows["kpi"], evidence_rows["status"], strict=True))

    allocation_items: list[dict[str, Any]] = []
    for row in policy_rows.to_dict("records"):
        current = current_values.get(row["decision"], 0.0)
        recommended = finite_number(row["value"], "recommended decision")
        allocation_items.append(
            {
                "strategy": row["strategy_id"],
                "variable": row["decision"],
                "unit": "INR" if any(token in row["decision"] for token in ("funding", "support")) else "configured decision unit",
                "current": current,
                "recommended": recommended,
                "difference": recommended - current,
            }
        )

    kpi_items: list[dict[str, Any]] = []
    for row in kpi_rows[kpi_rows["strategy_type"] == "policy_selection"].to_dict("records"):
        current = current_kpis[row["kpi"]]
        kpi_items.append(
            {
                "strategy": row["strategy_id"],
                "kpi": row["kpi"],
                "current": finite_number(current["prediction"], "current KPI prediction"),
                "current_lower": finite_number(current["lower"], "current KPI lower interval"),
                "current_upper": finite_number(current["upper"], "current KPI upper interval"),
                "recommended": finite_number(row["prediction"], "recommended KPI prediction"),
                "recommended_lower": finite_number(row["lower"], "recommended KPI lower interval"),
                "recommended_upper": finite_number(row["upper"], "recommended KPI upper interval"),
                "evidence": evidence_by_kpi.get(row["kpi"], "unknown"),
            }
        )

    resource_items: list[dict[str, Any]] = []
    filtered_resources = resource_rows[
        (resource_rows["strategy_type"] == "policy_selection")
        | (resource_rows["strategy_id"] == "current")
    ]
    for row in filtered_resources.to_dict("records"):
        cost = finite_number(row["total_cost"], "total cost")
        budget = cost + finite_number(row["budget_remaining"], "budget remaining")
        resource_items.extend(
            [
                {"strategy": row["strategy_id"], "label": "Budget", "value": cost, "limit": budget, "unit": "INR"},
                {"strategy": row["strategy_id"], "label": "Allocated faculty effort", "value": finite_number(row["allocated_faculty_fte"], "allocated faculty FTE"), "limit": 0.0, "unit": "FTE"},
            ]
        )

    constraint_items: list[dict[str, Any]] = []
    for row in constraint_rows[constraint_rows["strategy_id"].isin(strategies)].to_dict("records"):
        residual = finite_number(row["residual"], "constraint residual")
        constraint_items.append(
            {"strategy": row["strategy_id"], "constraint": row["constraint"], "residual": residual, "passed": residual <= 1e-9}
        )

    evidence_notes = []
    for row in evidence_rows.to_dict("records"):
        status = "descriptive" if row["status"] == "public_descriptive" else ("unsupported" if row["status"] == "unsupported" else "synthetic")
        evidence_notes.append(EvidenceNote(title_case(row["kpi"]), row["claim_boundary"] or "No claim boundary recorded.", status))

    return OverviewSnapshot(
        id=snapshot.definition.id,
        label=snapshot.definition.label,
        version=snapshot.definition.version,
        evidence_class=snapshot.definition.evidence_class,
        evidence_label=snapshot.definition.evidence_label,
        claim_boundary=snapshot.definition.claim_boundary,
        strategies=strategies,
        default_strategy="policy_balanced" if "policy_balanced" in strategies else (strategies[0] if strategies else None),
        allocations=pd.DataFrame(allocation_items),
        kpis=pd.DataFrame(kpi_items),
        resources=pd.DataFrame(resource_items),
        constraints=pd.DataFrame(constraint_items),
        base_metrics=[
            Metric("Policy views", str(len(strategies)), "Saved base-scenario selections"),
            Metric("Scenario contexts", str(resource_rows["scenario"].nunique()), "Base and stress contexts in the saved package"),
            Metric("Comparison runs", str(manifest.get("completed_comparison_runs", 0)), f"{manifest.get('matched_candidate_evaluations', 0)} matched candidate evaluations per run"),
            Metric("Intervention evidence", "Synthetic", "Public-calibrated but not empirically fitted", "warning"),
        ],
        evidence_notes=evidence_notes,
        source_files=snapshot.definition.files,
    )


def _empirical(snapshot: LoadedSnapshot) -> OverviewSnapshot:
    coverage = _frame(snapshot, "coverage")
    sources = _frame(snapshot, "sources")
    public_only = _frame(snapshot, "publicOnly")
    evidence = _frame(snapshot, "evidence")

    def count_for(provenance: str) -> int:
        rows = coverage[coverage["provenance"] == provenance]
        return int(sum(finite_number(value, "coverage count") for value in rows["count"]))

    notes = [
        EvidenceNote(title_case(row["kpi"]), row["claim_boundary"] or "Descriptive public evidence only.", "descriptive")
        for row in evidence[evidence["status"] == "public_descriptive"].to_dict("records")
    ]
    notes.extend(
        [
            EvidenceNote("Public-only denominator sensitivity", f"{len(public_only)} saved descriptive checks are available; none is a causal intervention estimate.", "descriptive"),
            EvidenceNote("Modeled intervention response", "Unavailable in the empirical lane. Synthetic scenario models remain segregated in the public + synthetic snapshot.", "unsupported"),
        ]
    )
    empty = pd.DataFrame()
    return OverviewSnapshot(
        id=snapshot.definition.id,
        label=snapshot.definition.label,
        version=snapshot.definition.version,
        evidence_class=snapshot.definition.evidence_class,
        evidence_label=snapshot.definition.evidence_label,
        claim_boundary=snapshot.definition.claim_boundary,
        strategies=[],
        default_strategy=None,
        allocations=empty.copy(),
        kpis=empty.copy(),
        resources=empty.copy(),
        constraints=empty.copy(),
        base_metrics=[
            Metric("Registered sources", str(len(sources)), "Authoritative public snapshots"),
            Metric("Observed coverage", str(count_for("observed_public")), "Coverage records marked observed_public"),
            Metric("Derived coverage", str(count_for("derived_public")), "Coverage records marked derived_public"),
            Metric("Empirical optimizer runs", "0", "No intervention-response optimization exists", "warning"),
        ],
        evidence_notes=notes,
        source_files=snapshot.definition.files,
    )


def adapt_overview(snapshot: LoadedSnapshot) -> OverviewSnapshot:
    if snapshot.definition.evidence_class == EvidenceClass.SYNTHETIC:
        return _synthetic(snapshot)
    if snapshot.definition.evidence_class == EvidenceClass.MIXED:
        return _mixed(snapshot)
    if snapshot.definition.evidence_class == EvidenceClass.EMPIRICAL:
        return _empirical(snapshot)
    raise ValueError(f"Unsupported evidence class: {snapshot.definition.evidence_class}")
