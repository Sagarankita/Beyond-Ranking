import copy
import json
import unittest
from pathlib import Path

from department_optimizer.allocation import AllocationProblem
from department_optimizer.robustness.runner import apply_scenario, evaluate_fixed
from tests.test_allocation_optimizers import DeterministicModel


REPO_ROOT = Path(__file__).resolve().parents[1]


def base_config():
    return json.loads(
        (REPO_ROOT / "configs/allocation/legacy_synthetic_method_fixture.json").read_text()
    )


class ScenarioTransformationTests(unittest.TestCase):
    def test_supported_shocks_apply_to_copy_without_mutating_base(self):
        base = base_config()
        original = copy.deepcopy(base)
        transformed, status, reason = apply_scenario(
            base,
            {
                "id": "fixture",
                "budget_limit": 15_000_000,
                "faculty_capacity_fte": 60,
                "unit_cost_multipliers": {"centres_of_excellence_count": 1.25},
            },
        )
        self.assertEqual(status, "supported")
        self.assertIsNone(reason)
        self.assertEqual(transformed["budget_limit"], 15_000_000)
        self.assertEqual(transformed["faculty_time"]["capacity_fte"], 60)
        centre = next(
            item
            for item in transformed["decision_variables"]
            if item["name"] == "centres_of_excellence_count"
        )
        self.assertEqual(centre["unit_cost"], 1_875_000)
        self.assertEqual(base, original)

    def test_missing_patent_and_compute_shocks_are_explicitly_unsupported(self):
        for variable in ("patent_ip_support", "compute_capacity_units"):
            transformed, status, reason = apply_scenario(
                base_config(),
                {
                    "id": variable,
                    "unit_cost_multipliers": {variable: 1.25},
                },
            )
            self.assertIsNone(transformed)
            self.assertEqual(status, "unsupported")
            self.assertIn(variable, reason)


class FixedStrategyTests(unittest.TestCase):
    def test_fixed_evaluation_reports_infeasibility_without_repairing_strategy(self):
        config = base_config()
        config["budget_limit"] = 10_000_000
        problem = AllocationProblem(config, DeterministicModel())
        allocation = config["reference_allocation"]["values"]
        result = evaluate_fixed(problem, allocation)
        self.assertEqual(result["allocation"], allocation)
        self.assertGreater(result["constraint_residuals"]["budget"], 0)
        self.assertFalse(result["nominal_feasible"])


if __name__ == "__main__":
    unittest.main()
