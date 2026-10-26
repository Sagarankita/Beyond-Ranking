"""Independent Prompt 18 audit for the VJTI public-plus-synthetic workflow."""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from department_optimizer.public_allocation.problem import FAMILIES, VJTIPublicAllocationProblem
from department_optimizer.public_experiments import build_report_from_artifacts


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def independent_hypervolume(points, reference):
    """Inclusion-exclusion rectangle union, independent of benchmark.metrics."""
    values = np.asarray(points, dtype=float)
    reference = np.asarray(reference, dtype=float)
    values = values[np.all(values < reference, axis=1)] if values.size else np.empty((0, len(reference)))
    total = 0.0
    for size in range(1, len(values) + 1):
        sign = 1.0 if size % 2 else -1.0
        for indexes in itertools.combinations(range(len(values)), size):
            lower = np.max(values[list(indexes)], axis=0)
            total += sign * float(np.prod(np.maximum(reference - lower, 0.0)))
    return total


def independent_igd(points, reference_front):
    values, reference = np.asarray(points, float), np.asarray(reference_front, float)
    if not len(values) or not len(reference):
        return float("nan")
    return float(np.sqrt(np.sum((reference[:, None, :] - values[None, :, :]) ** 2, axis=2)).min(axis=1).mean())


class Audit:
    def __init__(self):
        self.rows = []

    def add(self, check, category, status, evidence, detail=""):
        self.rows.append({"check": check, "category": category, "status": status,
                          "evidence": evidence, "detail": detail})

    def check(self, condition, check, category, evidence, failure):
        self.add(check, category, "pass" if condition else "fail", evidence,
                 "" if condition else failure)


def _verify_named_hashes(root, mapping):
    errors = []
    for name, expected in mapping.items():
        path = root / name
        if not path.is_file():
            errors.append(f"missing:{name}")
        elif _sha256(path) != expected:
            errors.append(f"hash:{name}")
    return errors


def _clean_reproduction(repo, config, output, audit):
    evidence = {"command": [], "returncode": None, "stdout": "", "stderr": ""}
    with tempfile.TemporaryDirectory(prefix="vjti-public-audit-") as temporary:
        clean = Path(temporary)
        shutil.copytree(repo / "department_optimizer", clean / "department_optimizer")
        shutil.copytree(repo / "libRION", clean / "libRION")
        (clean / "configs/public_allocation").mkdir(parents=True)
        shutil.copy2(repo / config["allocation_config"], clean / config["allocation_config"])
        model_relative = Path(config["evidence_root"])
        shutil.copytree(repo / model_relative, clean / model_relative)
        arguments = ["public_reproduce", "--config", config["allocation_config"],
                     "--model-root", config["evidence_root"], "--output", "reproduction",
                     "--seed", str(config["reproduction_seed"]),
                     "--evaluations", str(config["reproduction_evaluations"])]
        dependencies = [str(Path(np.__file__).resolve().parent.parent)]
        bootstrap = ("import runpy,sys;sys.path[:0]=" + repr([str(clean), *dependencies])
                     + ";sys.argv=" + repr(arguments)
                     + ";runpy.run_module('department_optimizer.audit.public_reproduce',run_name='__main__')")
        command = [sys.executable, "-c", bootstrap]
        result = subprocess.run(command, cwd=clean, capture_output=True,
                                text=True, check=False)
        evidence.update(command=command, returncode=result.returncode,
                        stdout=result.stdout, stderr=result.stderr)
        reproduced = clean / "reproduction"
        reproduction_output = output / "clean_reproduction"
        if result.returncode == 0 and reproduced.is_dir():
            shutil.copytree(reproduced, reproduction_output, dirs_exist_ok=True)
            evidence["copied_source_only"] = ["department_optimizer", "libRION", config["allocation_config"], config["evidence_root"]]
            audit.check(True, "clean_small_reproduction", "reproduction", str(reproduction_output), "")
        else:
            audit.check(False, "clean_small_reproduction", "reproduction", str(clean), result.stderr or result.stdout)
    (output / "reproduction_evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")


def _independent_reproduction_checks(repo, config, output, audit):
    root = output / "clean_reproduction"
    if not root.is_dir():
        return
    allocation = json.loads((repo / config["allocation_config"]).read_text(encoding="utf-8"))
    saved = json.loads((root / "baseline_evaluation.json").read_text(encoding="utf-8"))
    model_manifest = json.loads((repo / config["evidence_root"] / "model_manifest.json").read_text())
    frame = pd.DataFrame([saved["model_features"]], columns=model_manifest["feature_columns"])
    target = "q1_publications"
    model = joblib.load(repo / config["evidence_root"] / model_manifest["selected_models"][target]["model_file"])
    direct_prediction = max(0.0, float(model.predict(frame)[0]))
    prediction_ok = np.isclose(direct_prediction, saved["raw_kpis"][target])
    pd.DataFrame([{"target": target, "direct_model_prediction": direct_prediction,
                   "saved_evaluator_prediction": saved["raw_kpis"][target],
                   "absolute_difference": abs(direct_prediction - saved["raw_kpis"][target])}]).to_csv(
        output / "independent_prediction_check.csv", index=False)
    audit.check(prediction_ok, "selected_prediction_recomputed", "reproduction",
                "independent_prediction_check.csv", "direct model and evaluator prediction differ")

    candidate, intervals = saved["repaired"], saved["intervals"]
    manual = {}
    for variable in allocation["decision_variables"]:
        name, value = variable["name"], candidate[variable["name"]]
        manual[f"bounds__{name}"] = max(variable["lower"] - value, value - variable["upper"], 0.0)
        manual[f"increment__{name}"] = abs((value - variable["lower"]) / variable["increment"] - round((value - variable["lower"]) / variable["increment"])) * variable["increment"]
        if variable["type"] == "integer":
            manual[f"integrality__{name}"] = abs(value - round(value))
    manual["budget"] = max(0.0, saved["total_cost"] - allocation["budget_limit"])
    available = allocation["fixed_context"]["faculty_total"] - allocation["service_commitments"]["minimum_teaching_fte"]
    manual["faculty_effort_conservation"] = max(0.0, sum(candidate[name] for name in allocation["effort_decisions"]) - available)
    for name, minimum in (("student_support_faculty_effort", allocation["service_commitments"]["minimum_student_support_fte"]),
                          ("service_faculty_effort", allocation["service_commitments"]["minimum_service_fte"])):
        manual[f"service_floor__{name}"] = max(0.0, minimum - candidate[name])
    for dependency in allocation["dependencies"]:
        required = candidate[dependency["count_variable"]] * dependency["minimum_funding_per_unit"]
        manual[f"dependency__{dependency['name']}"] = max(0.0, required - candidate[dependency["funding_variable"]])
    for service in allocation["conservative_kpi_services"]:
        manual[f"service_kpi__{service['kpi']}"] = max(0.0, service["minimum_lower_bound"] - intervals[service["kpi"]]["lower"])
    rows = [{"constraint": name, "independent_residual": value,
             "saved_residual": saved["constraint_residuals"][name],
             "absolute_difference": abs(value - saved["constraint_residuals"][name])} for name, value in manual.items()]
    pd.DataFrame(rows).to_csv(output / "independent_constraint_check.csv", index=False)
    audit.check(all(np.isclose(row["independent_residual"], row["saved_residual"], atol=1e-10) for row in rows),
                "constraint_residuals_recomputed", "reproduction", "independent_constraint_check.csv",
                "one or more independently computed residuals differ")

    columns = [f"objective__{name}" for name in FAMILIES]
    reference = pd.read_csv(root / "pooled_reference_front.csv").to_numpy(float)
    recorded = pd.read_csv(root / "metrics.csv")
    metric_rows, pareto_errors = [], []
    for item in recorded.itertuples():
        archive = pd.read_csv(root / "runs" / item.algorithm / "archive.csv")
        points = archive[columns].to_numpy(float) if len(archive) else np.empty((0, 4))
        for first in range(len(points)):
            for second in range(len(points)):
                if first != second and np.all(points[first] <= points[second]) and np.any(points[first] < points[second]):
                    pareto_errors.append(f"{item.algorithm}:{second}")
        hv, distance = independent_hypervolume(points, np.full(4, 0.05)), independent_igd(points, reference)
        metric_rows.append({"algorithm": item.algorithm, "independent_hypervolume": hv,
                            "recorded_hypervolume": item.hypervolume, "independent_igd": distance,
                            "recorded_igd": item.igd})
    pd.DataFrame(metric_rows).to_csv(output / "independent_reproduction_metrics.csv", index=False)
    audit.check(not pareto_errors, "pareto_status_recomputed", "reproduction",
                "clean_reproduction/runs/*/archive.csv", f"dominated archive rows: {pareto_errors}")
    metrics_ok = all(np.isclose(row["independent_hypervolume"], row["recorded_hypervolume"], atol=1e-12)
                     and np.isclose(row["independent_igd"], row["recorded_igd"], atol=1e-12, equal_nan=True)
                     for row in metric_rows)
    audit.check(metrics_ok, "hypervolume_igd_recomputed", "reproduction",
                "independent_reproduction_metrics.csv", "independent metric mismatch")


def _matrix():
    return pd.DataFrame([
        ["Public-source acquisition and immutable snapshots", "implemented", "publicly_validated", "Official source identities and file hashes verified; values remain descriptive."],
        ["CE&IT capacity, faculty roster, placement and higher-study facts", "implemented", "public_descriptive", "Observed/derived public fields only; no causal interpretation."],
        ["Calibrated missing-field generator", "implemented", "synthetic_scenario", "Fixed seeds and versioned assumptions; not observed VJTI data."],
        ["Resource-to-KPI models and intervals", "implemented", "synthetic_scenario", "Generator validation only; no public test set."],
        ["VRS DEA peer fixture", "implemented", "synthetic_scenario", "Calibrated synthetic peers; not public institutional efficiency."],
        ["Four-family allocation evaluator", "implemented", "synthetic_scenario", "Mixed public context and synthetic response functions."],
        ["Repeated algorithm and robustness experiments", "implemented", "synthetic_scenario", "18/18 VJTI-calibrated runs plus legacy 25-seed software benchmark."],
        ["Public-only placement sensitivity", "implemented", "public_descriptive", "Rates only; no allocation effect."],
        ["Network DEA", "evidence_gate_applied", "deferred", "No observed comparable stage links."],
        ["Multi-period allocation", "evidence_gate_applied", "deferred", "No repeated observed department-period decisions and lags."],
        ["Gaussian-process extension", "not_run", "optional", "Optional and not needed for required completion."],
        ["Saved-artifact dashboard", "not_run", "optional", "Optional; static report remains reproducible."],
        ["Causal allocation effects", "not_claimed", "unsupported", "No intervention design or causal identification."],
        ["Empirically validated VJTI optimization", "not_claimed", "unsupported", "Department allocations and most outcomes are not publicly observed longitudinally."],
    ], columns=["work_item", "implementation_status", "evidence_status", "boundary"])


def _report(output, checks, matrix, complete):
    counts = checks.status.value_counts().to_dict()
    lines = ["# Final VJTI public-plus-synthetic completion audit", "",
             f"Result: **{counts.get('pass', 0)} passed, {counts.get('fail', 0)} failed, {counts.get('gap', 0)} explicit gaps.**", "",
             ("All required workflow gates pass. The project is complete as a **VJTI-calibrated methodological study**, not as an empirically validated or causal allocation study."
              if complete else "One or more required workflow gates failed; completion is not claimed."), "",
             "## Audit checks", "", "| Check | Category | Status | Evidence | Detail |",
             "|---|---|---|---|---|"]
    for row in checks.itertuples():
        lines.append(f"| {row.check} | {row.category} | {row.status} | {str(row.evidence).replace('|', '/')} | {str(row.detail).replace('|', '/')} |")
    lines += ["", "## Implementation and evidence matrix", "",
              "| Work item | Implementation | Evidence | Boundary |", "|---|---|---|---|"]
    for row in matrix.itertuples():
        lines.append(f"| {row.work_item} | {row.implementation_status} | {row.evidence_status} | {row.boundary} |")
    lines += ["", "## Reproduction", "",
              "The clean reproduction copied source code, the frozen allocation configuration, and the versioned model bundle into a temporary workspace without prior result artifacts. It ran NSGA-II and random search with seed 18001 and eight matched candidate evaluations each. Saved outputs are under `clean_reproduction/`.", "",
              "Independent calculations are in `independent_prediction_check.csv`, `independent_constraint_check.csv`, and `independent_reproduction_metrics.csv`.", "",
              "## Remaining gaps", "",
              "Network DEA and multi-period planning remain deferred at their evidence gates. The optional Gaussian-process comparison and dashboard were not undertaken. Causal effects and empirical VJTI optimization remain unsupported. None is represented as completed empirical work.", "",
              "## Reproduction commands", "", "```bash",
              "python -m department_optimizer.public_data.run --config configs/data/vjti_public_plus_synthetic_v1.json",
              "python -m department_optimizer.evidence_modeling.run --config configs/evidence_modeling/vjti_evidence_models_v1.json",
              "python -m department_optimizer.public_allocation.run --config configs/public_allocation/vjti_four_family_v1.json",
              "python -m department_optimizer.public_experiments.run --config configs/public_experiments/vjti_experiments_v1.json",
              "python -m department_optimizer.audit.public_run --config configs/audit/vjti_public_completion_v1.json",
              "```", ""]
    (output / "audit_report.md").write_text("\n".join(lines), encoding="utf-8")


def run_public_audit(config_path, output_root=None):
    config_path = Path(config_path).resolve()
    repo = config_path.parents[2]
    config = json.loads(config_path.read_text(encoding="utf-8"))
    output = Path(output_root).resolve() if output_root else repo / config["output_root"]
    output.mkdir(parents=True, exist_ok=True)
    audit = Audit()
    public_root, evidence_root = repo / config["public_root"], repo / config["evidence_root"]
    allocation_root, experiment_root = repo / config["allocation_root"], repo / config["experiment_root"]

    public_manifest = json.loads((public_root / "manifest.json").read_text())
    errors = _verify_named_hashes(public_root, public_manifest["generated_files"])
    source_register = pd.read_csv(public_root / "source_register.csv")
    for source in source_register[source_register.snapshot_exists.astype(bool)].itertuples():
        path = repo / source.snapshot_path
        if not path.is_file() or _sha256(path) != source.sha256:
            errors.append(f"raw:{source.source_id}")
    audit.check(not errors, "public_source_and_generated_hash_chain", "provenance",
                "public manifest + source register", f"hash errors: {errors}")

    evidence_manifest = json.loads((evidence_root / "manifest.json").read_text())
    model_manifest = json.loads((evidence_root / "model_manifest.json").read_text())
    errors = _verify_named_hashes(evidence_root, evidence_manifest["artifacts"])
    model_errors = [target for target, item in model_manifest["selected_models"].items()
                    if _sha256(evidence_root / item["model_file"]) != item["model_sha256"]]
    chain_ok = (evidence_manifest["prompt14_manifest_sha256"] == _sha256(public_root / "manifest.json")
                and model_manifest["prompt14_data_sha256"] == _sha256(public_root / "public_plus_synthetic.csv")
                and model_manifest["prompt14_generator_sha256"] == _sha256(public_root / "generator_assumptions.json"))
    audit.check(chain_ok and not errors and not model_errors, "generator_model_hash_chain", "provenance",
                "Prompt 14 -> Prompt 15 manifests and model files", f"artifact={errors}; model={model_errors}")

    leakage = json.loads((evidence_root / "leakage_checks.json").read_text())
    splits = pd.read_csv(evidence_root / "model_splits.csv")
    split_sets = {name: set(frame.unit_id) for name, frame in splits.groupby("split")}
    disjoint = all(split_sets[a].isdisjoint(split_sets[b]) for a, b in itertools.combinations(split_sets, 2))
    audit.check(leakage["passed"] and disjoint and not leakage["future_data_used"],
                "split_isolation_and_leakage", "model", "leakage_checks.json + model_splits.csv",
                "split overlap, future data, or leakage check failure")

    metrics = pd.read_csv(evidence_root / "model_metrics.csv")
    selected = metrics[metrics.split == "test_selected_with_interval"]
    validation_ok = (set(selected.target) == set(model_manifest["target_columns"])
                     and selected.interval_coverage.notna().all() and (selected.synthetic_share == 1.0).all())
    audit.check(validation_ok and model_manifest["public_test_set"] is None,
                "model_validation_and_coverage", "model", "model_metrics.csv + model_manifest.json",
                "target, interval, synthetic-share, or public-test disclosure mismatch")

    dea = json.loads((evidence_root / "dea_summary.json").read_text())
    dea_provenance = pd.read_csv(evidence_root / "dea_variable_provenance.csv")
    dea_ok = ("variable-returns-to-scale" in dea["model"] and dea["successful_solves"] == dea["dmu_count"]
              and not dea["public_dea_run"] and (dea_provenance.synthetic_calibrated_fraction == 1.0).all())
    audit.check(dea_ok, "dea_formulation_and_evidence", "dea", "dea_summary.json + dea_variable_provenance.csv",
                "DEA formulation, solve count, or synthetic evidence label mismatch")

    allocation_manifest = json.loads((allocation_root / "manifest.json").read_text())
    allocation_config = json.loads((repo / config["allocation_config"]).read_text())
    allocation_checks = pd.read_csv(allocation_root / "allocation_checks.csv")
    chain_ok = (allocation_manifest["prompt14_manifest_sha256"] == _sha256(public_root / "manifest.json")
                and allocation_manifest["prompt15_manifest_sha256"] == _sha256(evidence_root / "manifest.json")
                and allocation_manifest["prompt15_model_manifest_sha256"] == _sha256(evidence_root / "model_manifest.json"))
    audit.check(chain_ok and allocation_checks.passed.astype(bool).all(),
                "allocation_chain_units_feasibility", "allocation", "allocation manifest + checks",
                "upstream chain, units, integrality, feasibility, or accounting failed")
    problem = VJTIPublicAllocationProblem(allocation_config, evidence_root)
    baseline = problem.evaluate_fixed(allocation_config["reference_allocation"])
    directions_ok = all(np.isclose(baseline.objective_scores[name], -baseline.objective_benefits[name]) for name in FAMILIES)
    audit.check(directions_ok and set(baseline.objective_evidence.values()) == {"synthetic_scenario"},
                "objective_direction_and_evidence", "allocation", "independent baseline evaluation",
                "objective sign or evidence label mismatch")

    experiment_manifest = json.loads((experiment_root / "experiment_manifest.json").read_text())
    errors = _verify_named_hashes(experiment_root, experiment_manifest["artifact_hashes"])
    input_chain = (experiment_manifest["public_manifest_sha256"] == _sha256(public_root / "manifest.json")
                   and experiment_manifest["model_manifest_sha256"] == _sha256(evidence_root / "model_manifest.json")
                   and experiment_manifest["allocation_config_sha256"] == _sha256(repo / config["allocation_config"]))
    audit.check(input_chain and not errors, "experiment_and_report_hash_chain", "experiments",
                "experiment_manifest.json", f"hash errors: {errors}")
    experiment_config = json.loads((repo / config["experiment_config"]).read_text())
    statuses = []
    accounting_ok = True
    for status_path in sorted((experiment_root / "runs/comparison").glob("*/seed_*/status.json")):
        status = json.loads(status_path.read_text())
        accounting = json.loads((status_path.parent / "accounting.json").read_text())
        statuses.append(status)
        accounting_ok &= accounting["candidate_evaluations_total"] == experiment_config["matched_candidate_evaluations"]
    expected = len(experiment_config["algorithms"]) * len(experiment_config["comparison_seeds"])
    audit.check(len(statuses) == expected and all(x["status"] == "complete" for x in statuses) and accounting_ok,
                "matched_budgets_seed_and_algorithm_counts", "experiments", f"{len(statuses)}/{expected} run records",
                "run count, completion, or matched accounting failed")
    scenarios = experiment_config["scenarios"]
    budgets = {item["budget_limit"] for item in scenarios if item["name"].startswith("budget_")}
    allocations = pd.read_csv(experiment_root / "strategy_allocations.csv")
    scenario_ok = budgets == {30_000_000, 36_000_000, 42_000_000} and all(
        {"held_fixed", "scenario_reoptimization"}.issubset(set(allocations[allocations.scenario == item["name"]].strategy_type))
        for item in scenarios)
    audit.check(scenario_ok, "scenario_and_fixed_reoptimized_coverage", "experiments",
                "experiment config + strategy_allocations.csv", "budget levels or assessment modes missing")

    log = pd.read_csv(experiment_root / "strategy_selection_log.csv").fillna("")
    objective_rows = pd.read_csv(experiment_root / "strategy_objectives.csv")
    recommendations = allocations[allocations.strategy_type.isin(["policy_selection", "scenario_reoptimization"])]
    strategy_ok = recommendations.feasible.astype(bool).all() and objective_rows.groupby("strategy_id").objective.nunique().eq(4).all()
    audit.check(strategy_ok and {"selected", "duplicate"}.issubset(set(log.result)),
                "strategy_rules_feasibility_and_duplicates", "reporting", "strategy artifacts",
                "strategy feasibility, coverage, or duplicate preservation failed")

    report_before = _sha256(experiment_root / "report.md")
    build_report_from_artifacts(experiment_root)
    report_after = _sha256(experiment_root / "report.md")
    audit.check(report_before == report_after, "report_artifact_only_reproduction", "reporting",
                "report.md regenerated from saved artifacts", "report changed during artifact-only regeneration")

    final_root = repo / config["final_synthetic_benchmark_root"]
    completion = json.loads((final_root / "completion.json").read_text())
    statistics = pd.read_csv(final_root / "statistical_tests.csv")
    stats_ok = (completion["complete_jobs"] == completion["configured_jobs"] == 150
                and completion["failed_jobs"] == 0 and (statistics.paired_runs == 25).all()
                and set(statistics.status).issubset({"performed", "all_paired_differences_zero"})
                and statistics.holm_adjusted_p_value.notna().all())
    audit.check(stats_ok, "final_benchmark_statistical_tests", "statistics",
                "25-seed completion + paired tests + Holm correction", "completion or statistical-test contract failed")

    extension = json.loads((repo / config["extension_assessment"]).read_text())["assessment"]
    gates_ok = all(extension[name]["status"] == "deferred_evidence_gap" and not extension[name]["implementation_performed"]
                   for name in ("network_dea", "multi_period_planning"))
    audit.check(gates_ok, "advanced_extension_evidence_gates", "scope", config["extension_assessment"],
                "Network DEA or multi-period work exceeded its evidence gate")

    _clean_reproduction(repo, config, output, audit)
    _independent_reproduction_checks(repo, config, output, audit)
    test_paths = [str(repo), str(Path(np.__file__).resolve().parent.parent)]
    test_bootstrap = ("import sys,unittest;sys.path[:0]=" + repr(test_paths)
                      + ";s=unittest.defaultTestLoader.discover('tests');"
                      + "r=unittest.TextTestRunner(verbosity=1).run(s);raise SystemExit(not r.wasSuccessful())")
    tests = subprocess.run([sys.executable, "-c", test_bootstrap], cwd=repo,
                           capture_output=True, text=True, check=False)
    (output / "test_evidence.txt").write_text(tests.stdout + tests.stderr, encoding="utf-8")
    audit.check(tests.returncode == 0, "full_python_test_suite", "tests", "test_evidence.txt",
                (tests.stdout + tests.stderr)[-2000:])

    audit.add("network_dea_public_evidence", "gap", "gap", config["extension_assessment"],
              "deferred: no observed comparable stage links")
    audit.add("multi_period_public_evidence", "gap", "gap", config["extension_assessment"],
              "deferred: no observed longitudinal department decisions/outcomes")
    audit.add("causal_empirical_validation", "gap", "gap", "public_evidence_assessment.json",
              "unsupported: descriptive public fields and synthetic response models cannot identify causal effects")

    checks = pd.DataFrame(audit.rows)
    matrix = _matrix()
    checks.to_csv(output / "audit_checks.csv", index=False)
    matrix.to_csv(output / "implementation_evidence_matrix.csv", index=False)
    required_failures = checks[checks.status == "fail"]
    complete = required_failures.empty
    _report(output, checks, matrix, complete)
    manifest = {
        "audit_id": config["audit_id"], "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "config_sha256": _sha256(config_path), "required_checks_pass": complete,
        "completion_claim": "complete_vjti_calibrated_methodological_study" if complete else "incomplete",
        "empirical_validation_claim": False, "causal_claim": False,
        "passed": int((checks.status == "pass").sum()), "failed": int((checks.status == "fail").sum()),
        "gaps": int((checks.status == "gap").sum()), "python": platform.python_version(),
        "artifact_hashes": {path.name: _sha256(path) for path in output.iterdir()
                            if path.is_file() and path.name != "manifest.json"},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"output_root": str(output), "required_checks_pass": complete,
            "passed": manifest["passed"], "failed": manifest["failed"], "gaps": manifest["gaps"]}
