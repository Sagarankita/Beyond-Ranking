"""Command-line entry point for the corrected legacy RION baseline."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

from libRION.libRION import RionOptimiser


OBJECTIVE_NAMES = ["productivity", "quality", "cost_per_impact"]
INTEGER_COLUMNS = [
    "faculty_phd",
    "faculty_other",
    "centres_of_excellence_count",
    "industry_collaborations",
    "student_count",
    "num_courses",
    "papers_t1",
    "overall_rank",
]


def define_objective_functions(legacy_zero_impact: bool = False):
    """Return the three versioned legacy research objectives.

    The historical implementation returned 1e5 when impact was below one. That can
    incorrectly make a zero-impact candidate look cheaper than productive candidates.
    Corrected runs use a finite, deliberately poor score of 1e15 + budget. The old
    behavior remains available only through ``legacy_zero_impact=True``.
    """

    def research_fte(individual):
        return max(
            individual["faculty_phd"] * individual["frac_research_phd"]
            + individual["faculty_other"] * individual["frac_research_other"],
            1.0,
        )

    def objective_1_productivity(individual):
        return -float(individual["papers_t1"]) / research_fte(individual)

    def objective_2_quality(individual):
        impact = float(individual["papers_t1"] * individual["citation_percentile_avg"])
        return -impact / research_fte(individual)

    def objective_3_cost_efficiency(individual):
        budget = float(individual["research_budget"])
        impact = float(individual["papers_t1"] * individual["citation_percentile_avg"])
        if impact < 1.0:
            return 1e5 if legacy_zero_impact else 1e15 + budget
        return budget / (impact + 1e-6)

    return [objective_1_productivity, objective_2_quality, objective_3_cost_efficiency]


def define_constraints():
    """Box constraints in the same order as the legacy CSV columns."""
    return [
        [5, 250],
        [0, 100],
        [0.1, 0.9],
        [0.05, 0.8],
        [1e5, 5e9],
        [0, 15],
        [2.0, 15.0],
        [0.0, 1.0],
        [0, 100],
        [100, 10000],
        [10, 300],
        [0, 5000],
        [0.0, 1.0],
        [1, 200],
    ]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data/department_research_data.csv")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--generations", type=int, default=20)
    parser.add_argument("--population-size", type=int, default=50)
    parser.add_argument("--pso-iterations", type=int, default=10)
    parser.add_argument("--pso-backend", choices=["serial", "native"], default="serial")
    parser.add_argument(
        "--legacy-zero-impact",
        action="store_true",
        help="reproduce the historical 1e5 cost score for impact below one",
    )
    return parser.parse_args()


def run(args):
    data_path = Path(args.data)
    data = pd.read_csv(data_path)
    if "college_id" in data.columns:
        data = data.drop(columns=["college_id"])

    objectives = define_objective_functions(args.legacy_zero_impact)
    constraints = define_constraints()
    if len(data.columns) != len(constraints):
        raise ValueError(
            f"expected {len(constraints)} optimization columns, got {len(data.columns)}"
        )

    optimizer = RionOptimiser(
        generations=args.generations,
        pop_size=args.population_size,
        inertia=0.5,
        self_confidence=1.5,
        cross_confidence=1.5,
        pso_iterations=args.pso_iterations,
        seed=args.seed,
        pso_backend=args.pso_backend,
    )
    population = optimizer.optimise(
        data,
        objectives,
        constraints,
        integer_columns=INTEGER_COLUMNS,
    )
    evaluation = optimizer.evaluate_population(population).rename(
        columns={f"objective_{i + 1}": name for i, name in enumerate(OBJECTIVE_NAMES)}
    )
    annotated = pd.concat([population, evaluation], axis=1)
    annotated["run_seed"] = args.seed
    pareto = annotated[(annotated["feasible"]) & (annotated["pareto_rank"] == 0)].copy()

    output_dir = Path(args.output_dir or f"results/baseline_seed_{args.seed}")
    output_dir.mkdir(parents=True, exist_ok=True)
    annotated.to_csv(output_dir / "population.csv", index=False)
    pareto.to_csv(output_dir / "pareto_front.csv", index=False)
    config = {
        "seed": args.seed,
        "generations": args.generations,
        "population_size": args.population_size,
        "pso_iterations": args.pso_iterations,
        "pso_backend": args.pso_backend,
        "omp_num_threads": os.environ.get("OMP_NUM_THREADS"),
        "pso_inertia": 0.5,
        "pso_cognitive": 1.5,
        "pso_social": 1.5,
        "crossover_probability": 0.3,
        "constraint_penalty_weight": 1000.0,
        "data": str(data_path),
        "objectives": OBJECTIVE_NAMES,
        "objective_direction": "minimize",
        "zero_impact_policy": "legacy_1e5" if args.legacy_zero_impact else "1e15_plus_budget",
        "integer_columns": INTEGER_COLUMNS,
        "constraints": dict(zip(data.columns, constraints)),
    }
    (output_dir / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    return annotated, pareto, output_dir


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "allocation":
        from department_optimizer.allocation.workflow import main as allocation_main

        allocation_main(sys.argv[2:])
        return
    args = parse_args()
    population, pareto, output_dir = run(args)
    print(f"RION corrected baseline complete ({args.pso_backend} PSO backend)")
    print(f"Population: {len(population)}")
    print(f"Feasible: {int(population['feasible'].sum())}")
    print(f"Feasible Pareto solutions: {len(pareto)}")
    print(f"Outputs: {output_dir}")


if __name__ == "__main__":
    main()
