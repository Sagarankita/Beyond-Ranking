import copy
import json
import unittest
from pathlib import Path

import pandas as pd

from department_optimizer.allocation import (
    CanonicalNSGA2Adapter,
    MOEADAdapter,
    MOPSOAdapter,
    NSGA3Adapter,
    RandomSearchAdapter,
    RionAllocationAdapter,
)
from department_optimizer.public_allocation.problem import VJTIPublicAllocationProblem


ROOT = Path(__file__).resolve().parents[1]


class PublicExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.allocation = json.loads(
            (ROOT / "configs/public_allocation/vjti_four_family_v1.json").read_text()
        )
        cls.experiment = json.loads(
            (ROOT / "configs/public_experiments/vjti_experiments_v1.json").read_text()
        )
        cls.model_root = ROOT / "artifacts/evidence_modeling/vjti_v1"
        cls.output = ROOT / "artifacts/public_experiments/vjti_v1"

    def test_held_fixed_does_not_repair_budget_infeasibility(self):
        config = copy.deepcopy(self.allocation)
        config["budget_limit"] = 30_000_000
        problem = VJTIPublicAllocationProblem(config, self.model_root)
        fixed = problem.evaluate_fixed(config["reference_allocation"])
        repaired = problem.evaluate(config["reference_allocation"])
        self.assertAlmostEqual(fixed.total_cost, 33_300_000)
        self.assertFalse(fixed.feasible)
        self.assertLessEqual(repaired.total_cost, 30_000_000)

    def test_all_approved_adapters_match_declared_budget(self):
        problem = VJTIPublicAllocationProblem(self.allocation, self.model_root)
        adapters = [
            CanonicalNSGA2Adapter(population_size=4, generations=3, seed=2),
            NSGA3Adapter(reference_partitions=1, generations=3, seed=2),
            MOEADAdapter(reference_partitions=1, neighborhood_size=2, max_replacements=2, generations=3, seed=2),
            MOPSOAdapter(population_size=4, generations=3, archive_size=8, seed=2),
            RionAllocationAdapter(population_size=4, generations=1, pso_iterations=1, seed=2),
            RandomSearchAdapter(evaluations=16, seed=2),
        ]
        for adapter in adapters:
            with self.subTest(algorithm=adapter.name):
                self.assertEqual(adapter.run(problem).accounting["candidate_evaluations_total"], 16)

    def test_saved_prompt17_acceptance_artifacts(self):
        manifest = json.loads((self.output / "experiment_manifest.json").read_text())
        self.assertEqual(manifest["completed_comparison_runs"], 18)
        self.assertEqual(manifest["completed_comparison_runs"], manifest["declared_comparison_runs"])
        checks = pd.read_csv(self.output / "independent_checks.csv")
        self.assertTrue(checks.passed.all())
        allocations = pd.read_csv(self.output / "strategy_allocations.csv")
        scenario_types = allocations.groupby("scenario").strategy_type.unique()
        for scenario in self.experiment["scenarios"]:
            types = set(scenario_types[scenario["name"]])
            self.assertIn("held_fixed", types)
            self.assertIn("scenario_reoptimization", types)
        objectives = pd.read_csv(self.output / "strategy_objectives.csv")
        self.assertTrue(objectives.groupby("strategy_id").objective.nunique().eq(4).all())
        self.assertTrue(objectives.synthetic_coverage.notna().all())
        self.assertEqual(len(pd.read_csv(self.output / "common_uncertainty_draws.csv")), 1000)
        self.assertTrue((self.output / "public_only_sensitivity.csv").is_file())
        self.assertTrue((self.output / "current_vs_strategy_actions.csv").is_file())
        self.assertTrue((self.output / "tradeoff_cost_benefit.svg").is_file())


if __name__ == "__main__":
    unittest.main()
