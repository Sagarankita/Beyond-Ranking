"""RION: a corrected NSGA-II loop with PSO-driven mutation."""

from __future__ import annotations

from typing import Callable, Sequence

import numpy as np
import pandas as pd


class RionOptimiser:
    """Hybrid multi-objective optimizer using minimization objectives."""

    def __init__(
        self,
        generations: int = 10,
        pop_size: int = 100,
        inertia: float = 1.0,
        self_confidence: float = 1.0,
        cross_confidence: float = 1.0,
        pso_iterations: int = 10,
        seed: int | None = None,
        pso_backend: str = "serial",
        crossover_probability: float = 0.3,
        penalty_weight: float = 1000.0,
    ):
        if generations < 0:
            raise ValueError("generations must be non-negative")
        if pop_size < 2:
            raise ValueError("pop_size must be at least 2")
        if pso_backend not in {"serial", "native"}:
            raise ValueError("pso_backend must be 'serial' or 'native'")
        self.generations = generations
        self.pop_size = pop_size
        self.pso_inertia = inertia
        self.pso_self_conf = self_confidence
        self.pso_cross_conf = cross_confidence
        self.pso_iterations = pso_iterations
        self.seed = seed
        self.pso_backend = pso_backend
        self.crossover_probability = crossover_probability
        self.penalty_weight = penalty_weight
        self.rng = np.random.default_rng(seed)

    def optimise(
        self,
        df: pd.DataFrame,
        optimiser_funcs: Sequence[Callable[[pd.Series], float]],
        constraints: Sequence[Sequence[float]],
        integer_columns: Sequence[str] | None = None,
        repair_func: Callable[[pd.Series], pd.Series] | None = None,
        constraint_violation_func: Callable[[pd.Series], float] | None = None,
        evaluation_phase_callback: Callable[[str], None] | None = None,
    ) -> pd.DataFrame:
        if df.empty:
            raise ValueError("df must contain at least one row")
        if not optimiser_funcs:
            raise ValueError("at least one objective function is required")
        if len(constraints) != len(df.columns):
            raise ValueError("constraints must contain one [min, max] pair per column")
        for lower, upper in constraints:
            if lower > upper:
                raise ValueError("constraint lower bounds must not exceed upper bounds")

        self.data = df.copy()
        self.optimiser_funcs = list(optimiser_funcs)
        self.constraints = [tuple(map(float, bound)) for bound in constraints]
        self.external_repair_func = repair_func
        self.external_constraint_violation_func = constraint_violation_func
        self.evaluation_phase_callback = evaluation_phase_callback
        inferred = [column for column in df.columns if pd.api.types.is_integer_dtype(df[column])]
        self.integer_columns = set(inferred if integer_columns is None else integer_columns)
        unknown = self.integer_columns.difference(df.columns)
        if unknown:
            raise ValueError(f"unknown integer columns: {sorted(unknown)}")

        population = self._generate_population(self.pop_size)
        if self.evaluation_phase_callback is not None:
            self.evaluation_phase_callback("evolution")
        for _ in range(self.generations):
            parent_fronts, parent_ranks = self._fast_non_dominated_sort(population)
            parent_crowding = self._crowding_distances_for_fronts(population, parent_fronts)
            offspring = self._generate_offspring(
                population, self.pop_size, parent_ranks, parent_crowding
            )
            combined = pd.concat([population, offspring], ignore_index=True)
            population = self._select_survivors(combined)
        return self._repair_population(population).reset_index(drop=True)

    def _pso_class(self):
        if self.pso_backend == "serial":
            from libRION.libPSO import PSO
        else:
            from libRION.libPSO_parallel import PSO
        return PSO

    def _generate_population(self, size: int) -> pd.DataFrame:
        indices = self.rng.integers(0, len(self.data), size=size)
        return self._repair_population(self.data.iloc[indices].reset_index(drop=True).copy())

    def _generate_offspring(self, population, size, ranks, crowding):
        children: list[pd.Series] = []
        while len(children) < size:
            first = self._tournament(ranks, crowding)
            second = self._tournament(ranks, crowding)
            while second == first:
                second = self._tournament(ranks, crowding)
            pair = population.iloc[[first, second]].copy().reset_index(drop=True)
            for column in pair.columns:
                if self.rng.random() < self.crossover_probability:
                    pair.loc[0, column], pair.loc[1, column] = (
                        pair.loc[1, column], pair.loc[0, column]
                    )
            children.append(pair.iloc[0].copy())
            if len(children) < size:
                children.append(pair.iloc[1].copy())
        offspring = pd.DataFrame(children, columns=population.columns)
        return self._pso_mutation(self._repair_population(offspring))

    def _tournament(self, ranks, crowding) -> int:
        if len(ranks) < 2:
            raise ValueError("tournament selection requires at least two candidates")
        a, b = self.rng.choice(len(ranks), size=2, replace=False)
        key_a, key_b = (ranks[a], -crowding[a]), (ranks[b], -crowding[b])
        if key_a == key_b:
            return int(a if self.rng.random() < 0.5 else b)
        return int(a if key_a < key_b else b)

    def _pso_mutation(self, offspring: pd.DataFrame) -> pd.DataFrame:
        if offspring.empty or self.pso_iterations == 0:
            return offspring
        column_index = int(self.rng.integers(0, len(offspring.columns)))
        column = offspring.columns[column_index]
        positions = offspring[[column]].to_numpy(dtype=np.float64)
        objective_matrix = np.array(
            [self._objective_values(row) for _, row in offspring.iterrows()]
        )
        ideals = np.min(objective_matrix, axis=0)
        scales = np.ptp(objective_matrix, axis=0)
        scales = np.where(scales > 1e-12, scales, np.maximum(np.abs(ideals), 1.0))

        def scalarized_objective(x, particle_index):
            candidate = offspring.iloc[particle_index].copy()
            candidate.iloc[column_index] = x[0]
            candidate = self._repair_individual(candidate)
            normalized = (self._objective_values(candidate) - ideals) / scales
            return float(
                np.sum(normalized)
                + self.penalty_weight * self._constraint_violate(candidate)
            )

        lower, upper = self.constraints[column_index]
        if self.evaluation_phase_callback is not None:
            self.evaluation_phase_callback("inner_pso")
        pso = None
        try:
            pso = self._pso_class()(
                obj_func=scalarized_objective,
                data=positions,
                num_particles=len(offspring),
                max_iter=self.pso_iterations,
                inertia_weight=self.pso_inertia,
                cognitive_coeff=self.pso_self_conf,
                social_coeff=self.pso_cross_conf,
                lower_bounds=np.array([lower]),
                upper_bounds=np.array([upper]),
                seed=int(self.rng.integers(0, np.iinfo(np.uint32).max)),
                objective_uses_particle_index=True,
            )
            pso.optimize()
            offspring[column] = pso.positions[:, 0]
        finally:
            if pso is not None:
                close = getattr(pso, "close", None)
                if close is not None:
                    close()
            if self.evaluation_phase_callback is not None:
                self.evaluation_phase_callback("evolution")
        return self._repair_population(offspring)

    def _select_survivors(self, combined):
        fronts, _ = self._fast_non_dominated_sort(combined)
        selected: list[int] = []
        for front in fronts:
            remaining = self.pop_size - len(selected)
            if remaining <= 0:
                break
            if len(front) <= remaining:
                selected.extend(front)
            else:
                selected.extend(self._crowding(combined, front)[:remaining])
                break
        if len(selected) != self.pop_size:
            raise RuntimeError("survivor selection did not produce the requested size")
        return combined.iloc[selected].reset_index(drop=True).copy()

    def _fast_non_dominated_sort(self, population):
        size = len(population)
        if size == 0:
            return [], []
        domination_count = [0] * size
        dominates: list[list[int]] = [[] for _ in range(size)]
        ranks = [-1] * size
        for i in range(size):
            for j in range(i + 1, size):
                if self._dominates(population.iloc[i], population.iloc[j]):
                    dominates[i].append(j)
                    domination_count[j] += 1
                elif self._dominates(population.iloc[j], population.iloc[i]):
                    dominates[j].append(i)
                    domination_count[i] += 1
        fronts = [[i for i, count in enumerate(domination_count) if count == 0]]
        for index in fronts[0]:
            ranks[index] = 0
        front_index = 0
        while front_index < len(fronts) and fronts[front_index]:
            next_front: list[int] = []
            for p in fronts[front_index]:
                for q in dominates[p]:
                    domination_count[q] -= 1
                    if domination_count[q] == 0:
                        ranks[q] = front_index + 1
                        next_front.append(q)
            if next_front:
                fronts.append(next_front)
            front_index += 1
        return fronts, ranks

    def _dominates(self, p, q) -> bool:
        p_violation, q_violation = self._constraint_violate(p), self._constraint_violate(q)
        p_feasible, q_feasible = p_violation <= 1e-12, q_violation <= 1e-12
        if p_feasible != q_feasible:
            return p_feasible
        if not p_feasible:
            return p_violation < q_violation - 1e-12
        p_values, q_values = self._objective_values(p), self._objective_values(q)
        return bool(np.all(p_values <= q_values) and np.any(p_values < q_values))

    def _objective_values(self, individual):
        values = np.array([func(individual) for func in self.optimiser_funcs], dtype=float)
        if not np.all(np.isfinite(values)):
            raise ValueError("all objective functions must return finite values")
        return values

    def _crowding_distance(self, population, front):
        distances = {index: 0.0 for index in front}
        if len(front) <= 2:
            return {index: float("inf") for index in front}
        objective_values = {idx: self._objective_values(population.iloc[idx]) for idx in front}
        for objective in range(len(self.optimiser_funcs)):
            ordered = sorted(front, key=lambda idx: objective_values[idx][objective])
            first = objective_values[ordered[0]][objective]
            last = objective_values[ordered[-1]][objective]
            distances[ordered[0]] = distances[ordered[-1]] = float("inf")
            if last > first:
                for position in range(1, len(ordered) - 1):
                    previous = objective_values[ordered[position - 1]][objective]
                    following = objective_values[ordered[position + 1]][objective]
                    distances[ordered[position]] += (following - previous) / (last - first)
        return distances

    def _crowding(self, population, front):
        distances = self._crowding_distance(population, front)
        return sorted(front, key=lambda idx: (-distances[idx], idx))

    def _crowding_distances_for_fronts(self, population, fronts):
        distances = [0.0] * len(population)
        for front in fronts:
            for index, value in self._crowding_distance(population, front).items():
                distances[index] = value
        return distances

    def _constraint_violate(self, individual) -> float:
        if getattr(self, "external_constraint_violation_func", None) is not None:
            violation = float(self.external_constraint_violation_func(individual))
            if not np.isfinite(violation) or violation < 0:
                raise ValueError("external constraint violation must be finite and non-negative")
            return violation
        total = 0.0
        for value, (lower, upper) in zip(individual, self.constraints):
            if not np.isfinite(value):
                return float("inf")
            scale = max(abs(lower), abs(upper), upper - lower, 1.0)
            total += max(0.0, lower - float(value)) / scale
            total += max(0.0, float(value) - upper) / scale
        return total / len(self.constraints)

    def _repair_individual(self, individual):
        repaired = individual.copy()
        for index, column in enumerate(repaired.index):
            lower, upper = self.constraints[index]
            value = float(np.clip(float(repaired[column]), lower, upper))
            if column in self.integer_columns:
                value = int(np.clip(np.rint(value), np.ceil(lower), np.floor(upper)))
            repaired[column] = value
        if getattr(self, "external_repair_func", None) is not None:
            external = self.external_repair_func(repaired.copy())
            repaired = pd.Series(external, index=repaired.index, dtype=float)
        return repaired

    def _repair_population(self, population):
        repaired = population.apply(self._repair_individual, axis=1)
        for column in self.integer_columns:
            repaired[column] = repaired[column].astype("int64")
        return repaired

    def evaluate_population(self, population):
        """Return objective values, feasibility, violation, rank, and crowding."""
        fronts, ranks = self._fast_non_dominated_sort(population)
        crowding = self._crowding_distances_for_fronts(population, fronts)
        records = []
        for index, (_, row) in enumerate(population.iterrows()):
            violation = self._constraint_violate(row)
            record = {
                f"objective_{i + 1}": value
                for i, value in enumerate(self._objective_values(row))
            }
            record.update(
                constraint_violation=violation,
                feasible=violation <= 1e-12,
                pareto_rank=ranks[index],
                crowding_distance=crowding[index],
            )
            records.append(record)
        return pd.DataFrame(records, index=population.index)
