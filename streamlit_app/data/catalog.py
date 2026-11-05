from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = Path(__file__).with_name("catalog.json")


SNAPSHOT_SPECS: list[dict[str, Any]] = [
    {
        "id": "synthetic-phase7-v1",
        "label": "Synthetic method fixture",
        "version": "phase7-synthetic-v1",
        "evidenceClass": "synthetic_method_fixture",
        "evidenceLabel": "Synthetic fixture · not empirical",
        "supportsInterventionClaims": False,
        "claimBoundary": "Method-validation fixture only. Predictions are illustrative, noncausal, and not institution-specific.",
        "files": [
            {"id": "manifest", "sourcePath": "results/reporting/phase7-synthetic-v1/manifest.json", "format": "json"},
            {"id": "allocations", "sourcePath": "results/reporting/phase7-synthetic-v1/current_vs_strategy_allocations.csv", "format": "csv", "requiredColumns": ["strategy", "variable", "unit", "current", "recommended", "difference"], "numericColumns": ["current", "recommended", "difference"], "units": {"current": "unit column", "recommended": "unit column", "difference": "unit column"}},
            {"id": "kpis", "sourcePath": "results/reporting/phase7-synthetic-v1/current_vs_strategy_kpis.csv", "format": "csv", "requiredColumns": ["strategy", "kpi", "current_prediction", "current_lower", "current_upper", "recommended_prediction", "recommended_lower", "recommended_upper"], "numericColumns": ["current_prediction", "current_lower", "current_upper", "recommended_prediction", "recommended_lower", "recommended_upper"], "units": {"current_prediction": "KPI-specific", "recommended_prediction": "KPI-specific"}},
            {"id": "resources", "sourcePath": "results/reporting/phase7-synthetic-v1/resource_utilization.csv", "format": "csv", "requiredColumns": ["strategy", "cost", "budget_limit", "budget_utilization", "budget_remaining", "research_fte", "research_fte_capacity", "research_fte_utilization"], "numericColumns": ["cost", "budget_limit", "budget_utilization", "budget_remaining", "research_fte", "research_fte_capacity", "research_fte_utilization"], "units": {"cost": "INR", "budget_limit": "INR", "research_fte": "FTE"}},
            {"id": "constraints", "sourcePath": "results/reporting/phase7-synthetic-v1/constraint_checks.csv", "format": "csv", "requiredColumns": ["strategy", "constraint", "residual", "passed"], "numericColumns": ["residual"]},
            {"id": "portfolio", "sourcePath": "results/reporting/phase7-synthetic-v1/strategy_portfolio.csv", "format": "csv", "requiredColumns": ["selection_status", "allocation_group", "cost", "feasible", "objective_benefit__research"], "numericColumns": ["cost", "objective_benefit__research"]},
        ],
    },
    {
        "id": "vjti-public-synthetic-v1",
        "label": "VJTI public + synthetic scenario",
        "version": "vjti_public_plus_synthetic_experiments_v1",
        "evidenceClass": "public_plus_synthetic_scenario",
        "evidenceLabel": "Public-calibrated · synthetic responses",
        "supportsInterventionClaims": False,
        "claimBoundary": "Public evidence calibrates the baseline, but intervention responses are synthetic, associational, and noncausal.",
        "files": [
            {"id": "manifest", "sourcePath": "artifacts/public_experiments/vjti_v1/experiment_manifest.json", "format": "json"},
            {"id": "allocations", "sourcePath": "artifacts/public_experiments/vjti_v1/strategy_allocations.csv", "format": "csv", "requiredColumns": ["strategy_id", "strategy_type", "scenario", "source_artifact", "feasible", "total_cost", "budget_remaining", "decision", "value"], "numericColumns": ["total_cost", "budget_remaining", "value"], "units": {"total_cost": "INR", "budget_remaining": "INR", "value": "decision-specific"}},
            {"id": "kpis", "sourcePath": "artifacts/public_experiments/vjti_v1/strategy_kpis.csv", "format": "csv", "requiredColumns": ["strategy_id", "strategy_type", "scenario", "kpi", "prediction", "lower", "upper"], "numericColumns": ["prediction", "lower", "upper"], "units": {"prediction": "KPI-specific", "lower": "KPI-specific", "upper": "KPI-specific"}},
            {"id": "resources", "sourcePath": "artifacts/public_experiments/vjti_v1/strategy_resource_summary.csv", "format": "csv", "requiredColumns": ["strategy_id", "strategy_type", "scenario", "total_cost", "budget_remaining", "allocated_faculty_fte", "resource_feasible"], "numericColumns": ["total_cost", "budget_remaining", "allocated_faculty_fte"], "units": {"total_cost": "INR", "budget_remaining": "INR", "allocated_faculty_fte": "FTE"}},
            {"id": "constraints", "sourcePath": "artifacts/public_experiments/vjti_v1/strategy_constraints.csv", "format": "csv", "requiredColumns": ["strategy_id", "constraint", "residual", "normalized_residual"], "numericColumns": ["residual", "normalized_residual"]},
            {"id": "evidence", "sourcePath": "artifacts/evidence_modeling/vjti_v1/kpi_evidence_registry.csv", "format": "csv", "requiredColumns": ["kpi", "status", "public_model_status", "synthetic_model_status", "claim_boundary"]},
        ],
    },
    {
        "id": "vjti-empirical-v1",
        "label": "VJTI empirical public evidence",
        "version": "vjti-ceit-public-plus-synthetic-v1",
        "evidenceClass": "empirical_descriptive",
        "evidenceLabel": "Observed + derived · descriptive only",
        "supportsInterventionClaims": False,
        "claimBoundary": "Descriptive public evidence only. No empirical intervention-response model or empirical optimization run is available.",
        "files": [
            {"id": "manifest", "sourcePath": "artifacts/public_data/vjti_ceit_v1/manifest.json", "format": "json"},
            {"id": "coverage", "sourcePath": "artifacts/public_data/vjti_ceit_v1/provenance_coverage.csv", "format": "csv", "requiredColumns": ["dimension", "member", "provenance", "count", "coverage_fraction"], "numericColumns": ["count", "coverage_fraction"]},
            {"id": "sources", "sourcePath": "artifacts/public_data/vjti_ceit_v1/source_register.csv", "format": "csv", "requiredColumns": ["source_id", "title", "url", "access_date", "authority", "retrieval_status", "sha256"]},
            {"id": "publicOnly", "sourcePath": "artifacts/public_experiments/vjti_v1/public_only_sensitivity.csv", "format": "csv", "requiredColumns": ["analysis_track", "outcome", "denominator", "numerator", "denominator_value", "rate", "source_artifact", "causal_claim"], "numericColumns": ["numerator", "denominator_value", "rate"]},
            {"id": "evidence", "sourcePath": "artifacts/evidence_modeling/vjti_v1/kpi_evidence_registry.csv", "format": "csv", "requiredColumns": ["kpi", "status", "public_model_status", "synthetic_model_status", "claim_boundary"]},
        ],
    },
]


def build_catalog() -> dict[str, Any]:
    snapshots: list[dict[str, Any]] = []
    for snapshot in SNAPSHOT_SPECS:
        files: list[dict[str, Any]] = []
        for definition in snapshot["files"]:
            source = (REPOSITORY_ROOT / definition["sourcePath"]).resolve()
            data = source.read_bytes()
            files.append(
                {
                    **definition,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "bytes": len(data),
                }
            )
        snapshots.append({**snapshot, "files": files})
    return {
        "schemaVersion": 1,
        "description": "Allow-listed immutable artifacts for the Streamlit decision studio.",
        "snapshots": snapshots,
    }


def write_catalog(path: Path = CATALOG_PATH) -> None:
    path.write_text(json.dumps(build_catalog(), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Refresh the committed UI artifact catalog.")
    parser.add_argument("--write", action="store_true", help="Write streamlit_app/data/catalog.json")
    args = parser.parse_args()
    if not args.write:
        parser.error("Pass --write to refresh the catalog.")
    write_catalog()
    print(f"Wrote {CATALOG_PATH.relative_to(REPOSITORY_ROOT)}")
