"""Frozen multi-objective metric definitions used by the benchmark runner."""

from __future__ import annotations

import numpy as np


def nondominated(points):
    """Return unique nondominated rows for a minimization problem."""
    values = np.asarray(points, dtype=float)
    if values.size == 0:
        width = values.shape[1] if values.ndim == 2 else 0
        return np.empty((0, width), dtype=float)
    if values.ndim != 2 or not np.isfinite(values).all():
        raise ValueError("points must be a finite two-dimensional array")
    values = np.unique(values, axis=0)
    keep = np.ones(len(values), dtype=bool)
    for index, point in enumerate(values):
        dominated_by_other = np.any(
            np.all(values <= point, axis=1) & np.any(values < point, axis=1)
        )
        keep[index] = not dominated_by_other
    return values[keep]


def hypervolume(points, reference_point):
    """Exact dominated hypervolume by recursive slicing (minimization)."""
    reference = np.asarray(reference_point, dtype=float)
    values = np.asarray(points, dtype=float)
    if values.size == 0:
        return 0.0
    if values.ndim != 2 or values.shape[1] != len(reference):
        raise ValueError("point dimension must match the reference point")
    values = values[np.all(values < reference, axis=1)]
    if len(values) == 0:
        return 0.0
    values = nondominated(values)
    if values.shape[1] == 1:
        return float(reference[0] - np.min(values[:, 0]))
    volume = 0.0
    levels = np.unique(values[:, -1])
    for index, level in enumerate(levels):
        upper = levels[index + 1] if index + 1 < len(levels) else reference[-1]
        if upper <= level:
            continue
        cross_section = values[values[:, -1] <= level, :-1]
        volume += hypervolume(cross_section, reference[:-1]) * (upper - level)
    return float(volume)


def igd(points, reference_front):
    """Mean distance from each reference-front point to the approximation."""
    values = np.asarray(points, dtype=float)
    reference = np.asarray(reference_front, dtype=float)
    if len(values) == 0 or len(reference) == 0:
        return float("nan")
    distances = np.linalg.norm(reference[:, None, :] - values[None, :, :], axis=2)
    return float(np.min(distances, axis=1).mean())


def spacing(points):
    """Sample SD of nearest-neighbour distances; lower is more even."""
    values = np.asarray(points, dtype=float)
    if len(values) < 2:
        return 0.0 if len(values) == 1 else float("nan")
    distances = np.linalg.norm(values[:, None, :] - values[None, :, :], axis=2)
    np.fill_diagonal(distances, np.inf)
    nearest = np.min(distances, axis=1)
    return float(np.std(nearest, ddof=1))


def normalize_objectives(points, lower, upper, clip=True):
    values = np.asarray(points, dtype=float)
    low = np.asarray(lower, dtype=float)
    high = np.asarray(upper, dtype=float)
    if np.any(high <= low):
        raise ValueError("every objective upper bound must exceed its lower bound")
    normalized = (values - low) / (high - low)
    return np.clip(normalized, 0.0, 1.0) if clip else normalized
