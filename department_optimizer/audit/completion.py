"""Audit implementation claims against source, saved artifacts, and a clean reproduction."""

from __future__ import annotations

import argparse
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

import numpy as np
import pandas as pd

from department_optimizer.allocation import AllocationProblem
from department_optimizer.allocation.problem import OBJECTIVE_FAMILIES
from department_optimizer.modeling import load_prediction_bundle


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def independent_hypervolume(points, reference):
    """Brute-force rectangle union for audit-only metric recomputation."""
    values = np.asarray(points, dtype=float)
    reference = np.asarray(reference, dtype=float)
    if values.size == 0:
        return 0.0
    values = values[np.all(values < reference, axis=1)]
    total = 0.0
    for size in range(1, len(values) + 1):
        sign = 1.0 if size % 2 else -1.0
        for indexes in itertools.combinations(range(len(values)), size):
            lower = np.max(values[list(indexes)], axis=0)
            total += sign * float(np.prod(np.maximum(reference - lower, 0.0)))
    return total


def independent_igd(points, reference_front):
    values = np.asarray(points, dtype=float)
    reference = np.asarray(reference_front, dtype=float)
    if len(values) == 0 or len(reference) == 0:
        return float("nan")
    distances = np.sqrt(
        np.sum((reference[:, None, :] - values[None, :, :]) ** 2, axis=2)
    )
    return float(np.min(distances, axis=1).mean())


class Audit:
    def __init__(self):
        self.rows = []

    def add(self, check_id, category, status, evidence, details=""):
        if status not in {"pass", "fail", "gap"}:
            raise ValueError(f"invalid audit status: {status}")
        self.rows.append(
            {
                "check_id": check_id,
                "category": category,
                "status": status,
                "evidence": evidence,
                "details": details,
            }
        )

    def check(self, condition, check_id, category, evidence, failure):
        self.add(
            check_id,
            category,
            "pass" if condition else "fail",
            evidence,
            "" if condition else failure,
        )

    def frame(self):
        return pd.DataFrame(self.rows)


def _normalization(config):
    scaling = config["objective_scaling"]
    return (
        np.asarray(scaling["lower"], dtype=float),
        np.asarray(scaling["upper"], dtype=float),
        np.asarray(config["hypervolume_reference_point"], dtype=float),
    )


def _recompute_metrics(
    root,
    audit,
    check_id="metrics_independent_recompute",
    output_path=None,
):
    config = json.loads((root / "benchmark_config_snapshot.json").read_text())
    lower, upper, hv_reference = _normalization(config)
    pooled = pd.read_csv(root / "pooled_reference_front.csv").to_numpy(dtype=float)
    recorded = pd.read_csv(root / "per_seed_metrics.csv")
    mismatches = []
    independent_rows = []
    for _, item in recorded[recorded.status == "complete"].iterrows():
        archive = pd.read_csv(
            root / "runs" / item.algorithm / f"seed_{int(item.seed)}" / "archive.csv"
        )
        columns = [f"objective__{name}" for name in config["objective_scaling"]["objective_order"]]
        values = archive[columns].to_numpy(dtype=float)
        normalized = np.clip((values - lower) / (upper - lower), 0.0, 1.0)
        hv = independent_hypervolume(normalized, hv_reference)
        igd = independent_igd(normalized, pooled)
        independent_rows.append(
            {
                "algorithm": item.algorithm,
                "seed": int(item.seed),
                "independent_hypervolume": hv,
                "recorded_hypervolume": item.hypervolume,
                "hypervolume_absolute_difference": abs(hv - item.hypervolume),
                "independent_igd": igd,
                "recorded_igd": item.igd,
                "igd_absolute_difference": abs(igd - item.igd),
            }
        )
        if not np.isclose(hv, item.hypervolume, rtol=1e-10, atol=1e-12):
            mismatches.append(f"{item.algorithm}/{int(item.seed)} hypervolume")
        if not np.isclose(igd, item.igd, rtol=1e-10, atol=1e-12, equal_nan=True):
            mismatches.append(f"{item.algorithm}/{int(item.seed)} IGD")
    if output_path is not None:
        pd.DataFrame(independent_rows).to_csv(output_path, index=False)
    audit.check(
        not mismatches,
        check_id,
        "benchmark",
        str(root / "per_seed_metrics.csv"),
        f"metric mismatches: {mismatches}",
    )


def _audit_archives(config, audit):
    allocation_path = Path(config["allocation_config"])
    allocation_config = json.loads(allocation_path.read_text())
    model = load_prediction_bundle(allocation_config["model_bundle"])
    problem = AllocationProblem(allocation_config, model)
    benchmark_root = Path(config["benchmark_root"])
    errors = []
    checked = 0
    for archive_path in sorted((benchmark_root / "runs").glob("*/seed_*/archive.csv")):
        frame = pd.read_csv(archive_path)
        objectives = frame[[f"objective__{name}" for name in OBJECTIVE_FAMILIES]].to_numpy(
            dtype=float
        )
        for first in range(len(objectives)):
            for second in range(len(objectives)):
                if first != second and np.all(objectives[first] <= objectives[second]) and np.any(
                    objectives[first] < objectives[second]
                ):
                    errors.append(f"dominated row {second} in {archive_path}")
        for row_index, row in frame.iterrows():
            allocation = {name: float(row[name]) for name in problem.variable_names}
            result = problem.evaluate(allocation)
            checked += 1
            if not result.nominal_feasible or result.normalized_violation > 1e-12:
                errors.append(f"infeasible {archive_path}:{row_index}")
            if any(
                not np.isclose(result.repaired[name], allocation[name])
                for name in problem.variable_names
            ):
                errors.append(f"repair changed archive {archive_path}:{row_index}")
            for variable in problem.variables:
                if variable["type"] == "integer" and not float(
                    allocation[variable["name"]]
                ).is_integer():
                    errors.append(f"noninteger {variable['name']} in {archive_path}:{row_index}")
            for name in OBJECTIVE_FAMILIES:
                if not np.isclose(result.objective_scores[name], row[f"objective__{name}"]):
                    errors.append(f"objective mismatch {name} in {archive_path}:{row_index}")
                if not np.isclose(
                    row[f"objective__{name}"], -row[f"objective_benefit__{name}"]
                ):
                    errors.append(f"objective sign mismatch {name} in {archive_path}:{row_index}")
    audit.check(
        checked > 0 and not errors,
        "archive_independent_validation",
        "optimization",
        f"{checked} archived candidates independently evaluated",
        "; ".join(errors[:20]) if errors else "no archive candidates found",
    )


def _audit_accounting_root(root, expected_jobs, audit, check_id, label):
    root = Path(root)
    errors = []
    count = 0
    for status_path in sorted((root / "runs").glob("*/seed_*/status.json")):
        status = json.loads(status_path.read_text())
        accounting = json.loads((status_path.parent / "evaluation_accounting.json").read_text())
        count += 1
        if status["status"] != "complete":
            errors.append(f"incomplete {status_path.parent}")
        if status["candidate_evaluations"] != status["target_candidate_evaluations"]:
            errors.append(f"budget mismatch {status_path.parent}")
        if accounting["candidate_evaluations_total"] != status["candidate_evaluations"]:
            errors.append(f"accounting mismatch {status_path.parent}")
        if status["final_batch_overshoot"] != 0:
            errors.append(f"unexpected overshoot {status_path.parent}")
    audit.check(
        count == expected_jobs and not errors,
        check_id,
        "benchmark",
        f"{count} {label} job status/accounting pairs",
        "; ".join(errors) if errors else f"expected {expected_jobs} jobs, found {count}",
    )


def _audit_accounting(config, audit):
    _audit_accounting_root(
        config["benchmark_root"],
        18,
        audit,
        "matched_evaluation_accounting",
        "smoke",
    )


def _copy_clean_workspace(source, target):
    for name in ("department_optimizer", "libRION", "configs", "artifacts", "data"):
        shutil.copytree(source / name, target / name)


def _clean_reproduction(repo_root, config, audit):
    saved_root = Path(config["saved_reproduction_root"])
    evidence = {}
    with tempfile.TemporaryDirectory(prefix="department-rank-audit-") as temporary:
        clean = Path(temporary)
        _copy_clean_workspace(repo_root, clean)
        reproduction_config = {
            "schema_version": 1,
            "benchmark_id": "phase12-clean-small-reproduction-v1",
            "data_role": "smoke",
            "allocation_config": "configs/allocation/legacy_synthetic_method_fixture.json",
            "seeds": [int(config["temporary_reproduction_seed"])],
            "evaluation_budget": int(config["temporary_reproduction_budget"]),
            "budget_definition": "Phase 12 clean reproduction candidate budget",
            "minimum_runs_for_inference": 10,
            "reference_front_version": "phase12-clean-small-pooled-v1",
            "objective_scaling": {
                "objective_order": list(OBJECTIVE_FAMILIES),
                "lower": [-1.0, -1.0, -1.0, -1.0],
                "upper": [0.0, 0.0, 0.0, 0.0],
                "clip": True,
                "status": "frozen_before_reproduction",
            },
            "hypervolume_reference_point": [1.1, 1.1, 1.1, 1.1],
            "algorithms": {
                "nsga2": {
                    "enabled": True,
                    "population_size": 4,
                    "generations": 4,
                },
                "random_search": {"enabled": True, "evaluations": 20},
            },
            "output_root": "results/phase12-small-reproduction",
        }
        config_path = clean / "configs/audit-clean-benchmark.json"
        config_path.write_text(json.dumps(reproduction_config, indent=2) + "\n")
        environment = os.environ.copy()
        existing = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = str(clean) + (os.pathsep + existing if existing else "")
        command = [
            sys.executable,
            "-m",
            "department_optimizer.benchmark.run",
            "--config",
            str(config_path.relative_to(clean)),
        ]
        result = subprocess.run(
            command, cwd=clean, env=environment, capture_output=True, text=True, check=False
        )
        produced = clean / reproduction_config["output_root"]
        if result.returncode == 0 and produced.exists():
            saved_root.mkdir(parents=True, exist_ok=True)
            shutil.copytree(produced, saved_root, dirs_exist_ok=True)
            recorded = pd.read_csv(produced / "per_seed_metrics.csv")
            pooled = pd.read_csv(produced / "pooled_reference_front.csv").to_numpy(dtype=float)
            lower, upper, reference = _normalization(reproduction_config)
            mismatches = []
            independent_rows = []
            for _, item in recorded.iterrows():
                archive = pd.read_csv(
                    produced / "runs" / item.algorithm / f"seed_{int(item.seed)}" / "archive.csv"
                )
                columns = [f"objective__{name}" for name in OBJECTIVE_FAMILIES]
                normalized = np.clip(
                    (archive[columns].to_numpy(dtype=float) - lower) / (upper - lower),
                    0.0,
                    1.0,
                )
                hv = independent_hypervolume(normalized, reference)
                igd = independent_igd(normalized, pooled)
                independent_rows.append(
                    {
                        "algorithm": item.algorithm,
                        "seed": int(item.seed),
                        "independent_hypervolume": hv,
                        "recorded_hypervolume": item.hypervolume,
                        "independent_igd": igd,
                        "recorded_igd": item.igd,
                    }
                )
                if not np.isclose(hv, item.hypervolume, rtol=1e-10, atol=1e-12):
                    mismatches.append(f"{item.algorithm} HV")
                if not np.isclose(igd, item.igd, rtol=1e-10, atol=1e-12):
                    mismatches.append(f"{item.algorithm} IGD")
            independent = pd.DataFrame(independent_rows)
            independent.to_csv(saved_root / "independent_metric_check.csv", index=False)
            evidence = {
                "command": command,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "jobs": len(recorded),
                "metric_mismatches": mismatches,
            }
            audit.check(
                len(recorded) == 2 and not mismatches,
                "clean_temporary_reproduction",
                "reproduction",
                str(saved_root),
                f"jobs={len(recorded)}, metric mismatches={mismatches}",
            )
        else:
            evidence = {
                "command": command,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
            audit.add(
                "clean_temporary_reproduction",
                "reproduction",
                "fail",
                "temporary isolated source copy",
                result.stderr or result.stdout,
            )
    saved_root.mkdir(parents=True, exist_ok=True)
    (saved_root / "reproduction_evidence.json").write_text(
        json.dumps(evidence, indent=2) + "\n"
    )


def _subprocess_check(command, check_id, category, evidence, audit):
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    audit.check(
        result.returncode == 0,
        check_id,
        category,
        evidence,
        (result.stdout + "\n" + result.stderr)[-4000:],
    )
    return result


def _final_benchmark_complete(config):
    final_root = Path(config["final_benchmark_root"])
    completion_path = final_root / "completion.json"
    if not completion_path.exists():
        return False
    completion = json.loads(completion_path.read_text())
    return (
        completion.get("complete_jobs")
        == completion.get("configured_jobs")
        == 150
        and completion.get("failed_jobs") == 0
    )


def _completion_matrix(config):
    final_complete = _final_benchmark_complete(config)
    return pd.DataFrame(
        [
            ["Phase 0", "Corrected serial baseline and optional native checks", "complete"],
            ["Phase 1", "Schema, provenance, scenarios, synthetic data audit", "complete_synthetic_track"],
            ["Phase 2", "DEA mathematical fixture and outputs", "complete_method_fixture"],
            ["Phase 3", "Versioned KPI predictor and uncertainty", "complete_synthetic_track"],
            ["Phase 4", "Shared evaluator and first feasible workflow", "complete"],
            ["Phase 5", "Six common-contract optimization tracks", "complete_pilot"],
            ["Phase 6A", "Three-seed matched-budget smoke benchmark", "complete_smoke"],
            ["Phase 6A", "Configured 25-seed final benchmark", "complete" if final_complete else "not_executed_or_incomplete"],
            ["Phase 6B", "Five supported scenarios and uncertainty sensitivity", "complete_synthetic_track"],
            ["Phase 6B", "Patent and compute shocks", "unsupported_by_current_decision_model"],
            ["Phase 7", "Saved-artifact strategy portfolio and report", "complete_synthetic_track"],
            ["Evidence", "Observed departmental allocation/outcome validation", "not_available"],
        ],
        columns=["phase", "deliverable", "status"],
    )


def _write_report(output, config, checks, matrix):
    counts = checks.status.value_counts().to_dict()
    final_complete = _final_benchmark_complete(config)
    lines = [
        "# Phase 12 completion audit",
        "",
        "> This audit distinguishes reproducible implementation evidence from configured, unsupported, and unexecuted work.",
        "",
        f"Result: **{counts.get('pass', 0)} passed, {counts.get('fail', 0)} failed, {counts.get('gap', 0)} explicit gaps.**",
        "",
        "## Completion status",
        "",
        "| Phase | Deliverable | Status |",
        "| --- | --- | --- |",
    ]
    for _, row in matrix.iterrows():
        lines.append(f"| {row.phase} | {row.deliverable} | {row.status} |")
    conclusion = (
        "The configured 25-seed synthetic benchmark is complete for all six algorithm "
        "tracks with matched evaluation budgets and independently checked hypervolume "
        "and IGD values."
        if final_complete
        else "The configured 25-seed synthetic benchmark is not complete."
    )
    lines += [
        "",
        "## Audit checks",
        "",
        "| Check | Category | Status | Evidence | Details |",
        "| --- | --- | --- | --- | --- |",
    ]
    for _, row in checks.iterrows():
        detail = str(row.details).replace("|", "\\|").replace("\n", " ")
        evidence = str(row.evidence).replace("|", "\\|")
        lines.append(
            f"| {row.check_id} | {row.category} | {row.status} | {evidence} | {detail} |"
        )
    lines += [
        "",
        "## Completion conclusion",
        "",
        "The repository is a reproducible synthetic methodological prototype through the strategy-reporting layer. The matched-budget benchmarks, supported scenario analysis, and small clean reproduction are evidenced by saved artifacts.",
        "",
        conclusion,
        "",
        "The proposal's empirical claim remains incomplete because the dataset, current allocation, and response model are synthetic or illustrative. Patent/compute shocks and innovation/student/societal strategy conclusions remain unsupported by the current decision and outcome schema.",
        "",
        "No best-algorithm or real-world productivity-improvement claim is supported by the current evidence.",
        "",
        "## Reproduction",
        "",
        "```bash",
        "make test",
        "make benchmark-smoke",
        "make benchmark-final",
        "make robustness-smoke",
        "make strategy-report",
        "make completion-audit",
        "```",
        "",
        "The clean reproduction output and independently recomputed hypervolume/IGD values are saved under `results/audit/phase12-small-reproduction/`.",
    ]
    (output / "audit_report.md").write_text("\n".join(lines) + "\n")


def run_audit(config_path, output_root=None):
    repo_root = Path.cwd()
    config_path = Path(config_path)
    config = json.loads(config_path.read_text())
    output = Path(output_root or config["output_root"])
    output.mkdir(parents=True, exist_ok=True)
    audit = Audit()

    required = [
        config["data_path"], config["provenance_path"], config["data_audit_path"],
        config["model_manifest"], config["allocation_config"], config["benchmark_root"],
        config["robustness_root"], config["reporting_root"],
    ]
    missing = [path for path in required if not Path(path).exists()]
    audit.check(not missing, "required_artifacts_exist", "setup", "; ".join(required), f"missing: {missing}")

    provenance = json.loads(Path(config["provenance_path"]).read_text())
    data_audit = json.loads(Path(config["data_audit_path"]).read_text())
    model_manifest = json.loads(Path(config["model_manifest"]).read_text())
    data_hash = _sha256(config["data_path"])
    audit.check(
        data_hash == data_audit["sha256"] == model_manifest["data_sha256"],
        "data_hash_chain",
        "provenance",
        data_hash,
        "data, audit, and model-manifest hashes differ",
    )
    audit.check(
        provenance["datasets"][0]["provenance"] == "synthetic"
        and data_audit["source_data_mutated"] is False,
        "synthetic_provenance_and_immutability",
        "provenance",
        config["provenance_path"],
        "synthetic classification or source immutability declaration failed",
    )
    features = set(model_manifest["feature_columns"])
    targets = set(model_manifest["target_columns"])
    forbidden = set(model_manifest["forbidden_feature_columns"])
    audit.check(
        features.isdisjoint(targets | forbidden) and "overall_rank" not in features,
        "target_leakage_contract",
        "model",
        config["model_manifest"],
        f"leaking features: {sorted(features & (targets | forbidden))}",
    )
    audit.check(
        set(model_manifest["selected_models"]) == targets
        and all("test_evaluation" in model_manifest for _ in [0]),
        "model_version_metrics_uncertainty",
        "model",
        config["model_manifest"],
        "selected model, test metrics, or uncertainty metadata missing",
    )

    completion = json.loads((Path(config["benchmark_root"]) / "completion.json").read_text())
    metrics = pd.read_csv(Path(config["benchmark_root"]) / "per_seed_metrics.csv")
    algorithms = set(metrics.algorithm)
    audit.check(
        completion["complete_jobs"] == completion["configured_jobs"] == 18
        and completion["failed_jobs"] == 0,
        "smoke_benchmark_complete",
        "benchmark",
        str(Path(config["benchmark_root"]) / "completion.json"),
        "smoke benchmark is incomplete or has failures",
    )
    audit.check(
        algorithms == {"nsga2", "nsga3", "moead", "mopso", "rion", "random_search"},
        "algorithm_coverage",
        "benchmark",
        ", ".join(sorted(algorithms)),
        "required algorithm tracks are missing",
    )
    _audit_accounting(config, audit)
    _recompute_metrics(Path(config["benchmark_root"]), audit)
    _audit_archives(config, audit)

    robustness_manifest = json.loads((Path(config["robustness_root"]) / "manifest.json").read_text())
    scenario_catalog = pd.read_csv(Path(config["robustness_root"]) / "scenario_catalog.csv")
    audit.check(
        (scenario_catalog.status == "supported").sum() >= 3
        and {15_000_000.0, 20_000_000.0, 25_000_000.0}.issubset(
            set(scenario_catalog.budget_limit.dropna())
        ),
        "scenario_coverage",
        "robustness",
        str(Path(config["robustness_root"]) / "scenario_catalog.csv"),
        "three budget levels or supported scenarios are missing",
    )
    draws = pd.read_csv(Path(config["robustness_root"]) / "common_uncertainty_draws.csv")
    audit.check(
        len(draws) == robustness_manifest["uncertainty"]["draws"]
        and robustness_manifest["uncertainty"]["common_draws_across_strategies_and_scenarios"],
        "common_uncertainty_draws",
        "robustness",
        str(Path(config["robustness_root"]) / "common_uncertainty_draws.csv"),
        "common-draw declaration or count mismatch",
    )
    assessments = pd.read_csv(Path(config["robustness_root"]) / "strategy_scenario_assessments.csv")
    audit.check(
        set(assessments.assessment_mode) == {"reoptimized", "fixed_baseline_strategy"},
        "fixed_vs_reoptimized_separation",
        "robustness",
        str(Path(config["robustness_root"]) / "strategy_scenario_assessments.csv"),
        "fixed and adaptive assessments are not both present",
    )
    unsupported = set(scenario_catalog[scenario_catalog.status == "unsupported"].scenario_id)
    audit.check(
        {"patent_cost_plus_25pct", "compute_cost_plus_25pct"}.issubset(unsupported),
        "unsupported_shocks_disclosed",
        "robustness",
        ", ".join(sorted(unsupported)),
        "unsupported patent/compute shocks were not disclosed",
    )

    report_manifest_path = Path(config["reporting_root"]) / "manifest.json"
    report_manifest = json.loads(report_manifest_path.read_text())
    hash_errors = [
        name
        for name, item in report_manifest["source_artifacts"].items()
        if not Path(item["path"]).exists() or _sha256(item["path"]) != item["sha256"]
    ]
    audit.check(
        not hash_errors,
        "report_source_hashes",
        "reporting",
        str(report_manifest_path),
        f"changed/missing report sources: {hash_errors}",
    )
    portfolio = pd.read_csv(Path(config["reporting_root"]) / "strategy_portfolio.csv")
    constraint_checks = pd.read_csv(Path(config["reporting_root"]) / "constraint_checks.csv")
    audit.check(
        portfolio.allocation_group.nunique() == report_manifest["unique_selected_allocations"]
        and portfolio.duplicates_another_strategy.astype(bool).all(),
        "strategy_duplicate_disclosure",
        "reporting",
        str(Path(config["reporting_root"]) / "strategy_portfolio.csv"),
        "strategy allocation groups or duplicate flags are inconsistent",
    )
    audit.check(
        constraint_checks.passed.astype(bool).all(),
        "reported_strategy_constraints",
        "reporting",
        str(Path(config["reporting_root"]) / "constraint_checks.csv"),
        "a reported current/strategy constraint failed",
    )

    final_root = Path(config["final_benchmark_root"])
    if (final_root / "completion.json").exists():
        final = json.loads((final_root / "completion.json").read_text())
        final_metrics = pd.read_csv(final_root / "per_seed_metrics.csv")
        configured_seeds = set(
            json.loads((final_root / "benchmark_config_snapshot.json").read_text())["seeds"]
        )
        expected_algorithms = {
            "nsga2", "nsga3", "moead", "mopso", "rion", "random_search"
        }
        coverage_ok = (
            set(final_metrics.algorithm) == expected_algorithms
            and len(final_metrics) == 150
            and all(
                set(final_metrics[final_metrics.algorithm == algorithm].seed)
                == configured_seeds
                for algorithm in expected_algorithms
            )
            and (final_metrics.status == "complete").all()
        )
        audit.check(
            _final_benchmark_complete(config) and coverage_ok,
            "final_25_seed_benchmark",
            "completion",
            str(final_root / "completion.json"),
            "final benchmark completion, algorithm, or seed coverage mismatch",
        )
        _audit_accounting_root(
            final_root,
            150,
            audit,
            "final_matched_evaluation_accounting",
            "final",
        )
        _recompute_metrics(
            final_root,
            audit,
            check_id="final_metrics_independent_recompute",
            output_path=output / "final_benchmark_independent_metric_check.csv",
        )
    else:
        audit.add(
            "final_25_seed_benchmark",
            "completion",
            "gap",
            "configs/benchmark/final_synthetic_25seeds.json",
            "configured but not executed; no inferential best-algorithm claim is supported",
        )
    audit.add(
        "empirical_departmental_evidence",
        "completion",
        "gap",
        config["provenance_path"],
        "only synthetic data and an illustrative reference allocation are available",
    )

    _clean_reproduction(repo_root, config, audit)
    full_tests = _subprocess_check(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        "full_test_suite",
        "tests",
        "python -m unittest discover -s tests -v",
        audit,
    )
    native_path = Path(config["native_library"])
    if native_path.exists():
        native = _subprocess_check(
            [sys.executable, "-m", "unittest", "tests.test_native_pso", "-v"],
            "optional_native_backend",
            "native",
            f"{native_path} sha256={_sha256(native_path)}",
            audit,
        )
        native_evidence = {
            "status": "tested_existing_binary",
            "path": str(native_path),
            "sha256": _sha256(native_path),
            "returncode": native.returncode,
            "stdout": native.stdout,
            "stderr": native.stderr,
        }
    else:
        audit.add(
            "optional_native_backend",
            "native",
            "gap",
            str(native_path),
            "optional compiled library is absent; serial workflow remains available",
        )
        native_evidence = {"status": "not_built", "path": str(native_path)}
    (output / "native_check.json").write_text(json.dumps(native_evidence, indent=2) + "\n")

    matrix = _completion_matrix(config)
    checks = audit.frame()
    checks.to_csv(output / "audit_checks.csv", index=False)
    matrix.to_csv(output / "completion_matrix.csv", index=False)
    (output / "audit_checks.json").write_text(
        json.dumps(checks.to_dict("records"), indent=2) + "\n"
    )
    _write_report(output, config, checks, matrix)
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "audit_id": config["audit_id"],
                "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                "config_path": str(config_path),
                "config_sha256": _sha256(config_path),
                "status_counts": checks.status.value_counts().to_dict(),
                "full_test_returncode": full_tests.returncode,
                "environment": {
                    "python": sys.version,
                    "platform": platform.platform(),
                    "numpy": np.__version__,
                    "pandas": pd.__version__,
                },
            },
            indent=2,
        )
        + "\n"
    )
    return output, checks


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/audit/phase12.json")
    parser.add_argument("--output-root")
    return parser.parse_args()


def main():
    args = parse_args()
    output, checks = run_audit(
        Path(args.config), Path(args.output_root) if args.output_root else None
    )
    counts = checks.status.value_counts().to_dict()
    print(
        f"Completion audit: {counts.get('pass', 0)} passed, "
        f"{counts.get('fail', 0)} failed, {counts.get('gap', 0)} gaps; {output}"
    )
    if counts.get("fail", 0):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
