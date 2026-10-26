"""Portable, deterministic particle-swarm optimizer."""

from __future__ import annotations

from typing import Callable

import numpy as np


class PSO:
    """Minimize a scalar function with a bounded particle swarm.

    ``objective_uses_particle_index`` lets RION evaluate particle ``p`` in the
    context of candidate row ``p``, instead of sharing row zero's context.
    """

    def __init__(
        self,
        obj_func: Callable[..., float],
        data,
        num_particles: int | None = None,
        max_iter: int = 100,
        inertia_weight: float = 0.5,
        cognitive_coeff: float = 1.5,
        social_coeff: float = 1.5,
        lower_bounds=None,
        upper_bounds=None,
        seed: int | None = None,
        objective_uses_particle_index: bool = False,
    ):
        self.obj_func = obj_func
        self.positions = np.asarray(data, dtype=np.float64).copy()
        if self.positions.ndim != 2 or not self.positions.size:
            raise ValueError("data must be a non-empty 2D array")

        actual_particles, self.dim = self.positions.shape
        self.num_particles = actual_particles if num_particles is None else num_particles
        if self.num_particles != actual_particles:
            raise ValueError("num_particles must match the number of data rows")
        if max_iter < 0:
            raise ValueError("max_iter must be non-negative")

        self.max_iter = max_iter
        self.inertia_weight = inertia_weight
        self.cognitive_coeff = cognitive_coeff
        self.social_coeff = social_coeff
        self.objective_uses_particle_index = objective_uses_particle_index
        self.rng = np.random.default_rng(seed)

        data_min = np.min(self.positions, axis=0)
        data_max = np.max(self.positions, axis=0)
        data_range = data_max - data_min
        self.lower_bounds = np.asarray(
            data_min - 0.5 * data_range if lower_bounds is None else lower_bounds,
            dtype=np.float64,
        )
        self.upper_bounds = np.asarray(
            data_max + 0.5 * data_range if upper_bounds is None else upper_bounds,
            dtype=np.float64,
        )
        if self.lower_bounds.shape != (self.dim,) or self.upper_bounds.shape != (self.dim,):
            raise ValueError("bounds must contain one value per dimension")
        if np.any(self.lower_bounds > self.upper_bounds):
            raise ValueError("lower bounds must not exceed upper bounds")

        self.positions = np.clip(self.positions, self.lower_bounds, self.upper_bounds)
        self.vmax = 0.2 * (self.upper_bounds - self.lower_bounds)
        self.velocities = self.rng.uniform(-1.0, 1.0, self.positions.shape)
        self.velocities = np.clip(self.velocities, -self.vmax, self.vmax)
        self.personal_best_positions = self.positions.copy()
        self.personal_best_scores = np.array(
            [self._score(position, p) for p, position in enumerate(self.positions)]
        )
        best_index = int(np.argmin(self.personal_best_scores))
        self.global_best_position = self.personal_best_positions[best_index].copy()
        self.global_best_score = float(self.personal_best_scores[best_index])

    def _score(self, position: np.ndarray, particle_index: int) -> float:
        score = (
            self.obj_func(position, particle_index)
            if self.objective_uses_particle_index
            else self.obj_func(position)
        )
        score = float(score)
        if not np.isfinite(score):
            raise ValueError("objective function returned a non-finite score")
        return score

    def optimize(self):
        for _ in range(self.max_iter):
            # Synchronous PSO semantics: every particle in this iteration sees the
            # same frozen global best. Personal/global bests are reduced afterwards.
            global_best_snapshot = self.global_best_position.copy()
            for p in range(self.num_particles):
                r1 = self.rng.random(self.dim)
                r2 = self.rng.random(self.dim)
                cognitive = self.cognitive_coeff * r1 * (
                    self.personal_best_positions[p] - self.positions[p]
                )
                social = self.social_coeff * r2 * (
                    global_best_snapshot - self.positions[p]
                )
                self.velocities[p] = np.clip(
                    self.inertia_weight * self.velocities[p] + cognitive + social,
                    -self.vmax,
                    self.vmax,
                )
                self.positions[p] = np.clip(
                    self.positions[p] + self.velocities[p],
                    self.lower_bounds,
                    self.upper_bounds,
                )
                score = self._score(self.positions[p], p)
                if score < self.personal_best_scores[p]:
                    self.personal_best_scores[p] = score
                    self.personal_best_positions[p] = self.positions[p].copy()
            best_index = int(np.argmin(self.personal_best_scores))
            self.global_best_score = float(self.personal_best_scores[best_index])
            self.global_best_position = self.personal_best_positions[best_index].copy()
        return self.global_best_position.copy(), self.global_best_score
