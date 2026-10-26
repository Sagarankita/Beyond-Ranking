"""Measure cheap-callback and end-to-end serial/native timing without speedup claims."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from statistics import median
from time import perf_counter

import numpy as np
import pandas as pd

from libRION.libPSO import PSO as SerialPSO
from libRION.libPSO_parallel import PSO as NativePSO
from libRION.libRION import RionOptimiser
from main import INTEGER_COLUMNS, define_constraints, define_objective_functions


def time_pso(cls, repeats, particles, dimensions, iterations):
    samples = []
    evaluation_counts = []
    initial = np.random.default_rng(91).uniform(-5, 5, size=(particles, dimensions))
    for _ in range(repeats):
        evaluations = 0

        def cheap_sphere(position):
            nonlocal evaluations
            evaluations += 1
            return float(np.dot(position, position))

        started = perf_counter()
        pso = cls(
            cheap_sphere,
            initial,
            max_iter=iterations,
            lower_bounds=np.full(dimensions, -5.0),
            upper_bounds=np.full(dimensions, 5.0),
            seed=73,
        )
        try:
            pso.optimize()
        finally:
            close = getattr(pso, "close", None)
            if close:
                close()
        samples.append(perf_counter() - started)
        evaluation_counts.append(evaluations)
    expected = particles * (iterations + 1)
    if any(count != expected for count in evaluation_counts):
        raise RuntimeError(f"unexpected objective counts: {evaluation_counts}, expected {expected}")
    return {
        "seconds": samples,
        "median_seconds": median(samples),
        "objective_evaluations_per_run": expected,
        "median_seconds_per_objective_evaluation": median(samples) / expected,
    }


def time_rion(backend, repeats):
    frame = pd.read_csv("data/department_research_data.csv").drop(columns=["college_id"])
    samples = []
    for _ in range(repeats):
        optimizer = RionOptimiser(
            generations=2,
            pop_size=20,
            inertia=0.5,
            self_confidence=1.5,
            cross_confidence=1.5,
            pso_iterations=5,
            seed=42,
            pso_backend=backend,
        )
        started = perf_counter()
        optimizer.optimise(
            frame,
            define_objective_functions(),
            define_constraints(),
            integer_columns=INTEGER_COLUMNS,
        )
        samples.append(perf_counter() - started)
    return {"seconds": samples, "median_seconds": median(samples)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--particles", type=int, default=100)
    parser.add_argument("--dimensions", type=int, default=10)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")

    result = {
        "purpose": "diagnostic timing; not a speedup or scientific-performance claim",
        "omp_num_threads": os.environ.get("OMP_NUM_THREADS", "runtime default"),
        "cheap_objective": {
            "particles": args.particles,
            "dimensions": args.dimensions,
            "iterations": args.iterations,
            "serial": time_pso(
                SerialPSO, args.repeats, args.particles, args.dimensions, args.iterations
            ),
            "native": time_pso(
                NativePSO, args.repeats, args.particles, args.dimensions, args.iterations
            ),
        },
        "rion_workflow": {
            "generations": 2,
            "population_size": 20,
            "pso_iterations": 5,
            "serial": time_rion("serial", args.repeats),
            "native": time_rion("native", args.repeats),
        },
    }
    rendered = json.dumps(result, indent=2) + "\n"
    print(rendered, end="")
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered)


if __name__ == "__main__":
    main()
