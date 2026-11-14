from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query

from streamlit_app.api.schemas import (
    ComparisonRequest,
    ExplanationRequest,
    RunCreateRequest,
    ScenarioValidationRequest,
    SensitivityRequest,
)
from streamlit_app.api.service import DashboardRunService, DashboardServiceError


def create_app(service: DashboardRunService | None = None) -> FastAPI:
    owns_service = service is None
    run_service = service or DashboardRunService()

    @asynccontextmanager
    async def lifespan(_application: FastAPI):
        yield
        if owns_service:
            run_service.close()

    application = FastAPI(
        title="Beyond Ranking Dashboard API",
        version="1.0.0",
        description="Validated live-run adapter for the repository's canonical evaluators.",
        lifespan=lifespan,
    )
    application.state.run_service = run_service

    def handle(call):
        try:
            return call()
        except DashboardServiceError as exc:
            status = 404 if exc.code in {"run_not_found", "candidate_not_found", "recommendation_not_found", "sensitivity_not_found"} else 422
            raise HTTPException(status_code=status, detail=exc.detail()) from exc

    @application.get("/health")
    def health():
        return {"status": "ok", "service": "dashboard-live-run-v1"}

    @application.get("/config/defaults")
    def defaults(track: str = Query(default="vjti_public_plus_synthetic")):
        if track != "vjti_public_plus_synthetic":
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "unsupported_track",
                    "message": "Only the VJTI public-plus-synthetic track supports live runs.",
                    "fields": {"track": "unsupported"},
                },
            )
        return run_service.defaults()

    @application.post("/scenarios/validate")
    def validate_scenario(request: ScenarioValidationRequest):
        return run_service.validate_scenario(request)

    @application.post("/runs", status_code=202)
    def create_run(request: RunCreateRequest):
        return handle(lambda: run_service.create_run(request))

    @application.get("/runs/{run_id}")
    def get_run(run_id: str):
        return handle(lambda: run_service.get_run(run_id))

    @application.post("/runs/{run_id}/retry", status_code=202)
    def retry_run(run_id: str):
        return handle(lambda: run_service.retry_run(run_id))

    @application.get("/runs/{run_id}/candidates")
    def candidates(run_id: str):
        return handle(lambda: {"run_id": run_id, "candidates": run_service.candidates(run_id)})

    @application.get("/runs/{run_id}/recommendations")
    def recommendations(run_id: str):
        return handle(lambda: run_service.recommendations(run_id))

    @application.get("/explanations/status")
    def explanation_status():
        return run_service.explanation_status()

    @application.post("/runs/{run_id}/explanations")
    def explain(run_id: str, request: ExplanationRequest):
        return handle(
            lambda: run_service.explain(
                run_id, request.recommendation_id, request.language
            )
        )

    @application.post("/runs/{run_id}/sensitivity", status_code=202)
    def create_sensitivity(run_id: str, request: SensitivityRequest):
        return handle(lambda: run_service.create_sensitivity(run_id, request))

    @application.get("/runs/{run_id}/sensitivity/{sensitivity_run_id}")
    def sensitivity_result(run_id: str, sensitivity_run_id: str):
        return handle(lambda: run_service.sensitivity_result(run_id, sensitivity_run_id))

    @application.post("/comparisons")
    def compare(request: ComparisonRequest):
        return handle(
            lambda: run_service.compare(
                request.run_id, request.first_candidate_id, request.second_candidate_id
            )
        )

    @application.get("/benchmarks/final")
    def benchmark():
        return run_service.benchmark()

    @application.get("/evidence/summary")
    def evidence():
        return run_service.evidence()

    return application


app = create_app()
