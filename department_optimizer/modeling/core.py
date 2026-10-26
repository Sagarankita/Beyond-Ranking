"""Shared modeling, splitting, metric, and uncertainty helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


class ModelingDataError(ValueError):
    """Raised when data cannot support the configured response-model track."""


@dataclass(frozen=True)
class SplitDefinition:
    train: np.ndarray
    validation: np.ndarray
    calibration: np.ndarray
    test: np.ndarray

    def items(self):
        return (
            ("train", self.train),
            ("validation", self.validation),
            ("calibration", self.calibration),
            ("test", self.test),
        )


def validate_modeling_frame(frame: pd.DataFrame, config: dict):
    features = list(config["feature_columns"])
    targets = list(config["target_columns"])
    forbidden = set(config.get("forbidden_feature_columns", ()))
    overlap = sorted(set(features).intersection(targets) | set(features).intersection(forbidden))
    if overlap:
        raise ModelingDataError(f"target leakage or forbidden model features: {overlap}")
    required = {config["id_column"], *features, *targets}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ModelingDataError(f"missing modeling columns: {missing}")
    if frame[config["id_column"]].isna().any() or frame[config["id_column"]].duplicated().any():
        raise ModelingDataError("modeling identifiers must be present and unique")
    numeric = frame[features + targets].apply(pd.to_numeric, errors="coerce")
    bad_targets = [name for name in targets if numeric[name].isna().any()]
    if bad_targets:
        raise ModelingDataError(f"targets must be complete and numeric: {bad_targets}")
    finite_targets = np.isfinite(numeric[targets].to_numpy(dtype=float)).all(axis=0)
    if not finite_targets.all():
        bad = [targets[i] for i, valid in enumerate(finite_targets) if not valid]
        raise ModelingDataError(f"targets contain non-finite values: {bad}")
    all_missing_features = [name for name in features if numeric[name].isna().all()]
    if all_missing_features:
        raise ModelingDataError(f"features cannot be entirely missing: {all_missing_features}")
    feature_values = numeric[features].to_numpy(dtype=float)
    if np.isinf(feature_values).any():
        bad = [features[i] for i in np.flatnonzero(np.isinf(feature_values).any(axis=0))]
        raise ModelingDataError(f"features contain infinite values: {bad}")
    for target, bounds in config.get("target_bounds", {}).items():
        lower, upper = bounds
        if lower is not None and (numeric[target] < lower).any():
            raise ModelingDataError(f"target {target} is below configured lower bound {lower}")
        if upper is not None and (numeric[target] > upper).any():
            raise ModelingDataError(f"target {target} is above configured upper bound {upper}")
    return numeric


def deterministic_split(count: int, split_config: dict) -> SplitDefinition:
    if count < 20:
        raise ModelingDataError("at least 20 rows are required for four-way model validation")
    names = ("train", "validation", "calibration", "test")
    fractions = np.array([float(split_config[f"{name}_fraction"]) for name in names])
    if np.any(fractions <= 0) or not np.isclose(fractions.sum(), 1.0):
        raise ModelingDataError("split fractions must be positive and sum to one")
    rng = np.random.default_rng(int(split_config["model_seed"]))
    shuffled = rng.permutation(count)
    boundaries = np.floor(np.cumsum(fractions[:-1]) * count).astype(int)
    groups = np.split(shuffled, boundaries)
    if any(len(group) < 2 for group in groups):
        raise ModelingDataError("each train/validation/calibration/test split needs at least two rows")
    return SplitDefinition(*groups)


def regression_metrics(actual, predicted):
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    residual = actual - predicted
    return {
        "mae": float(np.mean(np.abs(residual))),
        "rmse": float(np.sqrt(np.mean(residual**2))),
    }


def residual_diagnostics(actual, predicted):
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    residual = actual - predicted
    correlation = 0.0
    if np.std(predicted) > 0 and np.std(residual) > 0:
        correlation = float(np.corrcoef(predicted, residual)[0, 1])
    return {
        "residual_mean": float(np.mean(residual)),
        "residual_median": float(np.median(residual)),
        "residual_std": float(np.std(residual)),
        "residual_p05": float(np.quantile(residual, 0.05)),
        "residual_p95": float(np.quantile(residual, 0.95)),
        "residual_prediction_correlation": correlation,
    }


def conformal_radius(actual, predicted, alpha: float):
    if not 0 < alpha < 1:
        raise ValueError("miscoverage alpha must be between zero and one")
    scores = np.abs(np.asarray(actual, dtype=float) - np.asarray(predicted, dtype=float))
    level = min(1.0, math.ceil((len(scores) + 1) * (1 - alpha)) / len(scores))
    try:
        return float(np.quantile(scores, level, method="higher"))
    except TypeError:  # NumPy < 1.22 compatibility
        return float(np.quantile(scores, level, interpolation="higher"))


def bounded_interval(prediction, radius: float, bounds):
    prediction = np.asarray(prediction, dtype=float)
    lower = prediction - radius
    upper = prediction + radius
    bound_lower, bound_upper = bounds
    if bound_lower is not None:
        lower = np.maximum(lower, bound_lower)
    if bound_upper is not None:
        upper = np.minimum(upper, bound_upper)
    return lower, upper
