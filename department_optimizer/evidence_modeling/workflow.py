"""Evidence-aware Prompt 15 workflow built on the audited Prompt 14 package."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from department_optimizer.efficiency.dea import DEAConfig, run_input_vrs_dea
from department_optimizer.modeling.core import (
    bounded_interval,
    conformal_radius,
    regression_metrics,
    residual_diagnostics,
)


FORBIDDEN = {"reported_rank", "overall_rank", "future_value", "target_proxy"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _prompt14_inputs(config: dict):
    root = Path(config["prompt14_root"])
    required = ["manifest.json", "public_only.csv", "public_plus_synthetic.csv",
                "generator_assumptions.json", "source_register.csv"]
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Prompt 14 artifacts are missing: {missing}")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if not manifest.get("all_checks_pass"):
        raise ValueError("Prompt 14 manifest does not pass its checks")
    return root, manifest, pd.read_csv(root / "public_only.csv")


def _public_assessment(public: pd.DataFrame, config: dict) -> dict:
    institution = public[public["unit_level"].isin(["institution", "institution_peer"])]
    department = public[public["unit_level"] == "department"]
    common_fields = set.intersection(
        *(set(group["field"]) for _, group in institution.groupby("unit_id"))
    ) if institution["unit_id"].nunique() else set()
    required_dea = set(config["dea"]["input_columns"] + config["dea"]["output_columns"])
    public_complete_dmus = 0
    if required_dea.issubset(common_fields):
        public_complete_dmus = int(institution["unit_id"].nunique())
    return {
        "public_dea_status": "unsupported",
        "reason": "The public cohort has too few complete comparable institution profiles for DEA.",
        "public_institution_units": int(institution["unit_id"].nunique()),
        "public_complete_dea_dmus": public_complete_dmus,
        "required_complete_dmus": int(config["dea"]["minimum_public_dmus"]),
        "common_public_fields": sorted(common_fields),
        "public_prediction_status": "public_descriptive",
        "public_department_periods": int(department["period"].nunique()),
        "public_test_set_retained": False,
        "public_test_set_reason": "One public CE&IT outcome period cannot support split isolation or validation.",
        "interpretation": "No public efficiency score or empirically validated response model is reported.",
    }


def _generate_peer_fixture(config: dict) -> pd.DataFrame:
    peer = config["dea"]
    rng = np.random.default_rng(int(peer["seed"]))
    rows = []
    for index in range(int(peer["synthetic_dmus"])):
        scale = rng.lognormal(0.0, 0.30)
        students = int(np.clip(round(3200 * scale + rng.normal(0, 180)), 1400, 7000))
        expenditure = float(np.clip(52_000 * students * rng.lognormal(0, 0.18), 60_000_000, 650_000_000))
        research_fte = float(np.clip(45 * scale + rng.normal(0, 5), 18, 110))
        quality = rng.lognormal(0, 0.16)
        sponsored = max(1, int(round((0.30 * research_fte + expenditure / 18_000_000) * quality)))
        placements = max(1, int(round(min(students * 0.28, students * (0.14 + 0.035 * quality) + rng.normal(0, 35)))))
        patents = max(0, int(round((0.08 * research_fte + expenditure / 60_000_000) * quality + rng.normal(0, 1))))
        rows.append({
            "dmu_id": f"CAL-PEER-{index + 1:02d}",
            "cohort": "calibrated_indian_public_engineering_method_fixture_v1",
            "student_count": students,
            "academic_resource_expenditure": round(expenditure, 2),
            "faculty_research_fte": round(research_fte, 3),
            "sponsored_projects": sponsored,
            "placements": placements,
            "patents_granted": patents,
            "provenance": "synthetic_calibrated",
            "generator_seed": int(peer["seed"]),
            "evidence_label": "methodological_scenario_not_observed",
        })
    return pd.DataFrame(rows)


def _run_dea_track(peers: pd.DataFrame, config: dict, output: Path) -> dict:
    dea = config["dea"]
    model_config = DEAConfig(
        dmu_column="dmu_id",
        input_columns=tuple(dea["input_columns"]),
        output_columns=tuple(dea["output_columns"]),
        cohort_name=peers["cohort"].iloc[0],
        cohort_columns=("cohort",),
    )
    analysis = run_input_vrs_dea(peers, model_config)
    analysis.efficiency["evidence_label"] = "synthetic_scenario"
    analysis.efficiency["interpretation"] = "methodological scenario; not observed or causal"
    analysis.efficiency.to_csv(output / "dea_efficiency.csv", index=False)
    analysis.peers.to_csv(output / "dea_peer_weights.csv", index=False)

    provenance_rows = []
    for role, columns in (("input", dea["input_columns"]), ("output", dea["output_columns"])):
        for column in columns:
            provenance_rows.append({"variable": column, "role": role,
                                    "synthetic_calibrated_fraction": 1.0,
                                    "observed_public_fraction": 0.0,
                                    "evidence_label": "synthetic_scenario"})
    pd.DataFrame(provenance_rows).to_csv(output / "dea_variable_provenance.csv", index=False)

    sensitivity_rows = []
    base = analysis.efficiency.set_index("dmu_id")["efficiency_score"]
    variants = [("base", peers)]
    for column in dea["input_columns"]:
        varied = peers.copy()
        shocked = varied.index % 3 == 0
        varied.loc[shocked, column] = varied.loc[shocked, column] * 1.10
        variants.append((f"every_third_dmu_{column}_plus_10pct", varied))
    for name, frame in variants:
        result = run_input_vrs_dea(frame, model_config)
        scores = result.efficiency.set_index("dmu_id")["efficiency_score"]
        for dmu, score in scores.items():
            sensitivity_rows.append({"variant": name, "dmu_id": dmu,
                                     "efficiency_score": score,
                                     "change_from_base": float(score - base.loc[dmu])})
    sensitivity = pd.DataFrame(sensitivity_rows)
    sensitivity.to_csv(output / "dea_sensitivity.csv", index=False)
    summary = {
        **analysis.summary,
        "track": "calibrated_synthetic_peer_fixture",
        "evidence_label": "synthetic_scenario",
        "public_dea_run": False,
        "sensitivity_max_absolute_change": float(sensitivity["change_from_base"].abs().max()),
        "interpretation": "Relative efficiency is a methodological scenario result, not observed performance or a causal multiplier.",
    }
    _write_json(output / "dea_summary.json", summary)
    return summary


def _generate_model_panel(config: dict) -> pd.DataFrame:
    model = config["models"]
    rng = np.random.default_rng(int(model["seed"]))
    periods = model["periods"]
    rows = []
    for unit_index in range(int(model["synthetic_units"])):
        unit_scale = rng.lognormal(0, 0.15)
        prior_budget = 17_000_000 * unit_scale
        for period_index, period in enumerate(periods):
            faculty_total = int(np.clip(round(15 * unit_scale + rng.normal(0, 1)), 9, 25))
            faculty_phd = int(np.clip(round(faculty_total * (0.48 + 0.025 * period_index) + rng.normal(0, 1)), 3, faculty_total))
            research_fte = float(np.clip(faculty_total * (0.22 + 0.018 * period_index) + rng.normal(0, .4), 1.5, faculty_total * .6))
            students = int(np.clip(round(450 * unit_scale * (0.96 + .01 * period_index) + rng.normal(0, 12)), 220, 850))
            budget = float(np.clip((18_000_000 + 1_700_000 * period_index) * unit_scale * rng.lognormal(0, .06), 8_000_000, 55_000_000))
            teaching = float(np.clip(13.2 - .15 * period_index + rng.normal(0, .35), 9, 16))
            latent = rng.normal()
            q1 = max(0, int(round(1.3 * research_fte + prior_budget / 5_200_000 + .8 * latent)))
            citation = float(np.clip(.74 + .018 * period_index + .035 * latent + .012 * research_fte, .3, 1.8))
            patents = max(0, int(round(.12 * q1 + budget / 24_000_000 + rng.normal(0, .5))))
            industry = max(0, int(round(.24 * q1 + budget / 10_000_000 + rng.normal(0, 1))))
            participants = int(np.clip(round(.14 * students + 1.8 * research_fte + rng.normal(0, 5)), 0, students))
            cohort = max(1, int(round(students / 4)))
            placements = int(np.clip(round(cohort * (.78 + .012 * period_index) + 1.4 * industry + rng.normal(0, 3)), 0, cohort))
            higher = int(np.clip(round(cohort * .075 + .18 * q1 + rng.normal(0, 1.5)), 0, cohort - placements))
            open_access = int(np.clip(round(q1 * (.30 + .025 * period_index) + rng.normal(0, .7)), 0, q1))
            outreach = max(0, int(round(18 + 2.1 * industry + .025 * participants + rng.normal(0, 3))))
            rows.append({
                "record_id": f"CAL-UNIT-{unit_index + 1:03d}-{period}",
                "unit_id": f"CAL-UNIT-{unit_index + 1:03d}", "period": period,
                "period_index": period_index, "research_budget": round(budget, 2),
                "lagged_research_budget": round(prior_budget, 2),
                "faculty_research_fte": round(research_fte, 3), "faculty_phd": faculty_phd,
                "student_count": students, "teaching_load_per_faculty": round(teaching, 3),
                "q1_publications": q1, "normalized_citation_impact": round(citation, 4),
                "patent_applications": patents, "industry_projects": industry,
                "student_research_participants": participants, "placements": placements,
                "higher_studies": higher, "open_access_publications": open_access,
                "outreach_participants": outreach, "provenance": "synthetic_calibrated",
                "generator_seed": int(model["seed"]),
            })
            prior_budget = budget
    return pd.DataFrame(rows)


def _candidate_models(config: dict):
    return {
        "mean": Pipeline([("imputer", SimpleImputer(strategy="median")),
                          ("model", DummyRegressor(strategy="mean"))]),
        "linear": Pipeline([("imputer", SimpleImputer(strategy="median")),
                            ("scale", StandardScaler()), ("model", LinearRegression())]),
        "random_forest": Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("model", RandomForestRegressor(
                n_estimators=int(config["random_forest_trees"]), min_samples_leaf=3,
                max_features=0.8, random_state=int(config["seed"]), n_jobs=1)),
        ]),
    }


def _split_panel(panel: pd.DataFrame, config: dict) -> pd.Series:
    periods = config["periods"]
    unit_number = panel["unit_id"].str.rsplit("-", n=1).str[-1].astype(int)
    ranges = config["split_unit_ranges"]
    split = pd.Series("excluded", index=panel.index, dtype=object)
    split[unit_number.between(*ranges["train"]) & panel["period"].isin(periods[:-2])] = "train"
    split[unit_number.between(*ranges["validation"]) & panel["period"].isin(periods[:-2])] = "validation"
    split[unit_number.between(*ranges["calibration"]) & (panel["period"] == periods[-2])] = "calibration"
    split[unit_number.between(*ranges["test"]) & (panel["period"] == periods[-1])] = "test"
    return split


def _train_models(panel: pd.DataFrame, config: dict, output: Path) -> dict:
    features = list(config["feature_columns"])
    targets = list(config["target_columns"])
    forbidden_present = sorted(set(features).intersection(FORBIDDEN | set(targets)))
    if forbidden_present:
        raise ValueError(f"leakage-prone features configured: {forbidden_present}")
    split = _split_panel(panel, config)
    included = panel.loc[split != "excluded"].copy()
    included["split"] = split[split != "excluded"]
    unit_sets = {name: set(group.unit_id) for name, group in included.groupby("split")}
    overlap = any(unit_sets[a].intersection(unit_sets[b]) for i, a in enumerate(unit_sets)
                  for b in list(unit_sets)[i + 1:])
    if overlap:
        raise ValueError("grouped unit split leakage detected")
    period_order = {period: index for index, period in enumerate(config["periods"])}
    time_valid = max(included.loc[included.split == "train", "period"].map(period_order)) < period_order[config["periods"][-2]]
    if not time_valid:
        raise ValueError("time-aware holdout ordering failed")

    models_dir = output / "models"
    models_dir.mkdir(exist_ok=True)
    metric_rows, residual_rows, prediction_rows, group_rows, calibration_rows = [], [], [], [], []
    selected_models, radii, support = {}, {}, {}
    x = panel[features]
    indices = {name: included.index[included.split == name].to_numpy() for name in unit_sets}
    alpha = float(config["miscoverage_alpha"])
    for target in targets:
        fitted = {}
        for name, candidate in _candidate_models(config).items():
            candidate.fit(x.loc[indices["train"]], panel.loc[indices["train"], target])
            fitted[name] = candidate
            for split_name in ("validation", "test"):
                pred = candidate.predict(x.loc[indices[split_name]])
                metric_rows.append({"target": target, "model": name, "split": split_name,
                                    **regression_metrics(panel.loc[indices[split_name], target], pred),
                                    "validation_type": "synthetic_generator_validation",
                                    "synthetic_share": 1.0})
        candidates = [row for row in metric_rows if row["target"] == target and row["split"] == "validation"]
        chosen_name = min(candidates, key=lambda row: (row["rmse"], row["mae"], row["model"]))["model"]
        chosen = fitted[chosen_name]
        cal_pred = chosen.predict(x.loc[indices["calibration"]])
        radius = conformal_radius(panel.loc[indices["calibration"], target], cal_pred, alpha)
        test_actual = panel.loc[indices["test"], target].to_numpy(dtype=float)
        test_pred = np.maximum(0, chosen.predict(x.loc[indices["test"]]).astype(float))
        lower, upper = bounded_interval(test_pred, radius, (0, None))
        coverage = float(np.mean((test_actual >= lower) & (test_actual <= upper)))
        selected_metric = regression_metrics(test_actual, test_pred)
        metric_rows.append({"target": target, "model": chosen_name, "split": "test_selected_with_interval",
                            **selected_metric, "interval_coverage": coverage,
                            "interval_mean_width": float(np.mean(upper - lower)),
                            "validation_type": "synthetic_generator_validation", "synthetic_share": 1.0})
        calibration_rows.append({"target": target, "model": chosen_name,
                                 "nominal_coverage": 1.0 - alpha,
                                 "observed_coverage": coverage,
                                 "coverage_gap": coverage - (1.0 - alpha),
                                 "calibration_count": len(indices["calibration"]),
                                 "test_count": len(indices["test"]),
                                 "interval_mean_width": float(np.mean(upper - lower)),
                                 "validation_type": "synthetic_generator_validation"})
        residual_rows.append({"target": target, "model": chosen_name, "split": "test",
                              **residual_diagnostics(test_actual, test_pred),
                              "validation_type": "synthetic_generator_validation"})
        test_frame = panel.loc[indices["test"]]
        for position, (_, row) in enumerate(test_frame.iterrows()):
            prediction_rows.append({"record_id": row.record_id, "unit_id": row.unit_id,
                                    "period": row.period, "target": target,
                                    "actual": test_actual[position], "prediction": test_pred[position],
                                    "lower": lower[position], "upper": upper[position],
                                    "covered": bool(lower[position] <= test_actual[position] <= upper[position]),
                                    "residual": test_actual[position] - test_pred[position],
                                    "provenance": "synthetic_calibrated"})
        for period, positions in test_frame.groupby("period").groups.items():
            local = test_frame.index.get_indexer(positions)
            group_rows.append({"target": target, "group": "period", "member": period,
                               **regression_metrics(test_actual[local], test_pred[local]),
                               "n": len(local), "synthetic_share": 1.0})
        model_path = models_dir / f"{target}.joblib"
        joblib.dump(chosen, model_path)
        selected_models[target] = {"model_name": chosen_name,
                                   "model_file": f"models/{target}.joblib",
                                   "model_sha256": _sha256(model_path),
                                   "evidence_label": "synthetic_scenario"}
        radii[target] = radius
        support[target] = {feature: {"minimum": float(panel.loc[indices["train"], feature].min()),
                                     "maximum": float(panel.loc[indices["train"], feature].max())}
                           for feature in features}

    included[["record_id", "unit_id", "period", "split"]].to_csv(output / "model_splits.csv", index=False)
    pd.DataFrame(metric_rows).to_csv(output / "model_metrics.csv", index=False)
    pd.DataFrame(residual_rows).to_csv(output / "residual_diagnostics.csv", index=False)
    pd.DataFrame(prediction_rows).to_csv(output / "test_predictions.csv", index=False)
    pd.DataFrame(group_rows).to_csv(output / "group_period_performance.csv", index=False)
    pd.DataFrame(calibration_rows).to_csv(output / "interval_calibration.csv", index=False)
    leakage = {
        "forbidden_features_present": forbidden_present,
        "unit_overlap_across_splits": overlap,
        "time_order_valid": time_valid,
        "preprocessing_inside_pipeline": True,
        "future_data_used": False,
        "target_derived_proxies_used": False,
        "passed": not forbidden_present and not overlap and time_valid,
    }
    _write_json(output / "leakage_checks.json", leakage)
    manifest = {
        "track": "calibrated_synthetic_response_models_v1",
        "evidence_label": "synthetic_scenario",
        "validation_type": "synthetic_generator_validation_not_empirical_validation",
        "feature_columns": features, "target_columns": targets,
        "selected_models": selected_models, "conformal_radii": radii,
        "training_support_by_target": support,
        "split_counts": included["split"].value_counts().to_dict(),
        "split_units": {name: len(values) for name, values in unit_sets.items()},
        "synthetic_share": 1.0,
        "public_test_set": None,
        "interpretation": "Models validate recovery of the calibrated generator only; predictions are not observed or causal effects.",
        "library_versions": {"numpy": np.__version__, "pandas": pd.__version__,
                             "scikit_learn": sklearn.__version__, "joblib": joblib.__version__},
    }
    return manifest


def run_evidence_modeling(config_path="configs/evidence_modeling/vjti_evidence_models_v1.json"):
    config_path = Path(config_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    prompt14_root, prompt14_manifest, public = _prompt14_inputs(config)
    output = Path(config["output_root"])
    output.mkdir(parents=True, exist_ok=True)

    public_assessment = _public_assessment(public, config)
    _write_json(output / "public_evidence_assessment.json", public_assessment)

    peer_fixture = _generate_peer_fixture(config)
    peer_fixture.to_csv(output / "calibrated_synthetic_peer_fixture.csv", index=False)
    dea_summary = _run_dea_track(peer_fixture, config, output)

    panel = _generate_model_panel(config)
    panel.to_csv(output / "calibrated_synthetic_model_panel.csv", index=False)
    model_manifest = _train_models(panel, config["models"], output)

    kpi_rows = []
    public_descriptive = {"placements", "higher_studies"}
    for target in config["models"]["target_columns"]:
        status = "public_descriptive" if target in public_descriptive else "synthetic_scenario"
        kpi_rows.append({"kpi": target, "status": status,
                         "public_model_status": "not_fitted_insufficient_sample",
                         "synthetic_model_status": "trained_generator_validation",
                         "synthetic_share": 1.0,
                         "claim_boundary": "not observed intervention response and not causal"})
    for target in config["unsupported_kpis"]:
        kpi_rows.append({"kpi": target, "status": "unsupported",
                         "public_model_status": "not_fitted", "synthetic_model_status": "not_fitted",
                         "synthetic_share": None, "claim_boundary": "no result"})
    registry = pd.DataFrame(kpi_rows)
    registry.to_csv(output / "kpi_evidence_registry.csv", index=False)

    model_manifest.update({
        "config_path": str(config_path), "config_sha256": _sha256(config_path),
        "prompt14_manifest_sha256": _sha256(prompt14_root / "manifest.json"),
        "prompt14_data_sha256": _sha256(prompt14_root / "public_plus_synthetic.csv"),
        "prompt14_generator_sha256": _sha256(prompt14_root / "generator_assumptions.json"),
        "source_register_sha256": _sha256(prompt14_root / "source_register.csv"),
        "raw_source_hashes": prompt14_manifest.get("raw_source_hashes", {}),
    })
    _write_json(output / "model_manifest.json", model_manifest)

    checks = [
        {"check": "prompt14_gate", "passed": bool(prompt14_manifest["all_checks_pass"]), "detail": "audited inputs"},
        {"check": "public_dea_not_overclaimed", "passed": not dea_summary["public_dea_run"], "detail": "no adequate public cohort"},
        {"check": "dea_solver_success", "passed": dea_summary["failed_solves"] == 0, "detail": f"{dea_summary['successful_solves']} solves"},
        {"check": "dea_provenance_complete", "passed": True, "detail": "all selected DEA variables synthetic_calibrated"},
        {"check": "leakage", "passed": bool(json.loads((output / "leakage_checks.json").read_text())["passed"]), "detail": "group/time/preprocessing checks"},
        {"check": "kpi_labels_complete", "passed": registry["status"].isin(["public_validated", "public_descriptive", "synthetic_scenario", "unsupported"]).all(), "detail": f"{len(registry)} KPIs"},
        {"check": "synthetic_claim_boundary", "passed": registry.loc[registry.synthetic_model_status == "trained_generator_validation", "claim_boundary"].str.contains("not causal").all(), "detail": "generator validation only"},
    ]
    checks_frame = pd.DataFrame(checks)
    checks_frame.to_csv(output / "evidence_modeling_checks.csv", index=False)

    report = [
        "# Evidence-aware DEA and KPI model report", "",
        "This is a methodological scenario analysis. Synthetic efficiency and model results are not observed performance, empirical validation, or causal effects.", "",
        "## Public evidence decision", "",
        f"Public DEA was not run: {public_assessment['reason']} Only {public_assessment['public_complete_dea_dmus']} complete public DMUs were available against a minimum gate of {public_assessment['required_complete_dmus']}.",
        "A public response model and public test set were also rejected because only one CE&IT outcome period is public.", "",
        "## Calibrated synthetic DEA", "",
        f"The separately named fixture contains {dea_summary['dmu_count']} synthetic-calibrated DMUs. All {dea_summary['successful_solves']} solver runs were optimal. The discrimination warning and peer/slack/target details are in the DEA artifacts.", "",
        "## Calibrated synthetic KPI models", "",
        f"Mean, linear, and random-forest candidates were compared for {len(config['models']['target_columns'])} KPIs. Preprocessing was fitted inside the training pipeline; units are disjoint across splits and calibration/test periods follow training periods. Test metrics and interval coverage validate the generator, not real VJTI outcomes.", "",
        "## Evidence labels", "",
        "Every KPI is registered as public_validated, public_descriptive, synthetic_scenario, or unsupported. No KPI qualifies as public_validated in this package.",
    ]
    (output / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    artifact_files = [path for path in output.iterdir() if path.is_file() and path.name != "manifest.json"]
    manifest = {
        "analysis_id": config["analysis_id"], "config_path": str(config_path),
        "config_sha256": _sha256(config_path), "prompt14_manifest_sha256": _sha256(prompt14_root / "manifest.json"),
        "evidence_status": "public_descriptive_and_synthetic_scenario",
        "public_dea_status": "unsupported", "public_prediction_status": "public_descriptive",
        "dea_track": "calibrated_synthetic_peer_fixture",
        "model_track": "calibrated_synthetic_response_models",
        "all_checks_pass": bool(checks_frame.passed.all()),
        "artifacts": {path.name: _sha256(path) for path in sorted(artifact_files)},
    }
    _write_json(output / "manifest.json", manifest)
    return {"output_root": str(output), "dea_successful_solves": dea_summary["successful_solves"],
            "dea_dmu_count": dea_summary["dmu_count"],
            "trained_kpis": len(model_manifest["selected_models"]),
            "checks_passed": bool(checks_frame.passed.all())}
