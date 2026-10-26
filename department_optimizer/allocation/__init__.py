"""Shared mixed-variable allocation problem used by all optimizers."""

from .problem import (
    AllocationProblem,
    EvaluationResult,
    ProblemConfigurationError,
    evaluate,
)
from .optimizers import CanonicalNSGA2Adapter, RionAllocationAdapter
from .advanced_optimizers import (
    MOEADAdapter,
    MOPSOAdapter,
    NSGA3Adapter,
    RandomSearchAdapter,
)

__all__ = [
    "AllocationProblem",
    "EvaluationResult",
    "ProblemConfigurationError",
    "evaluate",
    "CanonicalNSGA2Adapter",
    "RionAllocationAdapter",
    "NSGA3Adapter",
    "MOEADAdapter",
    "MOPSOAdapter",
    "RandomSearchAdapter",
]
