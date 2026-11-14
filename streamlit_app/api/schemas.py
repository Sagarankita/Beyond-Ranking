from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


AlgorithmName = Literal["nsga2", "nsga3", "moead", "mopso", "rion", "random_search"]
RecommendationProfile = Literal[
    "balanced",
    "research_focused",
    "innovation_focused",
    "student_focused",
    "robust",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScenarioOverrides(StrictModel):
    budget_limit: float | None = Field(default=None, gt=0)
    budget_unit: Literal["INR"] = "INR"
    faculty_total: float | None = Field(default=None, gt=0)
    faculty_unit: Literal["annual FTE"] = "annual FTE"
    cost_multipliers: dict[str, float] = Field(default_factory=dict)

    @field_validator("cost_multipliers")
    @classmethod
    def validate_multipliers(cls, value: dict[str, float]) -> dict[str, float]:
        if len(value) > 12:
            raise ValueError("at most 12 cost multipliers are allowed")
        for name, multiplier in value.items():
            if not name or not 0.1 <= float(multiplier) <= 10.0:
                raise ValueError("cost multipliers must be between 0.1 and 10")
        return value


class ScenarioValidationRequest(StrictModel):
    track_id: Literal["vjti_public_plus_synthetic"] = "vjti_public_plus_synthetic"
    overrides: ScenarioOverrides = Field(default_factory=ScenarioOverrides)


class RunCreateRequest(ScenarioValidationRequest):
    algorithm: AlgorithmName = "nsga2"
    seed: int = Field(default=18001, ge=0, le=2_147_483_647)
    evaluation_budget: int = Field(default=16, ge=2, le=10_000)


class ComparisonRequest(StrictModel):
    run_id: str = Field(min_length=12, max_length=64)
    first_candidate_id: str = Field(min_length=12, max_length=64)
    second_candidate_id: str = Field(min_length=12, max_length=64)


class SensitivityRequest(StrictModel):
    factor: Literal["budget_limit", "faculty_total"]
    new_value: float = Field(gt=0)
    profile: RecommendationProfile = "balanced"


class ExplanationRequest(StrictModel):
    recommendation_id: str = Field(min_length=12, max_length=64)
    language: Literal["en"] = "en"

