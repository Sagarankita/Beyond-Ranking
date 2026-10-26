"""Seeded scalar search for minimum cost subject to KPI/objective targets."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from department_optimizer.allocation.problem import OBJECTIVE_FAMILIES


def assess_targets(problem, targets):
    """Return support status before optimization so missing outcomes are never invented."""
    available_kpis = set(problem.model.manifest["target_columns"])
    unsupported = []
    for target in targets:
        kind, name = target.get("kind"), target.get("name")
        if kind == "kpi":
            if name not in available_kpis:
                unsupported.append(f"KPI {name}")
        elif kind == "objective_benefit":
            if name not in OBJECTIVE_FAMILIES:
                unsupported.append(f"objective family {name}")
            elif not problem.config["objective_families"][name].get("components"):
                unsupported.append(f"objective family {name}")
        else:
            unsupported.append(f"target kind {kind}")
        if target.get("direction") not in {"minimum", "maximum"}:
            unsupported.append(f"direction for {name}")
        try:
            value = float(target.get("value"))
            if not np.isfinite(value):
                unsupported.append(f"nonfinite value for {name}")
        except (TypeError, ValueError):
            unsupported.append(f"value for {name}")
    return {
        "status": "supported" if not unsupported else "unsupported",
        "unsupported": sorted(set(unsupported)),
    }


def target_values(evaluation, targets):
    values = {}
    for target in targets:
        if target["kind"] == "kpi":
            values[target["name"]] = float(evaluation.raw_kpis[target["name"]])
        else:
            values[target["name"]] = float(
                evaluation.objective_benefits[target["name"]]
            )
    return values


def target_residuals(evaluation, targets):
    residuals = {}
    values = target_values(evaluation, targets)
    for target in targets:
        name = target["name"]
        threshold = float(target["value"])
        value = values[name]
        residual = threshold - value if target["direction"] == "minimum" else value - threshold
        residuals[name] = float(residual)
    return residuals


@dataclass
class SearchResult:
    status: str
    candidate: dict | None
    evaluation: object | None
    target_residuals: dict
    accounting: dict


class TargetCostOptimizer:
    """Feasibility-first evolutionary search followed by cost-coordinate polishing."""

    def __init__(self, population_size=20, generations=9, evaluation_budget=250, seed=0):
        if population_size < 4 or generations < 0:
            raise ValueError("target-cost search needs population >= 4 and generations >= 0")
        if evaluation_budget < population_size:
            raise ValueError("evaluation budget must cover initialization")
        self.population_size = int(population_size)
        self.generations = int(generations)
        self.evaluation_budget = int(evaluation_budget)
        self.seed = int(seed)

    def run(self, problem, targets):
        support = assess_targets(problem, targets)
        if support["status"] != "supported":
            return SearchResult(
                "unsupported_targets", None, None, {},
                {"candidate_evaluations_total": 0, **support},
            )
        rng = np.random.default_rng(self.seed)
        calls = 0
        phase_counts = {"initialization": 0, "evolution": 0, "cost_polish": 0}

        def evaluate(vector, phase):
            nonlocal calls
            if calls >= self.evaluation_budget:
                return None
            calls += 1
            phase_counts[phase] += 1
            result = problem.evaluate(vector)
            residuals = target_residuals(result, targets)
            target_violation = sum(
                max(0.0, value) / max(abs(float(target["value"])), 1.0)
                for target, value in zip(targets, residuals.values())
            )
            total_violation = float(result.normalized_violation + target_violation)
            return {
                "vector": np.array(
                    [result.repaired[name] for name in problem.variable_names], dtype=float
                ),
                "evaluation": result,
                "target_residuals": residuals,
                "total_violation": total_violation,
                "target_feasible": bool(
                    result.nominal_feasible
                    and all(value <= 1e-9 for value in residuals.values())
                ),
            }

        lower = np.array([float(item["lower"]) for item in problem.variables])
        upper = np.array([float(item["upper"]) for item in problem.variables])
        population = []
        # Boundary candidates improve reproducibility for targets favored by free effort.
        boundary = upper.copy()
        population.append(evaluate(boundary, "initialization"))
        while len(population) < self.population_size:
            population.append(
                evaluate(rng.uniform(lower, upper), "initialization")
            )

        def key(item):
            return (
                0 if item["target_feasible"] else 1,
                item["evaluation"].cost if item["target_feasible"] else item["total_violation"],
                item["total_violation"],
                item["evaluation"].cost,
            )

        population.sort(key=key)
        for _ in range(self.generations):
            children = []
            while len(children) < self.population_size and calls < self.evaluation_budget:
                tournament_a = rng.choice(population, size=2, replace=False)
                tournament_b = rng.choice(population, size=2, replace=False)
                first = min(tournament_a, key=key)["vector"]
                second = min(tournament_b, key=key)["vector"]
                mask = rng.random(len(lower)) < 0.5
                child = np.where(mask, first, second).astype(float)
                blend = rng.random(len(lower)) < 0.35
                alpha = rng.random(np.sum(blend))
                child[blend] = (
                    alpha * first[blend] + (1.0 - alpha) * second[blend]
                )
                mutate = rng.random(len(lower)) < max(0.25, 1.0 / len(lower))
                child[mutate] += rng.normal(0.0, 0.12, np.sum(mutate)) * (
                    upper[mutate] - lower[mutate]
                )
                child = np.clip(child, lower, upper)
                evaluated = evaluate(child, "evolution")
                if evaluated is not None:
                    children.append(evaluated)
            population = sorted(population + children, key=key)[: self.population_size]

        feasible = [item for item in population if item["target_feasible"]]
        if feasible:
            best = min(feasible, key=lambda item: item["evaluation"].cost)
            # Free effort can increase target margin and permit a cheaper monetary allocation.
            for index, variable in enumerate(problem.variables):
                if variable["cost_mode"] == "non_monetary" and calls < self.evaluation_budget:
                    trial = best["vector"].copy()
                    trial[index] = upper[index]
                    evaluated = evaluate(trial, "cost_polish")
                    if evaluated["target_feasible"] and evaluated["evaluation"].cost <= best[
                        "evaluation"
                    ].cost:
                        best = evaluated
            for index, variable in enumerate(problem.variables):
                if variable["cost_mode"] == "non_monetary" or calls >= self.evaluation_budget:
                    continue
                increment = float(variable["increment"])
                current = best["vector"][index]
                steps = int(round((current - lower[index]) / increment))
                low_step, high_step = 0, steps
                local_best = best
                while low_step <= high_step and calls < self.evaluation_budget:
                    middle = (low_step + high_step) // 2
                    trial = best["vector"].copy()
                    trial[index] = lower[index] + middle * increment
                    evaluated = evaluate(trial, "cost_polish")
                    if evaluated["target_feasible"]:
                        local_best = evaluated
                        high_step = middle - 1
                    else:
                        low_step = middle + 1
                if local_best["evaluation"].cost <= best["evaluation"].cost:
                    best = local_best
            status = "target_feasible"
        else:
            best = min(population, key=key)
            status = "no_target_feasible_candidate_within_budget"

        return SearchResult(
            status=status,
            candidate={
                name: float(value) for name, value in zip(problem.variable_names, best["vector"])
            },
            evaluation=best["evaluation"],
            target_residuals=best["target_residuals"],
            accounting={
                "candidate_evaluations_total": calls,
                "evaluation_budget": self.evaluation_budget,
                "candidate_evaluations_by_phase": phase_counts,
                "population_size": self.population_size,
                "generations": self.generations,
                "seed": self.seed,
            },
        )
