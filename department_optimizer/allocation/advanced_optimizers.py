"""NSGA-III, MOEA/D, archive-based MOPSO, and random-search adapters."""

from __future__ import annotations

from itertools import combinations

import numpy as np

from .optimizers import (
    AlgorithmResult,
    EvaluationCache,
    _crowding,
    _dominates,
    _flatten,
    _fronts,
    _polynomial_mutation,
    _rank_and_crowding,
    _repair_vector,
    _sample,
    _sbx,
    _tournament,
)
from .problem import OBJECTIVE_FAMILIES, AllocationProblem, EvaluationResult


def das_dennis_reference_directions(objectives: int, partitions: int):
    """Return deterministic simplex-lattice reference directions."""
    if objectives < 2 or partitions < 1:
        raise ValueError("reference directions need at least two objectives and one partition")
    directions = []
    for dividers in combinations(range(partitions + objectives - 1), objectives - 1):
        edges = (-1, *dividers, partitions + objectives - 1)
        composition = [edges[i + 1] - edges[i] - 1 for i in range(objectives)]
        directions.append(np.asarray(composition, dtype=float) / partitions)
    return np.asarray(directions)


def associate_to_reference_directions(values, directions):
    values = np.asarray(values, dtype=float)
    ideal = np.min(values, axis=0)
    nadir = np.max(values, axis=0)
    span = np.where(nadir - ideal > 1e-12, nadir - ideal, 1.0)
    normalized = (values - ideal) / span
    unit = directions / np.linalg.norm(directions, axis=1, keepdims=True)
    projections = normalized @ unit.T
    projected = projections[:, :, None] * unit[None, :, :]
    distances = np.linalg.norm(normalized[:, None, :] - projected, axis=2)
    niche = np.argmin(distances, axis=1)
    return niche, distances[np.arange(len(values)), niche], distances


def nsga3_survival(evaluations, count, directions, rng):
    fronts, _ = _fronts(evaluations)
    selected = []
    split_front = None
    for front in fronts:
        if len(selected) + len(front) <= count:
            selected.extend(front)
        else:
            split_front = list(front)
            break
    if len(selected) == count or split_front is None:
        return selected[:count]

    all_values = np.array([item.objective_vector() for item in evaluations])
    niche, distance, _ = associate_to_reference_directions(all_values, directions)
    niche_count = np.zeros(len(directions), dtype=int)
    for index in selected:
        niche_count[niche[index]] += 1
    available = set(split_front)
    while len(selected) < count and available:
        available_niches = sorted({int(niche[index]) for index in available})
        minimum = min(niche_count[index] for index in available_niches)
        candidate_niches = [index for index in available_niches if niche_count[index] == minimum]
        chosen_niche = int(rng.choice(candidate_niches))
        candidates = [index for index in available if niche[index] == chosen_niche]
        if niche_count[chosen_niche] == 0:
            chosen = min(candidates, key=lambda index: (distance[index], index))
        else:
            chosen = int(rng.choice(candidates))
        selected.append(chosen)
        available.remove(chosen)
        niche_count[chosen_niche] += 1
    return selected


class NSGA3Adapter:
    name = "nsga3"

    def __init__(self, reference_partitions=3, generations=4, seed=42):
        self.reference_partitions = int(reference_partitions)
        self.directions = das_dennis_reference_directions(
            len(OBJECTIVE_FAMILIES), self.reference_partitions
        )
        self.population_size = len(self.directions)
        self.generations = int(generations)
        self.seed = int(seed)

    def run(self, problem: AllocationProblem):
        rng = np.random.default_rng(self.seed)
        cache = EvaluationCache(problem)
        vectors = _sample(problem, rng, self.population_size)
        evaluations = [cache.evaluate(vector) for vector in vectors]
        lower = np.array([float(item["lower"]) for item in problem.variables])
        upper = np.array([float(item["upper"]) for item in problem.variables])
        for _ in range(self.generations):
            cache.set_phase("evolution")
            _, ranks, crowding = _rank_and_crowding(evaluations)
            children = []
            while len(children) < self.population_size:
                first = vectors[_tournament(rng, ranks, crowding)]
                second = vectors[_tournament(rng, ranks, crowding)]
                child_a, child_b = _sbx(first, second, lower, upper, rng)
                children.append(
                    _repair_vector(
                        problem, _polynomial_mutation(child_a, lower, upper, rng)
                    )
                )
                if len(children) < self.population_size:
                    children.append(
                        _repair_vector(
                            problem, _polynomial_mutation(child_b, lower, upper, rng)
                        )
                    )
            child_vectors = np.asarray(children)
            child_evaluations = [cache.evaluate(vector) for vector in child_vectors]
            combined_vectors = np.vstack([vectors, child_vectors])
            combined_evaluations = evaluations + child_evaluations
            selected = nsga3_survival(
                combined_evaluations, self.population_size, self.directions, rng
            )
            vectors = combined_vectors[selected]
            evaluations = [combined_evaluations[index] for index in selected]
        population, archive = _flatten(problem, vectors, evaluations, self.name, self.seed)
        accounting = cache.summary()
        accounting.update(
            algorithm=self.name,
            population_size=self.population_size,
            generations=self.generations,
            reference_partitions=self.reference_partitions,
            reference_direction_count=len(self.directions),
            reference_directions=self.directions.tolist(),
            inner_pso_evaluations=0,
            candidate_evaluations_initialization=self.population_size,
            candidate_evaluations_evolution=self.population_size * self.generations,
            candidate_evaluations_inner_pso=0,
            candidate_evaluations_total=self.population_size * (self.generations + 1),
        )
        return AlgorithmResult(population, archive, accounting)


def tchebycheff(objectives, weight, ideal):
    return float(np.max(np.maximum(weight, 1e-6) * np.abs(objectives - ideal)))


class MOEADAdapter:
    name = "moead"

    def __init__(
        self,
        reference_partitions=3,
        neighborhood_size=5,
        max_replacements=2,
        generations=4,
        seed=42,
    ):
        self.reference_partitions = int(reference_partitions)
        self.directions = das_dennis_reference_directions(
            len(OBJECTIVE_FAMILIES), self.reference_partitions
        )
        self.population_size = len(self.directions)
        self.neighborhood_size = int(neighborhood_size)
        self.max_replacements = int(max_replacements)
        self.generations = int(generations)
        self.seed = int(seed)
        if not 2 <= self.neighborhood_size <= self.population_size:
            raise ValueError("MOEA/D neighborhood_size must be between 2 and population size")
        if self.max_replacements < 1:
            raise ValueError("MOEA/D max_replacements must be positive")

    def run(self, problem: AllocationProblem):
        rng = np.random.default_rng(self.seed)
        cache = EvaluationCache(problem)
        vectors = _sample(problem, rng, self.population_size)
        evaluations = [cache.evaluate(vector) for vector in vectors]
        distances = np.linalg.norm(
            self.directions[:, None, :] - self.directions[None, :, :], axis=2
        )
        neighborhoods = np.argsort(distances, axis=1)[:, : self.neighborhood_size]
        lower = np.array([float(item["lower"]) for item in problem.variables])
        upper = np.array([float(item["upper"]) for item in problem.variables])
        ideal = np.min(np.array([item.objective_vector() for item in evaluations]), axis=0)
        for _ in range(self.generations):
            cache.set_phase("evolution")
            for subproblem in rng.permutation(self.population_size):
                parents = rng.choice(neighborhoods[subproblem], size=2, replace=False)
                child, _ = _sbx(vectors[parents[0]], vectors[parents[1]], lower, upper, rng)
                child = _repair_vector(
                    problem, _polynomial_mutation(child, lower, upper, rng)
                )
                child_evaluation = cache.evaluate(child)
                ideal = np.minimum(ideal, child_evaluation.objective_vector())
                replacements = 0
                for neighbor in rng.permutation(neighborhoods[subproblem]):
                    existing = evaluations[neighbor]
                    replace = _dominates(child_evaluation, existing)
                    if (
                        not replace
                        and child_evaluation.normalized_violation <= 1e-12
                        and existing.normalized_violation <= 1e-12
                    ):
                        replace = tchebycheff(
                            child_evaluation.objective_vector(),
                            self.directions[neighbor],
                            ideal,
                        ) < tchebycheff(
                            existing.objective_vector(), self.directions[neighbor], ideal
                        )
                    if replace:
                        vectors[neighbor] = child
                        evaluations[neighbor] = child_evaluation
                        replacements += 1
                    if replacements >= self.max_replacements:
                        break
        population, archive = _flatten(problem, vectors, evaluations, self.name, self.seed)
        accounting = cache.summary()
        accounting.update(
            algorithm=self.name,
            population_size=self.population_size,
            generations=self.generations,
            decomposition="weighted_tchebycheff",
            reference_partitions=self.reference_partitions,
            reference_direction_count=len(self.directions),
            reference_directions=self.directions.tolist(),
            neighborhood_size=self.neighborhood_size,
            neighborhoods=neighborhoods.tolist(),
            maximum_replacements_per_offspring=self.max_replacements,
            inner_pso_evaluations=0,
            candidate_evaluations_initialization=self.population_size,
            candidate_evaluations_evolution=self.population_size * self.generations,
            candidate_evaluations_inner_pso=0,
            candidate_evaluations_total=self.population_size * (self.generations + 1),
        )
        return AlgorithmResult(population, archive, accounting)


def update_external_archive(vectors, evaluations, archive_size):
    """Repair-independent archive update over already repaired vectors."""
    unique = {}
    for vector, evaluation in zip(vectors, evaluations):
        key = tuple(float(value) for value in vector)
        if key not in unique:
            unique[key] = (np.asarray(vector, dtype=float).copy(), evaluation)
    pairs = list(unique.values())
    pair_evaluations = [item[1] for item in pairs]
    fronts, _ = _fronts(pair_evaluations)
    nondominated = [pairs[index] for index in fronts[0]] if fronts else []
    while len(nondominated) > archive_size:
        distances = _crowding(
            [item[1] for item in nondominated], list(range(len(nondominated)))
        )
        removable = [index for index, value in distances.items() if np.isfinite(value)]
        if not removable:
            removable = list(range(len(nondominated)))
        remove = min(removable, key=lambda index: (distances[index], index))
        nondominated.pop(remove)
    return (
        np.asarray([item[0] for item in nondominated], dtype=float),
        [item[1] for item in nondominated],
    )


def select_crowding_leader(archive_evaluations, rng):
    if not archive_evaluations:
        raise ValueError("MOPSO cannot select a leader from an empty archive")
    if len(archive_evaluations) == 1:
        return 0
    distances = _crowding(
        archive_evaluations, list(range(len(archive_evaluations)))
    )
    first, second = rng.choice(len(archive_evaluations), size=2, replace=False)
    first_distance, second_distance = distances[first], distances[second]
    if first_distance == second_distance:
        return int(first if rng.random() < 0.5 else second)
    return int(first if first_distance > second_distance else second)


class MOPSOAdapter:
    name = "mopso"

    def __init__(
        self,
        population_size=20,
        generations=4,
        archive_size=20,
        inertia=0.6,
        cognitive=1.5,
        social=1.5,
        maximum_velocity_rate=0.2,
        seed=42,
    ):
        if population_size < 2 or archive_size < 1:
            raise ValueError("MOPSO needs at least two particles and a positive archive")
        self.population_size = int(population_size)
        self.generations = int(generations)
        self.archive_size = int(archive_size)
        self.inertia = float(inertia)
        self.cognitive = float(cognitive)
        self.social = float(social)
        self.maximum_velocity_rate = float(maximum_velocity_rate)
        self.seed = int(seed)

    def run(self, problem: AllocationProblem):
        rng = np.random.default_rng(self.seed)
        cache = EvaluationCache(problem)
        lower = np.array([float(item["lower"]) for item in problem.variables])
        upper = np.array([float(item["upper"]) for item in problem.variables])
        velocity_limit = self.maximum_velocity_rate * (upper - lower)
        vectors = _sample(problem, rng, self.population_size)
        evaluations = [cache.evaluate(vector) for vector in vectors]
        velocities = rng.uniform(-velocity_limit, velocity_limit, vectors.shape)
        personal_vectors = vectors.copy()
        personal_evaluations = list(evaluations)
        archive_vectors, archive_evaluations = update_external_archive(
            vectors, evaluations, self.archive_size
        )
        for _ in range(self.generations):
            cache.set_phase("evolution")
            new_vectors = []
            for particle in range(self.population_size):
                leader_index = select_crowding_leader(archive_evaluations, rng)
                leader = archive_vectors[leader_index]
                r1, r2 = rng.random(len(lower)), rng.random(len(lower))
                velocities[particle] = np.clip(
                    self.inertia * velocities[particle]
                    + self.cognitive * r1 * (personal_vectors[particle] - vectors[particle])
                    + self.social * r2 * (leader - vectors[particle]),
                    -velocity_limit,
                    velocity_limit,
                )
                moved = np.clip(vectors[particle] + velocities[particle], lower, upper)
                new_vectors.append(_repair_vector(problem, moved))
            vectors = np.asarray(new_vectors)
            evaluations = [cache.evaluate(vector) for vector in vectors]
            for particle, current in enumerate(evaluations):
                previous = personal_evaluations[particle]
                if _dominates(current, previous):
                    choose_current = True
                elif _dominates(previous, current):
                    choose_current = False
                else:
                    combined = [previous, current]
                    distance = _crowding(combined, [0, 1])
                    choose_current = (
                        distance[1] > distance[0]
                        or (distance[1] == distance[0] and rng.random() < 0.5)
                    )
                if choose_current:
                    personal_vectors[particle] = vectors[particle]
                    personal_evaluations[particle] = current
            merged_vectors = np.vstack([archive_vectors, vectors])
            merged_evaluations = archive_evaluations + evaluations
            archive_vectors, archive_evaluations = update_external_archive(
                merged_vectors, merged_evaluations, self.archive_size
            )
        population, _ = _flatten(problem, vectors, evaluations, self.name, self.seed)
        _, archive = _flatten(
            problem, archive_vectors, archive_evaluations, self.name, self.seed
        )
        accounting = cache.summary()
        accounting.update(
            algorithm=self.name,
            population_size=self.population_size,
            generations=self.generations,
            archive_capacity=self.archive_size,
            final_archive_size=len(archive),
            leader_selection="binary_tournament_higher_crowding_distance",
            archive_pruning="nondominated_deduplicate_then_crowding",
            inertia=self.inertia,
            cognitive=self.cognitive,
            social=self.social,
            maximum_velocity_rate=self.maximum_velocity_rate,
            particle_update_evaluations=int(self.population_size * self.generations),
            inner_pso_evaluations=0,
            candidate_evaluations_initialization=self.population_size,
            candidate_evaluations_evolution=self.population_size * self.generations,
            candidate_evaluations_inner_pso=0,
            candidate_evaluations_total=self.population_size * (self.generations + 1),
        )
        return AlgorithmResult(population, archive, accounting)


class RandomSearchAdapter:
    name = "random_search"

    def __init__(self, evaluations=100, seed=42):
        if evaluations < 2:
            raise ValueError("random search needs at least two evaluations")
        self.evaluations = int(evaluations)
        self.seed = int(seed)

    def run(self, problem: AllocationProblem):
        rng = np.random.default_rng(self.seed)
        cache = EvaluationCache(problem)
        vectors = _sample(problem, rng, self.evaluations)
        evaluations = [cache.evaluate(vector) for vector in vectors]
        population, archive = _flatten(
            problem, vectors, evaluations, self.name, self.seed
        )
        accounting = cache.summary()
        accounting.update(
            algorithm=self.name,
            population_size=len(population),
            generations=0,
            configured_evaluations=self.evaluations,
            inner_pso_evaluations=0,
            candidate_evaluations_initialization=self.evaluations,
            candidate_evaluations_evolution=0,
            candidate_evaluations_inner_pso=0,
            candidate_evaluations_total=self.evaluations,
        )
        return AlgorithmResult(population, archive, accounting)
