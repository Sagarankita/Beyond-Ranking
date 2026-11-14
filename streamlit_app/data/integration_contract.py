"""Frozen dashboard integration types and backend-derived fixture builder.

This module describes data crossing the optimization-to-dashboard boundary. It does
not implement optimization, prediction, repair, scoring, or strategy selection.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from department_optimizer.public_allocation.problem import VJTIPublicAllocationProblem


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_SCHEMA_VERSION = 1
FIXTURE_PATH = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "vjti_contract_v1.json"

VJTI_CONFIG_PATH = Path("configs/public_allocation/vjti_four_family_v1.json")
VJTI_MODEL_ROOT = Path("artifacts/evidence_modeling/vjti_v1")
VJTI_EXPERIMENT_CONFIG_PATH = Path("configs/public_experiments/vjti_experiments_v1.json")
VJTI_ARCHIVE_PATH = Path(
    "artifacts/public_experiments/vjti_v1/runs/comparison/mopso/seed_17001/archive.csv"
)
VJTI_STATUS_PATH = VJTI_ARCHIVE_PATH.with_name("status.json")
VJTI_ACCOUNTING_PATH = VJTI_ARCHIVE_PATH.with_name("accounting.json")
FINAL_BENCHMARK_COMPLETION_PATH = Path(
    "results/benchmarks/phase6-final-synthetic-25seeds-v1/completion.json"
)
FINAL_BENCHMARK_METRICS_PATH = Path(
    "results/benchmarks/phase6-final-synthetic-25seeds-v1/per_seed_metrics.csv"
)


class ContractValidationError(ValueError):
    """Raised when data does not meet the frozen dashboard contract."""


class EvidenceLabel(StrEnum):
    OBSERVED_PUBLIC = "observed_public"
    DERIVED_PUBLIC = "derived_public"
    PUBLIC_DESCRIPTIVE = "public_descriptive"
    PUBLIC_VALIDATED = "public_validated"
    SYNTHETIC_CALIBRATED = "synthetic_calibrated"
    SYNTHETIC_SCENARIO = "synthetic_scenario"
    UNSUPPORTED = "unsupported"


class EvaluatorId(StrEnum):
    LEGACY = "AllocationProblem"
    VJTI = "VJTIPublicAllocationProblem"


@dataclass(frozen=True)
class DecisionVariableContract:
    name: str
    value: float
    unit: str
    variable_type: str
    lower: float
    upper: float
    increment: float
    cost_mode: str
    evidence: str


@dataclass(frozen=True)
class ScenarioInputRecord:
    scenario_id: str
    scenario_hash: str
    track_id: str
    evaluator: str
    budget_limit: float
    currency: str
    currency_basis: str
    faculty_total: float
    evidence_class: str
    config_path: str
    model_manifest_path: str


@dataclass(frozen=True)
class ObjectiveFamilyRecord:
    name: str
    benefit: float
    score: float
    scale: str
    evidence: str
    synthetic_coverage: float


@dataclass(frozen=True)
class ConstraintResidualRecord:
    name: str
    residual: float
    normalized_residual: float
    satisfied: bool


@dataclass(frozen=True)
class UncertaintyRecord:
    kpi: str
    prediction: float
    lower: float
    upper: float
    validation_type: str
    evidence: str


@dataclass(frozen=True)
class EvaluatorResultRecord:
    feasible: bool
    robust_feasible: bool
    normalized_violation: float
    total_cost: float
    budget_remaining: float
    out_of_model_support: bool
    out_of_support_features: tuple[str, ...]
    dea_status: str
    objectives: tuple[ObjectiveFamilyRecord, ...]
    constraints: tuple[ConstraintResidualRecord, ...]
    uncertainty: tuple[UncertaintyRecord, ...]


@dataclass(frozen=True)
class CandidateRecord:
    candidate_id: str
    scenario_hash: str
    source_run_id: str
    source_artifact: str
    source_row: int
    algorithm: str
    seed: int
    decisions: tuple[DecisionVariableContract, ...]
    evaluation: EvaluatorResultRecord


@dataclass(frozen=True)
class BenchmarkRecord:
    benchmark_id: str
    configured_jobs: int
    complete_jobs: int
    failed_jobs: int
    algorithms: tuple[str, ...]
    seeds: tuple[int, ...]
    evaluation_budget: int
    completion_artifact: str
    metrics_artifact: str


def _absolute(relative_path: Path) -> Path:
    return REPOSITORY_ROOT / relative_path


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _finite(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ContractValidationError(f"{label} must be numeric") from exc
    if not math.isfinite(number):
        raise ContractValidationError(f"{label} must be finite")
    return number


def _read_json(relative_path: Path) -> dict[str, Any]:
    return json.loads(_absolute(relative_path).read_text(encoding="utf-8"))


def build_vjti_contract_fixture() -> dict[str, Any]:
    """Build one real saved-candidate trace through the canonical VJTI evaluator."""

    config = _read_json(VJTI_CONFIG_PATH)
    experiment_config = _read_json(VJTI_EXPERIMENT_CONFIG_PATH)
    status = _read_json(VJTI_STATUS_PATH)
    accounting = _read_json(VJTI_ACCOUNTING_PATH)
    completion = _read_json(FINAL_BENCHMARK_COMPLETION_PATH)
    metrics = pd.read_csv(_absolute(FINAL_BENCHMARK_METRICS_PATH))
    archive = pd.read_csv(_absolute(VJTI_ARCHIVE_PATH))

    source_row = 4
    saved = archive.iloc[source_row]
    problem = VJTIPublicAllocationProblem(config, _absolute(VJTI_MODEL_ROOT))
    decisions = {name: _finite(saved[name], name) for name in problem.variable_names}
    evaluation = problem.evaluate_fixed(decisions)

    config_hash = file_sha256(_absolute(VJTI_CONFIG_PATH))
    model_manifest_path = VJTI_MODEL_ROOT / "model_manifest.json"
    model_hash = file_sha256(_absolute(model_manifest_path))
    scenario_hash = canonical_sha256(
        {
            "track_id": config["analysis_id"],
            "config": config,
            "config_sha256": config_hash,
            "model_manifest_sha256": model_hash,
        }
    )
    source_run_id = f"{experiment_config['analysis_id']}:mopso:seed_17001"
    candidate_id = canonical_sha256(
        {
            "scenario_hash": scenario_hash,
            "source_run_id": source_run_id,
            "source_row": source_row,
            "decisions": decisions,
        }
    )[:24]

    specifications = {item["name"]: item for item in config["decision_variables"]}
    decision_records = tuple(
        DecisionVariableContract(
            name=name,
            value=value,
            unit=str(specifications[name]["unit"]),
            variable_type=str(specifications[name]["type"]),
            lower=float(specifications[name]["lower"]),
            upper=float(specifications[name]["upper"]),
            increment=float(specifications[name]["increment"]),
            cost_mode=str(specifications[name]["cost_mode"]),
            evidence=str(specifications[name]["provenance"]),
        )
        for name, value in decisions.items()
    )
    objectives = tuple(
        ObjectiveFamilyRecord(
            name=name,
            benefit=float(evaluation.objective_benefits[name]),
            score=float(evaluation.objective_scores[name]),
            scale="normalized benefit [0, 1]; optimizer minimizes negative benefit",
            evidence=str(evaluation.objective_evidence[name]),
            synthetic_coverage=float(evaluation.synthetic_coverage[name]),
        )
        for name in evaluation.objective_benefits
    )
    constraints = tuple(
        ConstraintResidualRecord(
            name=name,
            residual=float(value),
            normalized_residual=float(evaluation.normalized_constraint_violations[name]),
            satisfied=bool(value <= 1e-9),
        )
        for name, value in evaluation.constraint_residuals.items()
    )
    uncertainty = tuple(
        UncertaintyRecord(
            kpi=name,
            prediction=float(evaluation.raw_kpis[name]),
            lower=float(interval["lower"]),
            upper=float(interval["upper"]),
            validation_type=str(interval["validation_type"]),
            evidence="synthetic_scenario",
        )
        for name, interval in evaluation.intervals.items()
    )
    result_record = EvaluatorResultRecord(
        feasible=bool(evaluation.feasible),
        robust_feasible=bool(evaluation.robust_feasible),
        normalized_violation=float(evaluation.normalized_violation),
        total_cost=float(evaluation.total_cost),
        budget_remaining=float(evaluation.budget_remaining),
        out_of_model_support=bool(evaluation.support_flags["out_of_model_support"]),
        out_of_support_features=tuple(evaluation.support_flags["out_of_support_features"]),
        dea_status=str(evaluation.dea_status),
        objectives=objectives,
        constraints=constraints,
        uncertainty=uncertainty,
    )
    candidate = CandidateRecord(
        candidate_id=candidate_id,
        scenario_hash=scenario_hash,
        source_run_id=source_run_id,
        source_artifact=f"{VJTI_ARCHIVE_PATH.as_posix()}#row={source_row}",
        source_row=source_row,
        algorithm="mopso",
        seed=17001,
        decisions=decision_records,
        evaluation=result_record,
    )
    scenario = ScenarioInputRecord(
        scenario_id="vjti-reference-36m",
        scenario_hash=scenario_hash,
        track_id=str(config["analysis_id"]),
        evaluator=EvaluatorId.VJTI,
        budget_limit=float(config["budget_limit"]),
        currency=str(config["currency"]["code"]),
        currency_basis=str(config["currency"]["base_year"]),
        faculty_total=float(config["fixed_context"]["faculty_total"]),
        evidence_class="public_plus_synthetic_scenario",
        config_path=VJTI_CONFIG_PATH.as_posix(),
        model_manifest_path=model_manifest_path.as_posix(),
    )

    completed_metrics = metrics[metrics["status"] == "complete"]
    benchmark = BenchmarkRecord(
        benchmark_id="phase6-final-synthetic-25seeds-v1",
        configured_jobs=int(completion["configured_jobs"]),
        complete_jobs=int(completion["complete_jobs"]),
        failed_jobs=int(completion["failed_jobs"]),
        algorithms=tuple(sorted(completed_metrics["algorithm"].unique())),
        seeds=tuple(sorted(int(value) for value in completed_metrics["seed"].unique())),
        evaluation_budget=int(completed_metrics["target_candidate_evaluations"].iloc[0]),
        completion_artifact=FINAL_BENCHMARK_COMPLETION_PATH.as_posix(),
        metrics_artifact=FINAL_BENCHMARK_METRICS_PATH.as_posix(),
    )

    fixture = {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "fixture_id": "vjti-mopso-17001-row4-contract-v1",
        "claim_boundary": (
            "Public-calibrated plus synthetic scenario evidence. Predictions are modeled, "
            "not causal or empirically validated allocation effects."
        ),
        "scenario": asdict(scenario),
        "candidate": asdict(candidate),
        "run": {
            "run_id": source_run_id,
            "status": status["status"],
            "algorithm": status["algorithm"],
            "seed": int(status["seed"]),
            "evaluation_accounting": accounting,
        },
        "benchmark": asdict(benchmark),
        "source_hashes": {
            path.as_posix(): file_sha256(_absolute(path))
            for path in (
                VJTI_CONFIG_PATH,
                model_manifest_path,
                VJTI_EXPERIMENT_CONFIG_PATH,
                VJTI_ARCHIVE_PATH,
                VJTI_STATUS_PATH,
                VJTI_ACCOUNTING_PATH,
                FINAL_BENCHMARK_COMPLETION_PATH,
                FINAL_BENCHMARK_METRICS_PATH,
            )
        },
        "supported_runtime_overrides": {
            "budget_limit": "INR total budget",
            "fixed_context.faculty_total": "annual faculty FTE supply",
            "decision_variables.<name>.cost_multiplier": "dimensionless supported unit-cost shock",
        },
        "requires_regeneration_or_retraining": [
            "decision variable bounds, increments, types, or model mappings",
            "objective KPI composition, weights, or normalization ranges",
            "KPI model features, targets, training data, support ranges, or conformal radii",
            "DEA inputs, outputs, peer cohort, or formulation",
            "public evidence values, derivations, or immutable source snapshots",
        ],
    }
    validate_contract_fixture(fixture)
    return fixture


def validate_contract_fixture(fixture: Mapping[str, Any]) -> None:
    if fixture.get("schema_version") != CONTRACT_SCHEMA_VERSION:
        raise ContractValidationError("unsupported dashboard contract schema")
    scenario = fixture.get("scenario")
    candidate = fixture.get("candidate")
    benchmark = fixture.get("benchmark")
    if not isinstance(scenario, Mapping) or not isinstance(candidate, Mapping):
        raise ContractValidationError("scenario and candidate records are required")
    if candidate.get("scenario_hash") != scenario.get("scenario_hash"):
        raise ContractValidationError("candidate belongs to a different scenario")
    if len(str(scenario.get("scenario_hash", ""))) != 64:
        raise ContractValidationError("scenario_hash must be a SHA-256 digest")
    if not candidate.get("decisions"):
        raise ContractValidationError("candidate decisions are required")
    evaluation = candidate.get("evaluation")
    if not isinstance(evaluation, Mapping):
        raise ContractValidationError("candidate evaluation is required")
    _finite(evaluation.get("total_cost"), "evaluation.total_cost")
    _finite(evaluation.get("budget_remaining"), "evaluation.budget_remaining")
    for item in evaluation.get("uncertainty", []):
        lower = _finite(item.get("lower"), "uncertainty.lower")
        point = _finite(item.get("prediction"), "uncertainty.prediction")
        upper = _finite(item.get("upper"), "uncertainty.upper")
        if not lower <= point <= upper:
            raise ContractValidationError("uncertainty interval does not contain prediction")
    if not isinstance(benchmark, Mapping):
        raise ContractValidationError("benchmark record is required")
    if int(benchmark.get("configured_jobs", -1)) != 150:
        raise ContractValidationError("final benchmark must declare 150 jobs")
    if int(benchmark.get("complete_jobs", -1)) != 150 or int(benchmark.get("failed_jobs", -1)) != 0:
        raise ContractValidationError("final benchmark is not complete")
    if len(benchmark.get("algorithms", ())) != 6 or len(benchmark.get("seeds", ())) != 25:
        raise ContractValidationError("final benchmark algorithm or seed count is incorrect")


def write_fixture(path: Path = FIXTURE_PATH) -> Path:
    fixture = build_vjti_contract_fixture()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(fixture, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path


if __name__ == "__main__":
    print(write_fixture().relative_to(REPOSITORY_ROOT))
