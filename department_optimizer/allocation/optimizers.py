"""Canonical NSGA-II and RION adapters for the shared allocation evaluator."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np
import pandas as pd

from libRION.libRION import RionOptimiser

from .problem import OBJECTIVE_FAMILIES, AllocationProblem, EvaluationResult


@dataclass
class AlgorithmResult:
    population: pd.DataFrame
    archive: pd.DataFrame
    accounting: dict


class EvaluationCache:
    """Cache repaired candidates and account actual shared-evaluator calls by phase."""

    def __init__(self, problem: AllocationProblem, phase: str = "initialization"):
        self.problem = problem
        self.phase = phase
        self._cache: dict[tuple[float, ...], EvaluationResult] = {}
        self.requests = Counter()
        self.unique = Counter()

    def set_phase(self, phase: str):
        self.phase = phase

    def key(self, candidate):
        if isinstance(candidate, pd.Series):
            values = [candidate[name] for name in self.problem.variable_names]
        elif isinstance(candidate, dict):
            values = [candidate[name] for name in self.problem.variable_names]
        else:
            values = candidate
        repaired = self.problem.repair(values)[1]
        return tuple(float(repaired[name]) for name in self.problem.variable_names)

    def evaluate(self, candidate):
        self.requests[self.phase] += 1
        key = self.key(candidate)
        if key not in self._cache:
            self._cache[key] = self.problem.evaluate(key)
            self.unique[self.phase] += 1
        return self._cache[key]

    def summary(self):
        return {
            "requested_by_phase": dict(sorted(self.requests.items())),
            "unique_shared_evaluator_calls_by_phase": dict(sorted(self.unique.items())),
            "requested_total": int(sum(self.requests.values())),
            "unique_shared_evaluator_calls_total": int(sum(self.unique.values())),
            "cache_hits": int(sum(self.requests.values()) - sum(self.unique.values())),
        }


def _dominates(first: EvaluationResult, second: EvaluationResult):
    first_feasible = first.normalized_violation <= 1e-12
    second_feasible = second.normalized_violation <= 1e-12
    if first_feasible != second_feasible:
        return first_feasible
    if not first_feasible:
        return first.normalized_violation < second.normalized_violation - 1e-12
    a, b = first.objective_vector(), second.objective_vector()
    return bool(np.all(a <= b) and np.any(a < b))


def _fronts(evaluations: list[EvaluationResult]):
    size = len(evaluations)
    dominated = [[] for _ in range(size)]
    counts = [0] * size
    ranks = [-1] * size
    for i in range(size):
        for j in range(i + 1, size):
            if _dominates(evaluations[i], evaluations[j]):
                dominated[i].append(j)
                counts[j] += 1
            elif _dominates(evaluations[j], evaluations[i]):
                dominated[j].append(i)
                counts[i] += 1
    fronts = [[i for i, count in enumerate(counts) if count == 0]]
    for index in fronts[0]:
        ranks[index] = 0
    cursor = 0
    while cursor < len(fronts) and fronts[cursor]:
        following = []
        for i in fronts[cursor]:
            for j in dominated[i]:
                counts[j] -= 1
                if counts[j] == 0:
                    ranks[j] = cursor + 1
                    following.append(j)
        if following:
            fronts.append(following)
        cursor += 1
    return fronts, ranks


def _crowding(evaluations: list[EvaluationResult], front: list[int]):
    distances = {index: 0.0 for index in front}
    if len(front) <= 2:
        return {index: float("inf") for index in front}
    matrix = np.array([evaluations[index].objective_vector() for index in front])
    for objective in range(matrix.shape[1]):
        order = np.argsort(matrix[:, objective], kind="stable")
        low, high = matrix[order[0], objective], matrix[order[-1], objective]
        distances[front[order[0]]] = float("inf")
        distances[front[order[-1]]] = float("inf")
        if high > low:
            for position in range(1, len(order) - 1):
                index = front[order[position]]
                if np.isfinite(distances[index]):
                    distances[index] += (
                        matrix[order[position + 1], objective]
                        - matrix[order[position - 1], objective]
                    ) / (high - low)
    return distances


def _rank_and_crowding(evaluations):
    fronts, ranks = _fronts(evaluations)
    crowding = [0.0] * len(evaluations)
    for front in fronts:
        for index, distance in _crowding(evaluations, front).items():
            crowding[index] = distance
    return fronts, ranks, crowding


def _sample(problem: AllocationProblem, rng, size):
    rows = []
    for _ in range(size):
        candidate = [
            rng.uniform(float(variable["lower"]), float(variable["upper"]))
            for variable in problem.variables
        ]
        repaired = problem.repair(candidate)[1]
        rows.append([repaired[name] for name in problem.variable_names])
    return np.asarray(rows, dtype=float)


def _sbx(first, second, lower, upper, rng, eta=15.0):
    child_a, child_b = first.copy(), second.copy()
    for i in range(len(first)):
        if rng.random() > 0.5 or abs(first[i] - second[i]) <= 1e-14:
            continue
        x1, x2 = sorted((first[i], second[i]))
        rand = rng.random()
        beta = 1.0 + 2.0 * (x1 - lower[i]) / (x2 - x1)
        alpha = 2.0 - beta ** (-(eta + 1.0))
        beta_q = (
            (rand * alpha) ** (1.0 / (eta + 1.0))
            if rand <= 1.0 / alpha
            else (1.0 / (2.0 - rand * alpha)) ** (1.0 / (eta + 1.0))
        )
        value_a = 0.5 * ((x1 + x2) - beta_q * (x2 - x1))
        beta = 1.0 + 2.0 * (upper[i] - x2) / (x2 - x1)
        alpha = 2.0 - beta ** (-(eta + 1.0))
        beta_q = (
            (rand * alpha) ** (1.0 / (eta + 1.0))
            if rand <= 1.0 / alpha
            else (1.0 / (2.0 - rand * alpha)) ** (1.0 / (eta + 1.0))
        )
        value_b = 0.5 * ((x1 + x2) + beta_q * (x2 - x1))
        if rng.random() < 0.5:
            value_a, value_b = value_b, value_a
        child_a[i] = np.clip(value_a, lower[i], upper[i])
        child_b[i] = np.clip(value_b, lower[i], upper[i])
    return child_a, child_b


def _polynomial_mutation(candidate, lower, upper, rng, eta=20.0):
    result = candidate.copy()
    probability = 1.0 / len(result)
    for i in range(len(result)):
        if rng.random() > probability or upper[i] <= lower[i]:
            continue
        delta1 = (result[i] - lower[i]) / (upper[i] - lower[i])
        delta2 = (upper[i] - result[i]) / (upper[i] - lower[i])
        rand = rng.random()
        mutation_power = 1.0 / (eta + 1.0)
        if rand < 0.5:
            xy = 1.0 - delta1
            value = 2.0 * rand + (1.0 - 2.0 * rand) * xy ** (eta + 1.0)
            delta_q = value**mutation_power - 1.0
        else:
            xy = 1.0 - delta2
            value = 2.0 * (1.0 - rand) + 2.0 * (rand - 0.5) * xy ** (eta + 1.0)
            delta_q = 1.0 - value**mutation_power
        result[i] = np.clip(
            result[i] + delta_q * (upper[i] - lower[i]), lower[i], upper[i]
        )
    return result


def _repair_vector(problem, vector):
    repaired = problem.repair(vector)[1]
    return np.array([repaired[name] for name in problem.variable_names], dtype=float)


def _tournament(rng, ranks, crowding):
    first, second = rng.choice(len(ranks), size=2, replace=False)
    key_first = (ranks[first], -crowding[first])
    key_second = (ranks[second], -crowding[second])
    if key_first == key_second:
        return int(first if rng.random() < 0.5 else second)
    return int(first if key_first < key_second else second)


def _flatten(problem, vectors, evaluations, algorithm, seed):
    _, ranks, crowding = _rank_and_crowding(evaluations)
    rows = []
    for vector, result, rank, distance in zip(vectors, evaluations, ranks, crowding):
        row = {name: float(value) for name, value in zip(problem.variable_names, vector)}
        row.update({f"kpi__{name}": value for name, value in result.raw_kpis.items()})
        for name, interval in result.uncertainty.items():
            row[f"lower__{name}"] = interval["lower"]
            row[f"upper__{name}"] = interval["upper"]
        row.update(
            {f"objective_benefit__{name}": value for name, value in result.objective_benefits.items()}
        )
        row.update({f"objective__{name}": value for name, value in result.objective_scores.items()})
        row.update(
            {f"constraint__{name}": value for name, value in result.constraint_residuals.items()}
        )
        row.update(
            {
                f"normalized_constraint__{name}": value
                for name, value in result.normalized_constraint_violations.items()
            }
        )
        row.update(
            normalized_violation=result.normalized_violation,
            feasible=result.nominal_feasible,
            robust_feasible=result.robust_feasible,
            out_of_model_support=result.support_flags["out_of_model_support"],
            out_of_support_features=result.support_flags["out_of_support_features"],
            cost=result.cost,
            budget_remaining=result.budget_remaining,
            pareto_rank=int(rank),
            crowding_distance=float(distance),
            algorithm=algorithm,
            run_seed=int(seed),
        )
        rows.append(row)
    population = pd.DataFrame(rows)
    allocation_columns = problem.variable_names
    archive = population[(population["feasible"]) & (population["pareto_rank"] == 0)].copy()
    archive = archive.drop_duplicates(subset=allocation_columns).reset_index(drop=True)
    return population.reset_index(drop=True), archive


class CanonicalNSGA2Adapter:
    name = "nsga2"

    def __init__(self, population_size=20, generations=5, seed=42):
        if population_size < 4:
            raise ValueError("NSGA-II population_size must be at least 4")
        if generations < 0:
            raise ValueError("generations must be non-negative")
        self.population_size = int(population_size)
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
                children.append(_repair_vector(problem, _polynomial_mutation(child_a, lower, upper, rng)))
                if len(children) < self.population_size:
                    children.append(_repair_vector(problem, _polynomial_mutation(child_b, lower, upper, rng)))
            child_vectors = np.asarray(children)
            child_evaluations = [cache.evaluate(vector) for vector in child_vectors]
            combined_vectors = np.vstack([vectors, child_vectors])
            combined_evaluations = evaluations + child_evaluations
            fronts, _, _ = _rank_and_crowding(combined_evaluations)
            selected = []
            for front in fronts:
                remaining = self.population_size - len(selected)
                if len(front) <= remaining:
                    selected.extend(front)
                else:
                    distance = _crowding(combined_evaluations, front)
                    selected.extend(sorted(front, key=lambda i: (-distance[i], i))[:remaining])
                    break
            vectors = combined_vectors[selected]
            evaluations = [combined_evaluations[index] for index in selected]
        population, archive = _flatten(problem, vectors, evaluations, self.name, self.seed)
        accounting = cache.summary()
        accounting.update(
            algorithm=self.name,
            population_size=self.population_size,
            generations=self.generations,
            inner_pso_evaluations=0,
            candidate_evaluations_initialization=self.population_size,
            candidate_evaluations_evolution=self.population_size * self.generations,
            candidate_evaluations_inner_pso=0,
            candidate_evaluations_total=self.population_size * (self.generations + 1),
        )
        return AlgorithmResult(population, archive, accounting)


class RionAllocationAdapter:
    name = "rion"

    def __init__(self, population_size=20, generations=5, pso_iterations=2, seed=42):
        self.population_size = int(population_size)
        self.generations = int(generations)
        self.pso_iterations = int(pso_iterations)
        self.seed = int(seed)

    def run(self, problem: AllocationProblem):
        rng = np.random.default_rng(self.seed)
        cache = EvaluationCache(problem)
        initial = _sample(problem, rng, max(self.population_size * 2, self.population_size))
        data = pd.DataFrame(initial, columns=problem.variable_names)

        def objective(index):
            return lambda row: cache.evaluate(row).objective_vector()[index]

        def repair(row):
            repaired = problem.repair(row)[1]
            return pd.Series(repaired, index=problem.variable_names)

        optimizer = RionOptimiser(
            generations=self.generations,
            pop_size=self.population_size,
            inertia=0.5,
            self_confidence=1.5,
            cross_confidence=1.5,
            pso_iterations=self.pso_iterations,
            seed=self.seed,
            pso_backend="serial",
        )
        population = optimizer.optimise(
            data,
            [objective(index) for index in range(len(OBJECTIVE_FAMILIES))],
            [(float(item["lower"]), float(item["upper"])) for item in problem.variables],
            integer_columns=[
                item["name"] for item in problem.variables if item["type"] == "integer"
            ],
            repair_func=repair,
            constraint_violation_func=lambda row: cache.evaluate(row).normalized_violation,
            evaluation_phase_callback=cache.set_phase,
        )
        cache.set_phase("final_export")
        vectors = population[problem.variable_names].to_numpy(dtype=float)
        evaluations = [cache.evaluate(vector) for vector in vectors]
        flattened, archive = _flatten(problem, vectors, evaluations, self.name, self.seed)
        accounting = cache.summary()
        accounting.update(
            algorithm=self.name,
            population_size=self.population_size,
            generations=self.generations,
            pso_iterations=self.pso_iterations,
            inner_pso_evaluations=int(cache.unique.get("inner_pso", 0)),
            inner_pso_evaluation_requests=int(cache.requests.get("inner_pso", 0)),
            # RION evaluates one offspring batch and then evaluates the whole
            # swarm once on construction and once per PSO iteration.  These
            # counts define the implementation-independent benchmark budget;
            # cache hits and final export are reported separately above.
            candidate_evaluations_initialization=self.population_size,
            candidate_evaluations_evolution=self.population_size * self.generations,
            candidate_evaluations_inner_pso=(
                self.population_size * self.generations * (self.pso_iterations + 1)
            ),
            candidate_evaluations_total=(
                self.population_size
                + self.population_size * self.generations * (self.pso_iterations + 2)
            ),
        )
        return AlgorithmResult(flattened, archive, accounting)
