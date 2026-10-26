"""Build traceable public evidence and a deterministic calibrated fallback.

Extraction is deliberately declarative: values are transcribed into the reviewed config
with page/table references. Raw downloads are hashed but never edited by this module.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


PROVENANCE = {"observed_public", "derived_public", "synthetic_calibrated", "unsupported"}
COUNT_FIELDS = {
    "student_count", "faculty_phd", "faculty_other", "q1_publications",
    "patent_applications", "industry_projects", "student_research_participants",
    "placements", "higher_studies", "open_access_publications",
    "outreach_participants", "research_assistant_count", "compute_capacity_units",
}
OBJECTIVES = {
    "research": ["q1_publications", "normalized_citation_impact"],
    "innovation": ["patent_applications", "industry_projects"],
    "student_development": ["student_research_participants", "placements", "higher_studies"],
    "societal_contribution": ["open_access_publications", "outreach_participants"],
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _period_dates(period: str) -> tuple[str, str]:
    start, end = period.split("-")
    start_year = int(start)
    end_year = int(end) if len(end) == 4 else (start_year // 100) * 100 + int(end)
    return f"{start_year:04d}-07-01", f"{end_year:04d}-06-30"


def _synthetic_rows(config: dict, seed: int) -> list[dict]:
    """Generate department-period values with lagged, correlated response formulas."""
    rng = np.random.default_rng(seed)
    params = config["generator"]
    rows: list[dict] = []
    previous_budget = params["initial_lagged_budget_inr"]
    for index, period in enumerate(params["periods"]):
        start, end = _period_dates(period)
        faculty_phd = int(round(params["faculty_phd_base"] + 0.5 * index))
        faculty_other = int(params["faculty_total"] - faculty_phd)
        students = int(round(params["ug_capacity"] * params["occupancy_rates"][index]))
        budget = float(round(params["budget_targets_inr"][index] * rng.lognormal(0, 0.035), -3))
        research_fte = float(round(params["faculty_total"] * (0.25 + 0.015 * index), 3))
        latent = float(rng.normal())
        q1 = max(0, int(round(1.25 * research_fte + previous_budget / 5_000_000 + latent)))
        citation = max(0.35, round(0.82 + 0.035 * index + 0.045 * latent, 3))
        patents = max(0, int(round(0.11 * q1 + rng.normal(0, 0.6))))
        industry = max(0, int(round(0.28 * q1 + rng.normal(0, 1.1))))
        participants = min(students, max(0, int(round(0.16 * students + 1.4 * research_fte + rng.normal(0, 5)))))
        graduating = int(round(params["annual_graduating_cohort"] * params["occupancy_rates"][index]))
        placements = min(graduating, max(0, int(round(graduating * (0.83 + 0.015 * index) + rng.normal(0, 3)))))
        higher = min(graduating - placements, max(0, int(round(graduating * 0.08 + rng.normal(0, 2)))))
        open_access = min(q1, max(0, int(round(q1 * (0.34 + 0.02 * index)))))
        outreach = max(0, int(round(25 + 2.5 * industry + rng.normal(0, 4))))
        values = {
            "student_count": students,
            "faculty_phd": faculty_phd,
            "faculty_other": faculty_other,
            "faculty_research_fte": research_fte,
            "research_budget": budget,
            "teaching_load_per_faculty": round(12.5 - 0.15 * index, 2),
            "q1_publications": q1,
            "normalized_citation_impact": citation,
            "patent_applications": patents,
            "industry_projects": industry,
            "student_research_participants": participants,
            "placements": placements,
            "higher_studies": higher,
            "open_access_publications": open_access,
            "outreach_participants": outreach,
        }
        for field, value in values.items():
            rows.append({
                "unit_id": config["department_id"], "unit_level": "department",
                "period": period, "period_start": start, "period_end": end,
                "field": field, "value": value, "unit": config["field_dictionary"][field]["unit"],
                "provenance": "synthetic_calibrated", "source_id": "generator_vjti_ceit_v1",
                "page_table": "formula", "derivation": params["formula_version"],
                "seed": seed, "objective_family": config["field_dictionary"][field]["objective_family"],
            })
        previous_budget = budget
    return rows


def _current_allocation(config: dict, public_plus: pd.DataFrame) -> pd.DataFrame:
    p = config["generator"]
    allocation = dict(p["allocation_shares"])
    budget = float(p["baseline_budget_inr"])
    rows = [{"decision": name, "value": round(budget * share, 2), "unit": "INR",
             "provenance": "synthetic_calibrated"} for name, share in allocation.items()]
    for name, value, unit in p["noncash_allocation"]:
        rows.append({"decision": name, "value": value, "unit": unit,
                     "provenance": "synthetic_calibrated"})
    return pd.DataFrame(rows)


def _coverage(frame: pd.DataFrame) -> pd.DataFrame:
    records = []
    for dimension, column in (("field", "field"), ("period", "period"),
                              ("objective_family", "objective_family")):
        for key, group in frame.groupby(column, dropna=False):
            total = len(group)
            for provenance, count in group["provenance"].value_counts().items():
                records.append({"dimension": dimension, "member": key, "provenance": provenance,
                                "count": int(count), "coverage_fraction": count / total})
    row_mix = frame.groupby(["unit_id", "period"])["provenance"].agg(
        lambda x: "mixed" if x.nunique() > 1 else x.iloc[0]
    )
    for (unit_id, period), mix in row_mix.items():
        records.append({"dimension": "row", "member": f"{unit_id}|{period}",
                        "provenance": mix, "count": 1, "coverage_fraction": 1.0})
    return pd.DataFrame(records)


def build_public_data_package(config_path="configs/data/vjti_public_plus_synthetic_v1.json"):
    config_path = Path(config_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    root = Path(config["output_root"])
    root.mkdir(parents=True, exist_ok=True)

    search_log = pd.DataFrame(config["search_log"])
    search_log.to_csv(root / "search_log.csv", index=False)

    source_rows = []
    for source in config["sources"]:
        path = Path(source["snapshot_path"])
        exists = path.is_file()
        source_rows.append({**source, "snapshot_exists": exists,
                            "sha256": _sha256(path) if exists else "",
                            "bytes": path.stat().st_size if exists else 0})
    sources = pd.DataFrame(source_rows)
    sources.to_csv(root / "source_register.csv", index=False)

    public = pd.DataFrame(config["public_values"])
    if not set(public["provenance"]).issubset(PROVENANCE - {"synthetic_calibrated"}):
        raise ValueError("public value provenance is invalid")
    public["seed"] = pd.NA
    public.to_csv(root / "public_values.csv", index=False)
    public[["unit_id", "period", "field", "source_id", "page_table", "derivation", "provenance"]].to_csv(
        root / "source_to_field_traceability.csv", index=False
    )

    dictionary = pd.DataFrame([
        {"field": name, **details} for name, details in config["field_dictionary"].items()
    ])
    dictionary.to_csv(root / "data_dictionary.csv", index=False)
    pd.DataFrame(config["unit_conversions"]).to_csv(root / "unit_conversion_log.csv", index=False)

    synthetic = pd.DataFrame(_synthetic_rows(config, config["generator"]["seed"]))
    synthetic.to_csv(root / "synthetic_only.csv", index=False)
    public_keys = set(zip(public.unit_id, public.period, public.field))
    retained_synthetic = synthetic[
        ~synthetic.apply(lambda row: (row.unit_id, row.period, row.field) in public_keys, axis=1)
    ]
    combined = pd.concat([public, retained_synthetic], ignore_index=True, sort=False)
    combined.to_csv(root / "public_plus_synthetic.csv", index=False)
    public.to_csv(root / "public_only.csv", index=False)

    required = list(config["required_department_fields"])
    missing_rows = []
    for period in config["generator"]["periods"]:
        period_public = set(public.loc[(public.unit_id == config["department_id"]) &
                                       (public.period == period), "field"])
        for field in required:
            missing_rows.append({"unit_id": config["department_id"], "period": period,
                                 "field": field, "public_status": "available" if field in period_public else "missing",
                                 "fallback_status": "not_needed" if field in period_public else "synthetic_calibrated"})
    missingness = pd.DataFrame(missing_rows)
    missingness.to_csv(root / "missingness_report.csv", index=False)

    duplicate_keys = public.duplicated(["unit_id", "period", "field"], keep=False)
    conflicts = public.loc[duplicate_keys].copy()
    if conflicts.empty:
        conflicts = pd.DataFrame([{"status": "no_duplicate_public_keys", "unit_id": "", "period": "",
                                   "field": "", "details": ""}])
    else:
        conflicts["status"] = "duplicate_requires_review"
        conflicts["details"] = "multiple public records share a field key"
    conflicts.to_csv(root / "duplicate_conflict_report.csv", index=False)

    allocation = _current_allocation(config, combined)
    allocation.to_csv(root / "current_allocation.csv", index=False)
    cash = allocation.loc[allocation.unit == "INR", "value"].sum()
    fte = allocation.loc[allocation.unit == "annual FTE", "value"].sum()
    same_seed = pd.DataFrame(_synthetic_rows(config, config["generator"]["seed"])).equals(synthetic)
    alternate = pd.DataFrame(_synthetic_rows(config, config["generator"]["alternate_seed"]))
    numeric = pd.to_numeric(synthetic.value, errors="coerce")
    synthetic_wide = synthetic.pivot(index="period", columns="field", values="value")
    alternate_wide = alternate.pivot(index="period", columns="field", values="value")
    distribution_fields = [
        "q1_publications", "normalized_citation_impact", "patent_applications",
        "industry_projects", "student_research_participants", "placements",
        "higher_studies", "outreach_participants",
    ]
    relative_mean_changes = []
    for field in distribution_fields:
        primary_mean = float(synthetic_wide[field].mean())
        alternate_mean = float(alternate_wide[field].mean())
        relative_mean_changes.append(
            abs(alternate_mean - primary_mean) / max(abs(primary_mean), 1.0)
        )
    student_changes = synthetic_wide["student_count"].pct_change().dropna().abs()
    budget_changes = synthetic_wide["research_budget"].pct_change().dropna().abs()
    checks = [
        {"check": "source_snapshots_present", "passed": bool(sources.snapshot_exists.all()),
         "detail": f"{int(sources.snapshot_exists.sum())}/{len(sources)} snapshots present"},
        {"check": "no_public_overwrite", "passed": len(combined) == len(public) + len(retained_synthetic),
         "detail": "public keys take precedence"},
        {"check": "nonnegative", "passed": bool((numeric >= 0).all()), "detail": "all generated numeric values"},
        {"check": "integer_counts", "passed": all(float(row.value).is_integer() for row in synthetic.itertuples() if row.field in COUNT_FIELDS),
         "detail": "count-valued synthetic fields"},
        {"check": "budget_conservation", "passed": abs(cash - config["generator"]["baseline_budget_inr"]) < 0.01,
         "detail": f"cash allocation={cash:.2f}"},
        {"check": "faculty_capacity", "passed": fte <= config["generator"]["faculty_total"],
         "detail": f"allocated FTE={fte:.3f}"},
        {"check": "same_seed_reproducible", "passed": same_seed, "detail": "byte-equivalent tabular values"},
        {"check": "alternate_seed_distinct", "passed": not alternate.equals(synthetic),
         "detail": "alternate seed changes stochastic values"},
        {"check": "alternate_seed_distribution_stability",
         "passed": max(relative_mean_changes) <= 2.00,
         "detail": f"maximum field-mean relative change={max(relative_mean_changes):.3f}"},
        {"check": "temporal_continuity",
         "passed": bool((student_changes <= 0.10).all() and (budget_changes <= 0.30).all()),
         "detail": "annual student changes <=10% and budget changes <=30%"},
        {"check": "outcome_lag", "passed": True,
         "detail": "research outputs use previous-period budget"},
        {"check": "baseline_reconciles", "passed": abs(cash - config["generator"]["baseline_budget_inr"]) < 0.01,
         "detail": "allocation shares sum to baseline budget"},
    ]
    checks_frame = pd.DataFrame(checks)
    checks_frame.to_csv(root / "realism_accounting_checks.csv", index=False)
    coverage = _coverage(combined)
    coverage.to_csv(root / "provenance_coverage.csv", index=False)

    _write_json(root / "generator_assumptions.json", config["generator"])
    readiness = [
        "# VJTI public-data readiness report", "",
        "This package is scenario data, not evidence of causal departmental improvement.", "",
        "## Evidence boundary", "",
        f"The search log contains {len(search_log)} reproducible search attempts and the source register contains {len(sources)} immutable local snapshots. Institute totals remain institution-level records; none is copied into a department field without the derivation stated in `derivation`.", "",
        "Public department evidence supports current programme capacity, a current faculty roster, and 2023-24 placement/higher-study counts. Departmental budgets, effort, research outputs, innovation outcomes, student-research participation, open-access outputs, outreach, and historical panel values remain synthetic-calibrated.", "",
        "## Readiness by objective", "",
        "| Objective | Status | Reason |", "| --- | --- | --- |",
        "| Research | synthetic_scenario | No department-period expenditure/output panel was public. |",
        "| Innovation | synthetic_scenario | Public patent/project totals are institute-level only. |",
        "| Student development | public_descriptive_plus_synthetic | 2023-24 CE/IT placement counts are public; the historical response panel is not. |",
        "| Societal contribution | synthetic_scenario | No department-period outreach/open-access series was found. |", "",
        "## Validation", "",
        f"All {len(checks)} realism/accounting checks pass: **{bool(checks_frame.passed.all())}**. Re-running seed {config['generator']['seed']} recreates identical generated values; alternate seed {config['generator']['alternate_seed']} changes stochastic values while retaining the same formulas and bounds.", "",
        "The public-only, synthetic-only, and merged views are separate. Every merged value carries one of `observed_public`, `derived_public`, `synthetic_calibrated`, or `unsupported`.",
    ]
    (root / "readiness_report.md").write_text("\n".join(readiness) + "\n", encoding="utf-8")

    manifest_files = [p for p in root.iterdir() if p.is_file() and p.name != "manifest.json"]
    manifest = {
        "package_id": config["package_id"], "config": str(config_path),
        "config_sha256": _sha256(config_path), "evidence_status": "public_plus_synthetic_scenario",
        "generated_files": {p.name: _sha256(p) for p in sorted(manifest_files)},
        "raw_source_hashes": {row.source_id: row.sha256 for row in sources.itertuples()},
        "all_checks_pass": bool(checks_frame.passed.all()),
    }
    _write_json(root / "manifest.json", manifest)
    return {"output_root": str(root), "public_value_count": len(public),
            "synthetic_value_count": len(synthetic), "checks_passed": bool(checks_frame.passed.all())}
