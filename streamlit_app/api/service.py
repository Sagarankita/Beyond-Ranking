from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from department_optimizer.allocation import (
    CanonicalNSGA2Adapter,
    MOEADAdapter,
    MOPSOAdapter,
    NSGA3Adapter,
    RandomSearchAdapter,
    RionAllocationAdapter,
)
from department_optimizer.public_allocation.problem import FAMILIES, VJTIPublicAllocationProblem
from streamlit_app.api.explanations import ExplanationService
from streamlit_app.api.recommendations import build_recommendations
from streamlit_app.api.schemas import RunCreateRequest, ScenarioValidationRequest, SensitivityRequest
from streamlit_app.data.integration_contract import (
    FINAL_BENCHMARK_COMPLETION_PATH,
    FINAL_BENCHMARK_METRICS_PATH,
    REPOSITORY_ROOT,
    VJTI_CONFIG_PATH,
    VJTI_EXPERIMENT_CONFIG_PATH,
    VJTI_MODEL_ROOT,
    canonical_sha256,
    file_sha256,
)


SERVICE_SCHEMA_VERSION = 1
SERVICE_PROTOCOL_VERSION = "dashboard-live-run-v1"
DEFAULT_RUN_ROOT = REPOSITORY_ROOT / "results" / "dashboard_runs"


class DashboardServiceError(ValueError):
    def __init__(self, code: str, message: str, fields: Mapping[str, str] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.fields = dict(fields or {})

    def detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "fields": self.fields}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _records(path: Path) -> list[dict[str, Any]]:
    """Read finite JSON-safe records from one versioned CSV artifact."""
    return json.loads(pd.read_csv(path).to_json(orient="records"))


def _atomic_json(path: Path, value: Mapping[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False, default=float) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _finite(value: Any, name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise DashboardServiceError("invalid_number", f"{name} must be finite", {name: "must be finite"})
    return number


class DashboardRunService:
    """Validated scenario adapter with persisted run state and real optimizer execution."""

    def __init__(
        self,
        run_root: Path | None = None,
        *,
        synchronous: bool = False,
        max_workers: int = 1,
        explanation_service: ExplanationService | None = None,
    ):
        self.run_root = Path(run_root or os.environ.get("DASHBOARD_RUN_ROOT", DEFAULT_RUN_ROOT))
        self.run_root.mkdir(parents=True, exist_ok=True)
        self.synchronous = synchronous
        self._lock = threading.RLock()
        self._executor = None if synchronous else ThreadPoolExecutor(max_workers=max_workers)
        self._explanation_service = explanation_service or ExplanationService.from_environment(
            REPOSITORY_ROOT
        )
        self._recover_interrupted_runs()

    def close(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=True, cancel_futures=False)

    def _recover_interrupted_runs(self) -> None:
        for status_path in self.run_root.glob("*/status.json"):
            status = _json(status_path)
            if status.get("status") in {"queued", "running"}:
                status.update(
                    status="interrupted",
                    phase="stopped",
                    updated_at_utc=_now(),
                    error={
                        "code": "service_restart",
                        "message": "The service restarted before this run completed.",
                        "retryable": True,
                    },
                )
                _atomic_json(status_path, status)

    @property
    def base_config(self) -> dict[str, Any]:
        return _json(REPOSITORY_ROOT / VJTI_CONFIG_PATH)

    @property
    def experiment_config(self) -> dict[str, Any]:
        return _json(REPOSITORY_ROOT / VJTI_EXPERIMENT_CONFIG_PATH)

    def defaults(self) -> dict[str, Any]:
        config = self.base_config
        variables = []
        for item in config["decision_variables"]:
            variables.append(
                {
                    "name": item["name"],
                    "unit": item["unit"],
                    "type": item["type"],
                    "lower": item["lower"],
                    "upper": item["upper"],
                    "increment": item["increment"],
                    "cost_mode": item["cost_mode"],
                    "unit_cost": item.get("unit_cost"),
                    "provenance": item["provenance"],
                    "editable": False,
                }
            )
        return {
            "schema_version": SERVICE_SCHEMA_VERSION,
            "track_id": "vjti_public_plus_synthetic",
            "analysis_id": config["analysis_id"],
            "evaluator": "VJTIPublicAllocationProblem",
            "evidence_class": config["evidence_status"],
            "claim_boundary": "Modeled public-calibrated plus synthetic scenario, not a causal effect estimate.",
            "defaults": {
                "budget_limit": config["budget_limit"],
                "budget_unit": "INR",
                "faculty_total": config["fixed_context"]["faculty_total"],
                "faculty_unit": "annual FTE",
                "cost_multipliers": {},
            },
            "service_commitments": config["service_commitments"],
            "decision_variables": variables,
            "supported_overrides": [
                "budget_limit",
                "faculty_total",
                "cost_multipliers.<existing monetary decision>",
            ],
            "presets": self.experiment_config["scenarios"],
            "algorithms": list(self.experiment_config["algorithms"]),
            "interactive_evaluation_budget": self.experiment_config["matched_candidate_evaluations"],
            "config_sha256": file_sha256(REPOSITORY_ROOT / VJTI_CONFIG_PATH),
            "model_manifest_sha256": file_sha256(REPOSITORY_ROOT / VJTI_MODEL_ROOT / "model_manifest.json"),
        }

    def _scenario_config(self, request: ScenarioValidationRequest) -> tuple[dict[str, Any], dict[str, str]]:
        config = copy.deepcopy(self.base_config)
        overrides = request.overrides
        errors: dict[str, str] = {}
        if overrides.budget_limit is not None:
            config["budget_limit"] = _finite(overrides.budget_limit, "budget_limit")
        if overrides.faculty_total is not None:
            config["fixed_context"]["faculty_total"] = _finite(overrides.faculty_total, "faculty_total")

        variables = {item["name"]: item for item in config["decision_variables"]}
        for name, multiplier in overrides.cost_multipliers.items():
            if name not in variables:
                errors[f"cost_multipliers.{name}"] = "unknown decision variable"
                continue
            if variables[name]["cost_mode"] == "non_monetary":
                errors[f"cost_multipliers.{name}"] = "cost multipliers require a monetary decision"
                continue
            variables[name]["cost_multiplier"] = float(multiplier)

        minimum_cost = 0.0
        for variable in config["decision_variables"]:
            lower = float(variable["lower"])
            multiplier = float(variable.get("cost_multiplier", 1.0))
            if variable["cost_mode"] == "direct_money":
                minimum_cost += lower * multiplier
            elif variable["cost_mode"] == "unit_cost":
                minimum_cost += lower * float(variable["unit_cost"]) * multiplier
        if float(config["budget_limit"]) + 1e-9 < minimum_cost:
            errors["budget_limit"] = f"must be at least INR {minimum_cost:,.0f} for configured lower bounds"

        effort_names = {
            "research_faculty_effort",
            "student_support_faculty_effort",
            "service_faculty_effort",
        }
        minimum_effort = sum(
            float(item["lower"]) for item in config["decision_variables"] if item["name"] in effort_names
        )
        teaching_floor = float(config["service_commitments"]["minimum_teaching_fte"])
        minimum_faculty = minimum_effort + teaching_floor
        if float(config["fixed_context"]["faculty_total"]) + 1e-9 < minimum_faculty:
            errors["faculty_total"] = (
                f"must be at least {minimum_faculty:g} annual FTE to preserve teaching and decision lower bounds"
            )
        return config, errors

    def validate_scenario(self, request: ScenarioValidationRequest) -> dict[str, Any]:
        config, errors = self._scenario_config(request)
        if errors:
            return {"valid": False, "field_errors": errors, "scenario_hash": None}
        try:
            problem = VJTIPublicAllocationProblem(config, REPOSITORY_ROOT / VJTI_MODEL_ROOT)
            reference = problem.evaluate_fixed(config["reference_allocation"])
        except Exception as exc:
            return {
                "valid": False,
                "field_errors": {"scenario": str(exc)},
                "scenario_hash": None,
            }
        scenario_hash = canonical_sha256(
            {
                "track_id": request.track_id,
                "config": config,
                "model_manifest_sha256": file_sha256(
                    REPOSITORY_ROOT / VJTI_MODEL_ROOT / "model_manifest.json"
                ),
            }
        )
        return {
            "valid": True,
            "field_errors": {},
            "scenario_hash": scenario_hash,
            "normalized": {
                "budget_limit": config["budget_limit"],
                "budget_unit": "INR",
                "faculty_total": config["fixed_context"]["faculty_total"],
                "faculty_unit": "annual FTE",
                "cost_multipliers": {
                    item["name"]: item["cost_multiplier"]
                    for item in config["decision_variables"]
                    if "cost_multiplier" in item
                },
            },
            "reference_assessment": {
                "feasible_without_repair": reference.feasible,
                "total_cost": reference.total_cost,
                "budget_remaining": reference.budget_remaining,
                "normalized_violation": reference.normalized_violation,
            },
            "config": config,
        }

    def _run_id(self, request: RunCreateRequest, scenario_hash: str) -> str:
        return canonical_sha256(
            {
                "protocol": SERVICE_PROTOCOL_VERSION,
                "scenario_hash": scenario_hash,
                "algorithm": request.algorithm,
                "seed": request.seed,
                "evaluation_budget": request.evaluation_budget,
            }
        )[:24]

    def _run_path(self, run_id: str) -> Path:
        if not run_id or any(character not in "0123456789abcdef" for character in run_id):
            raise DashboardServiceError("invalid_run_id", "Run ID must be hexadecimal")
        return self.run_root / run_id

    def create_run(self, request: RunCreateRequest) -> dict[str, Any]:
        expected = int(self.experiment_config["matched_candidate_evaluations"])
        if request.evaluation_budget != expected:
            raise DashboardServiceError(
                "unsupported_evaluation_budget",
                f"Interactive runs currently require exactly {expected} candidate evaluations.",
                {"evaluation_budget": f"must equal {expected}"},
            )
        validation = self.validate_scenario(request)
        if not validation["valid"]:
            raise DashboardServiceError(
                "invalid_scenario", "Scenario validation failed.", validation["field_errors"]
            )
        scenario_hash = validation["scenario_hash"]
        run_id = self._run_id(request, scenario_hash)
        run_path = self._run_path(run_id)
        status_path = run_path / "status.json"
        with self._lock:
            if status_path.exists():
                status = _json(status_path)
                status["duplicate_submission"] = True
                return status
            run_path.mkdir(parents=True, exist_ok=False)
            _atomic_json(run_path / "request.json", request.model_dump(mode="json"))
            _atomic_json(run_path / "scenario_config.json", validation["config"])
            status = {
                "run_id": run_id,
                "scenario_hash": scenario_hash,
                "status": "queued",
                "phase": "queued",
                "algorithm": request.algorithm,
                "seed": request.seed,
                "evaluation_budget": request.evaluation_budget,
                "attempt": 1,
                "created_at_utc": _now(),
                "updated_at_utc": _now(),
                "duplicate_submission": False,
                "error": None,
            }
            _atomic_json(status_path, status)
            self._submit(run_id)
            return _json(status_path)

    def _submit(self, run_id: str) -> None:
        if self.synchronous:
            self._execute(run_id)
        else:
            assert self._executor is not None
            self._executor.submit(self._execute, run_id)

    def _adapter(self, request: RunCreateRequest):
        parameters = copy.deepcopy(self.experiment_config["algorithms"][request.algorithm])
        classes = {
            "nsga2": CanonicalNSGA2Adapter,
            "nsga3": NSGA3Adapter,
            "moead": MOEADAdapter,
            "mopso": MOPSOAdapter,
            "rion": RionAllocationAdapter,
            "random_search": RandomSearchAdapter,
        }
        return classes[request.algorithm](seed=request.seed, **parameters)

    def _candidate_record(
        self,
        run_id: str,
        scenario_hash: str,
        source_row: int,
        row: pd.Series,
        problem: VJTIPublicAllocationProblem,
    ) -> dict[str, Any]:
        decisions = {name: float(row[name]) for name in problem.variable_names}
        result = problem.evaluate_fixed(decisions)
        if not result.feasible:
            raise DashboardServiceError(
                "revalidation_failed",
                f"Archive row {source_row} failed independent evaluator revalidation.",
            )
        candidate_id = canonical_sha256(
            {
                "run_id": run_id,
                "scenario_hash": scenario_hash,
                "source_row": source_row,
                "decisions": decisions,
            }
        )[:24]
        return {
            "candidate_id": candidate_id,
            "run_id": run_id,
            "scenario_hash": scenario_hash,
            "source_row": source_row,
            "revalidated": True,
            "feasible": True,
            "robust_feasible": bool(result.robust_feasible),
            "decisions": decisions,
            "total_cost": float(result.total_cost),
            "budget_remaining": float(result.budget_remaining),
            "normalized_violation": float(result.normalized_violation),
            "objectives": {
                name: {
                    "benefit": float(result.objective_benefits[name]),
                    "score": float(result.objective_scores[name]),
                    "evidence": result.objective_evidence[name],
                    "synthetic_coverage": float(result.synthetic_coverage[name]),
                }
                for name in result.objective_benefits
            },
            "kpis": {
                name: {
                    "prediction": float(result.raw_kpis[name]),
                    "lower": float(result.intervals[name]["lower"]),
                    "upper": float(result.intervals[name]["upper"]),
                    "validation_type": result.intervals[name]["validation_type"],
                }
                for name in result.raw_kpis
            },
            "constraints": {
                name: {
                    "residual": float(value),
                    "normalized_residual": float(result.normalized_constraint_violations[name]),
                    "satisfied": bool(value <= 1e-9),
                }
                for name, value in result.constraint_residuals.items()
            },
            "support_flags": result.support_flags,
            "dea_status": result.dea_status,
        }

    def _execute(self, run_id: str) -> None:
        run_path = self._run_path(run_id)
        status_path = run_path / "status.json"
        try:
            request = RunCreateRequest.model_validate(_json(run_path / "request.json"))
            config = _json(run_path / "scenario_config.json")
            status = _json(status_path)
            status.update(status="running", phase="optimization", updated_at_utc=_now(), error=None)
            _atomic_json(status_path, status)

            problem = VJTIPublicAllocationProblem(config, REPOSITORY_ROOT / VJTI_MODEL_ROOT)
            result = self._adapter(request).run(problem)
            actual_budget = int(result.accounting["candidate_evaluations_total"])
            if actual_budget != request.evaluation_budget:
                raise DashboardServiceError(
                    "evaluation_accounting_mismatch",
                    f"Optimizer consumed {actual_budget} evaluations, expected {request.evaluation_budget}.",
                )
            result.population.to_csv(run_path / "population.csv", index=False)
            result.archive.to_csv(run_path / "archive.csv", index=False)
            _atomic_json(run_path / "evaluation_accounting.json", result.accounting)

            status.update(phase="revalidation", updated_at_utc=_now())
            _atomic_json(status_path, status)
            candidates = [
                self._candidate_record(run_id, status["scenario_hash"], index, row, problem)
                for index, row in result.archive.reset_index(drop=True).iterrows()
            ]
            _atomic_json(run_path / "candidates.json", candidates)
            manifest = {
                "schema_version": SERVICE_SCHEMA_VERSION,
                "protocol_version": SERVICE_PROTOCOL_VERSION,
                "run_id": run_id,
                "scenario_hash": status["scenario_hash"],
                "evaluator": "VJTIPublicAllocationProblem",
                "algorithm": request.algorithm,
                "seed": request.seed,
                "evaluation_budget": request.evaluation_budget,
                "candidate_count": len(candidates),
                "request_sha256": file_sha256(run_path / "request.json"),
                "config_sha256": file_sha256(run_path / "scenario_config.json"),
                "model_manifest_sha256": file_sha256(
                    REPOSITORY_ROOT / VJTI_MODEL_ROOT / "model_manifest.json"
                ),
                "population_sha256": file_sha256(run_path / "population.csv"),
                "archive_sha256": file_sha256(run_path / "archive.csv"),
                "accounting_sha256": file_sha256(run_path / "evaluation_accounting.json"),
                "candidates_sha256": file_sha256(run_path / "candidates.json"),
                "claim_boundary": "Modeled public-calibrated plus synthetic scenario, not a causal effect estimate.",
            }
            _atomic_json(run_path / "manifest.json", manifest)
            status.update(
                status="complete",
                phase="complete",
                updated_at_utc=_now(),
                feasible_candidate_count=len(candidates),
                result="feasible_archive" if candidates else "no_feasible_solution",
                manifest_path=f"{run_id}/manifest.json",
            )
            _atomic_json(status_path, status)
        except Exception as exc:
            if isinstance(exc, DashboardServiceError):
                error = {**exc.detail(), "retryable": True}
            else:
                error = {
                    "code": "run_failed",
                    "message": str(exc),
                    "fields": {},
                    "retryable": True,
                }
            status = _json(status_path)
            status.update(
                status="failed",
                phase="failed",
                updated_at_utc=_now(),
                error=error,
            )
            _atomic_json(status_path, status)

    def get_run(self, run_id: str) -> dict[str, Any]:
        status_path = self._run_path(run_id) / "status.json"
        if not status_path.is_file():
            raise DashboardServiceError("run_not_found", "Run was not found.")
        return _json(status_path)

    def retry_run(self, run_id: str) -> dict[str, Any]:
        status_path = self._run_path(run_id) / "status.json"
        with self._lock:
            status = self.get_run(run_id)
            if status["status"] not in {"failed", "interrupted"}:
                raise DashboardServiceError(
                    "run_not_retryable", "Only failed or interrupted runs can be retried."
                )
            status.update(
                status="queued",
                phase="queued",
                attempt=int(status.get("attempt", 1)) + 1,
                updated_at_utc=_now(),
                error=None,
                duplicate_submission=False,
            )
            _atomic_json(status_path, status)
            self._submit(run_id)
            return _json(status_path)

    def candidates(self, run_id: str) -> list[dict[str, Any]]:
        status = self.get_run(run_id)
        if status["status"] != "complete":
            raise DashboardServiceError("run_not_complete", "Candidates are available after completion.")
        path = self._run_path(run_id) / "candidates.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def recommendations(self, run_id: str) -> dict[str, Any]:
        status = self.get_run(run_id)
        if status["status"] != "complete":
            raise DashboardServiceError(
                "run_not_complete", "Recommendations are available after run completion."
            )
        config = _json(self._run_path(run_id) / "scenario_config.json")
        problem = VJTIPublicAllocationProblem(config, REPOSITORY_ROOT / VJTI_MODEL_ROOT)
        return build_recommendations(
            run_status=status,
            candidates=self.candidates(run_id),
            problem=problem,
            experiment_config=self.experiment_config,
        )

    def explanation_status(self) -> dict[str, Any]:
        return {
            "enabled": bool(self._explanation_service.enabled),
            "provider_configured": self._explanation_service.provider is not None,
            "default_mode": "ai_available"
            if self._explanation_service.enabled
            and self._explanation_service.provider is not None
            else "rule_based",
            "provider_disclosure": (
                "When requested, the allowlisted recommendation fact packet is sent to Groq for wording only."
            ),
        }

    def explain(self, run_id: str, recommendation_id: str, language: str = "en") -> dict[str, Any]:
        package = self.recommendations(run_id)
        recommendation = next(
            (
                item
                for item in package["recommendations"]
                if item["recommendation_id"] == recommendation_id
            ),
            None,
        )
        if recommendation is None:
            raise DashboardServiceError(
                "recommendation_not_found",
                "Recommendation does not belong to this completed run.",
            )
        result = self._explanation_service.explain(
            recommendation=recommendation,
            cache_directory=self._run_path(run_id) / "explanations",
            language=language,
        )
        return {
            "run_id": run_id,
            "scenario_hash": package["scenario_hash"],
            "candidate_id": recommendation["candidate_id"],
            "recommendation_id": recommendation_id,
            "selection_unchanged": True,
            "structured_facts_remain_authoritative": True,
            **result,
        }

    @staticmethod
    def _recommendation_for_profile(package: Mapping[str, Any], profile: str) -> dict[str, Any] | None:
        profile_row = next(
            (
                item
                for item in package["profile_results"]
                if item["profile"] == profile and item["status"] in {"selected", "duplicate"}
            ),
            None,
        )
        if profile_row is None:
            return None
        return next(
            item
            for item in package["recommendations"]
            if item["recommendation_id"] == profile_row["recommendation_id"]
        )

    def create_sensitivity(self, run_id: str, request: SensitivityRequest) -> dict[str, Any]:
        base_status = self.get_run(run_id)
        if base_status["status"] != "complete":
            raise DashboardServiceError(
                "run_not_complete", "Sensitivity requires a completed baseline run."
            )
        recommendations = self.recommendations(run_id)
        baseline_recommendation = self._recommendation_for_profile(
            recommendations, request.profile
        )
        if baseline_recommendation is None:
            raise DashboardServiceError(
                "unsupported_profile",
                f"The {request.profile} profile has no supported baseline recommendation.",
            )
        original = RunCreateRequest.model_validate(_json(self._run_path(run_id) / "request.json"))
        base_config = _json(self._run_path(run_id) / "scenario_config.json")
        current_value = (
            float(base_config["budget_limit"])
            if request.factor == "budget_limit"
            else float(base_config["fixed_context"]["faculty_total"])
        )
        if math.isclose(float(request.new_value), current_value, rel_tol=0.0, abs_tol=1e-12):
            raise DashboardServiceError(
                "unchanged_factor",
                "Sensitivity factor must differ from the baseline scenario.",
                {"new_value": "must differ from the baseline value"},
            )
        changed_payload = original.model_dump(mode="json")
        changed_payload["overrides"][request.factor] = float(request.new_value)
        changed_request = RunCreateRequest.model_validate(changed_payload)
        changed_status = self.create_run(changed_request)
        context = {
            "schema_version": 1,
            "baseline_run_id": run_id,
            "sensitivity_run_id": changed_status["run_id"],
            "factor": request.factor,
            "before": current_value,
            "after": float(request.new_value),
            "unit": "INR" if request.factor == "budget_limit" else "annual FTE",
            "profile": request.profile,
            "baseline_candidate_id": baseline_recommendation["candidate_id"],
            "algorithm": original.algorithm,
            "seed": original.seed,
            "evaluation_budget": original.evaluation_budget,
            "assessment_modes": ["held_fixed_without_repair", "reoptimized"],
            "claim_boundary": "Controlled one-factor modeled sensitivity; not a causal real-world effect.",
            "created_at_utc": _now(),
        }
        _atomic_json(
            self._run_path(run_id) / "sensitivities" / f"{changed_status['run_id']}.json",
            context,
        )
        _atomic_json(self._run_path(changed_status["run_id"]) / "sensitivity_context.json", context)
        return {**context, "run_status": changed_status}

    def sensitivity_result(self, run_id: str, sensitivity_run_id: str) -> dict[str, Any]:
        self._run_path(sensitivity_run_id)
        context_path = self._run_path(run_id) / "sensitivities" / f"{sensitivity_run_id}.json"
        if not context_path.is_file():
            raise DashboardServiceError(
                "sensitivity_not_found", "Sensitivity case was not found for this baseline run."
            )
        context = _json(context_path)
        changed_status = self.get_run(sensitivity_run_id)
        if changed_status["status"] != "complete":
            return {**context, "status": changed_status["status"], "run_status": changed_status}

        baseline_package = self.recommendations(run_id)
        changed_package = self.recommendations(sensitivity_run_id)
        baseline_recommendation = self._recommendation_for_profile(
            baseline_package, context["profile"]
        )
        changed_recommendation = self._recommendation_for_profile(
            changed_package, context["profile"]
        )
        if baseline_recommendation is None:
            raise DashboardServiceError(
                "baseline_recommendation_missing", "The baseline recommendation is unavailable."
            )
        changed_config = _json(self._run_path(sensitivity_run_id) / "scenario_config.json")
        changed_problem = VJTIPublicAllocationProblem(
            changed_config, REPOSITORY_ROOT / VJTI_MODEL_ROOT
        )
        baseline_candidate = next(
            item
            for item in self.candidates(run_id)
            if item["candidate_id"] == baseline_recommendation["candidate_id"]
        )
        held_fixed = changed_problem.evaluate_fixed(baseline_candidate["decisions"])

        baseline_objectives = {
            item["name"]: item["proposed"]
            for item in baseline_recommendation["objective_deltas"]
        }
        held_fixed_objectives = {
            name: float(held_fixed.objective_benefits[name]) for name in FAMILIES
        }
        reoptimized_objectives = (
            {
                item["name"]: item["proposed"]
                for item in changed_recommendation["objective_deltas"]
            }
            if changed_recommendation
            else None
        )
        return {
            **context,
            "status": "complete",
            "run_status": changed_status,
            "held_fixed": {
                "assessment_mode": "held_fixed_without_repair",
                "candidate_id": baseline_candidate["candidate_id"],
                "feasible": bool(held_fixed.feasible),
                "robust_feasible": bool(held_fixed.robust_feasible),
                "total_cost": float(held_fixed.total_cost),
                "budget_remaining": float(held_fixed.budget_remaining),
                "objectives": held_fixed_objectives,
                "objective_changes_from_baseline": {
                    name: held_fixed_objectives[name] - baseline_objectives[name]
                    for name in FAMILIES
                },
            },
            "reoptimized": (
                {
                    "assessment_mode": "reoptimized",
                    "candidate_id": changed_recommendation["candidate_id"],
                    "nominal_feasible": changed_recommendation["nominal_feasible"],
                    "robust_feasible": changed_recommendation["robust_feasible"],
                    "total_cost": changed_recommendation["budget"]["proposed"],
                    "budget_remaining": changed_recommendation["budget"]["headroom"],
                    "objectives": reoptimized_objectives,
                    "objective_changes_from_baseline": {
                        name: reoptimized_objectives[name] - baseline_objectives[name]
                        for name in FAMILIES
                    },
                    "recommendation_id": changed_recommendation["recommendation_id"],
                }
                if changed_recommendation
                else None
            ),
            "interpretation": "Held-fixed tests the original allocation under the changed factor without repair. Reoptimized reports a new matched-method search. Neither is a causal effect estimate.",
        }

    def compare(self, run_id: str, first_id: str, second_id: str) -> dict[str, Any]:
        records = {item["candidate_id"]: item for item in self.candidates(run_id)}
        missing = [item for item in (first_id, second_id) if item not in records]
        if missing:
            raise DashboardServiceError(
                "candidate_not_found", "Candidate does not belong to this run.", {"candidate_id": missing[0]}
            )
        first, second = records[first_id], records[second_id]
        if first["scenario_hash"] != second["scenario_hash"]:
            raise DashboardServiceError("scenario_mismatch", "Candidates belong to different scenarios.")
        config = _json(self._run_path(run_id) / "scenario_config.json")
        units = {item["name"]: item["unit"] for item in config["decision_variables"]}
        return {
            "run_id": run_id,
            "scenario_hash": first["scenario_hash"],
            "first_candidate_id": first_id,
            "second_candidate_id": second_id,
            "cost_delta": second["total_cost"] - first["total_cost"],
            "budget_remaining_delta": second["budget_remaining"] - first["budget_remaining"],
            "decision_deltas": [
                {
                    "name": name,
                    "first": first["decisions"][name],
                    "second": second["decisions"][name],
                    "delta": second["decisions"][name] - first["decisions"][name],
                    "unit": units[name],
                }
                for name in first["decisions"]
            ],
            "objective_deltas": [
                {
                    "name": name,
                    "first_benefit": first["objectives"][name]["benefit"],
                    "second_benefit": second["objectives"][name]["benefit"],
                    "delta": second["objectives"][name]["benefit"]
                    - first["objectives"][name]["benefit"],
                    "scale": "normalized benefit [0, 1]",
                }
                for name in first["objectives"]
            ],
        }

    def benchmark(self) -> dict[str, Any]:
        completion = _json(REPOSITORY_ROOT / FINAL_BENCHMARK_COMPLETION_PATH)
        root = REPOSITORY_ROOT / "results" / "benchmarks" / "phase6-final-synthetic-25seeds-v1"
        metrics = pd.read_csv(REPOSITORY_ROOT / FINAL_BENCHMARK_METRICS_PATH)
        return {
            "benchmark_id": "phase6-final-synthetic-25seeds-v1",
            "evidence_class": "synthetic_method_fixture",
            "configured_jobs": completion["configured_jobs"],
            "complete_jobs": completion["complete_jobs"],
            "failed_jobs": completion["failed_jobs"],
            "algorithms": sorted(metrics["algorithm"].unique()),
            "seeds": sorted(int(value) for value in metrics["seed"].unique()),
            "evaluation_budget": int(metrics["target_candidate_evaluations"].iloc[0]),
            "metrics_path": FINAL_BENCHMARK_METRICS_PATH.as_posix(),
            "statistics_path": "results/benchmarks/phase6-final-synthetic-25seeds-v1/statistical_tests.csv",
            "native_rion_openmp_built": False,
            "per_seed_metrics": _records(root / "per_seed_metrics.csv"),
            "summary": _records(root / "summary_median_iqr.csv"),
            "statistical_tests": _records(root / "statistical_tests.csv"),
            "metric_definitions": {
                "hypervolume": {
                    "direction": "higher",
                    "description": "Volume dominated by the feasible approximation set against the saved common reference point.",
                },
                "igd": {
                    "direction": "lower",
                    "description": "Average distance from the saved pooled reference front to the approximation set.",
                },
                "spacing": {
                    "direction": "lower",
                    "description": "Variation in nearest-neighbor distances within the approximation set.",
                },
                "feasible_solution_rate": {
                    "direction": "higher",
                    "description": "Share of evaluated candidates that satisfied the shared evaluator constraints.",
                },
                "archive_size": {
                    "direction": "context",
                    "description": "Number of retained nondominated feasible candidates; larger is not automatically better.",
                },
                "runtime_seconds": {
                    "direction": "lower",
                    "description": "Wall-clock runtime in the reported workspace; hardware-dependent.",
                },
            },
            "algorithm_explanations": {
                "nsga2": "Ranks nondominated fronts and uses crowding distance to preserve spread.",
                "nsga3": "Uses reference directions and niching to distribute candidates across objectives.",
                "moead": "Decomposes the multi-objective problem into neighboring scalar subproblems.",
                "mopso": "Uses an external archive and leader selection to guide a particle swarm.",
                "rion": "Combines particle-swarm exploration with NSGA-II style selection in the serial implementation used here.",
                "random_search": "Samples the supported decision space as a non-adaptive baseline.",
            },
            "claim_boundary": (
                "Synthetic method comparison only. No algorithm is a universal winner, and live interactive runs are not part of this study."
            ),
        }

    def evidence(self) -> dict[str, Any]:
        root = REPOSITORY_ROOT / "artifacts" / "evidence_modeling" / "vjti_v1"
        public_root = REPOSITORY_ROOT / "artifacts" / "public_data" / "vjti_ceit_v1"
        audit_root = REPOSITORY_ROOT / "artifacts" / "public_audit" / "vjti_v1"
        robustness_root = REPOSITORY_ROOT / "results" / "robustness" / "phase6b-synthetic-v1"
        public = _json(root / "public_evidence_assessment.json")
        dea = _json(root / "dea_summary.json")
        model_manifest = _json(root / "model_manifest.json")
        model_metrics = pd.read_csv(root / "model_metrics.csv")
        test_metrics = model_metrics[model_metrics["split"] == "test"]
        return {
            "evidence_class": "public_plus_synthetic_scenario",
            "public_dea": {
                "status": public["public_dea_status"],
                "complete_dmus": public["public_complete_dea_dmus"],
                "required_dmus": public["required_complete_dmus"],
                "reason": public["reason"],
            },
            "synthetic_dea": {
                "evidence_label": dea["evidence_label"],
                "dmu_count": dea["dmu_count"],
                "successful_solves": dea["successful_solves"],
                "failed_solves": dea["failed_solves"],
                "interpretation": dea["interpretation"],
            },
            "public_prediction_status": public["public_prediction_status"],
            "public_test_set_retained": public["public_test_set_retained"],
            "public_test_set_reason": public["public_test_set_reason"],
            "source_register": "artifacts/public_data/vjti_ceit_v1/source_register.csv",
            "model_manifest": "artifacts/evidence_modeling/vjti_v1/model_manifest.json",
            "sources": _records(public_root / "source_register.csv"),
            "data_dictionary": _records(public_root / "data_dictionary.csv"),
            "provenance_coverage": _records(public_root / "provenance_coverage.csv"),
            "missingness": _records(public_root / "missingness_report.csv"),
            "audit_checks": _records(audit_root / "audit_checks.csv"),
            "kpi_registry": _records(root / "kpi_evidence_registry.csv"),
            "model_test_metrics": json.loads(test_metrics.to_json(orient="records")),
            "interval_calibration": _records(root / "interval_calibration.csv"),
            "residual_diagnostics": _records(root / "residual_diagnostics.csv"),
            "model_interpretation": model_manifest["interpretation"],
            "model_validation_type": model_manifest["validation_type"],
            "model_target_count": len(model_manifest["target_columns"]),
            "selected_models": {
                name: details["model_name"]
                for name, details in model_manifest["selected_models"].items()
            },
            "training_support_by_target": model_manifest["training_support_by_target"],
            "robustness": {
                "evidence_class": "synthetic_method_fixture",
                "scenario_catalog": _records(robustness_root / "scenario_catalog.csv"),
                "fixed_vs_reoptimized": _records(
                    robustness_root / "fixed_vs_reoptimized_comparison.csv"
                ),
                "interpretation": (
                    "Held-fixed rows assess an unchanged saved strategy under a changed scenario. Reoptimized rows run a new search. Differences are modeled sensitivity, not causal effects."
                ),
            },
        }
