from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx


DEFAULT_API_URL = "http://127.0.0.1:8000"


@dataclass(frozen=True)
class DashboardApiError(RuntimeError):
    message: str
    code: str = "api_error"
    fields: dict[str, str] | None = None
    status_code: int | None = None

    def __str__(self) -> str:
        return self.message


class DashboardApiClient:
    """Small HTTP client for the Prompt 2 API. It contains no evaluator logic."""

    def __init__(self, base_url: str | None = None, timeout: float = 15.0):
        self.base_url = (base_url or os.environ.get("DASHBOARD_API_URL", DEFAULT_API_URL)).rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = httpx.request(
                method,
                f"{self.base_url}{path}",
                timeout=self.timeout,
                **kwargs,
            )
        except httpx.RequestError as exc:
            raise DashboardApiError(
                f"The optimization API is unavailable at {self.base_url}.",
                code="api_unavailable",
            ) from exc
        if response.is_error:
            try:
                detail = response.json().get("detail", {})
            except ValueError:
                detail = {}
            if not isinstance(detail, dict):
                detail = {"message": str(detail)}
            raise DashboardApiError(
                str(detail.get("message", f"API request failed with status {response.status_code}.")),
                code=str(detail.get("code", "api_error")),
                fields=detail.get("fields") if isinstance(detail.get("fields"), dict) else {},
                status_code=response.status_code,
            )
        return response.json()

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def defaults(self) -> dict[str, Any]:
        return self._request("GET", "/config/defaults")

    def validate(self, overrides: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            "/scenarios/validate",
            json={"track_id": "vjti_public_plus_synthetic", "overrides": overrides},
        )

    def create_run(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/runs", json=request)

    def run_status(self, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/runs/{run_id}")

    def candidates(self, run_id: str) -> list[dict[str, Any]]:
        return self._request("GET", f"/runs/{run_id}/candidates")["candidates"]

    def recommendations(self, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/runs/{run_id}/recommendations")

    def explanation_status(self) -> dict[str, Any]:
        return self._request("GET", "/explanations/status")

    def explain(self, run_id: str, recommendation_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/runs/{run_id}/explanations",
            json={"recommendation_id": recommendation_id, "language": "en"},
        )

    def create_sensitivity(
        self, run_id: str, factor: str, new_value: float, profile: str
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/runs/{run_id}/sensitivity",
            json={"factor": factor, "new_value": new_value, "profile": profile},
        )

    def sensitivity_result(self, run_id: str, sensitivity_run_id: str) -> dict[str, Any]:
        return self._request(
            "GET", f"/runs/{run_id}/sensitivity/{sensitivity_run_id}"
        )

    def comparison(self, run_id: str, first: str, second: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/comparisons",
            json={
                "run_id": run_id,
                "first_candidate_id": first,
                "second_candidate_id": second,
            },
        )

    def evidence(self) -> dict[str, Any]:
        return self._request("GET", "/evidence/summary")

    def benchmark(self) -> dict[str, Any]:
        return self._request("GET", "/benchmarks/final")

    def wait_for_run(
        self,
        run_id: str,
        *,
        timeout_seconds: float = 60.0,
        interval_seconds: float = 0.25,
        on_status: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        status = self.run_status(run_id)
        while status["status"] in {"queued", "running"} and time.monotonic() < deadline:
            if on_status is not None:
                on_status(status)
            time.sleep(interval_seconds)
            status = self.run_status(run_id)
        if on_status is not None:
            on_status(status)
        return status
