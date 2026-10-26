import copy
import json
import tempfile
import unittest
from pathlib import Path

from department_optimizer.public_allocation.problem import (
    PublicAllocationConfigurationError,
    VJTIPublicAllocationProblem,
)
from department_optimizer.public_allocation.workflow import run_public_allocation


REPO_ROOT = Path(__file__).resolve().parents[1]


class PublicAllocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads(
            (REPO_ROOT / "configs/public_allocation/vjti_four_family_v1.json").read_text()
        )
        cls.model_root = REPO_ROOT / "artifacts/evidence_modeling/vjti_v1"

    def test_hand_reference_cost_objectives_and_constraints(self):
        problem = VJTIPublicAllocationProblem(self.config, self.model_root)
        result = problem.evaluate(self.config["reference_allocation"])
        self.assertAlmostEqual(result.total_cost, 33_300_000)
        self.assertAlmostEqual(sum(result.cost_components.values()), result.total_cost)
        self.assertTrue(result.feasible)
        self.assertEqual(set(result.objective_scores), {
            "research", "innovation", "student_development", "societal_contribution"
        })
        self.assertTrue(all(value == "synthetic_scenario" for value in result.objective_evidence.values()))
        self.assertIn("not used as a causal multiplier", result.dea_status)

    def test_patent_compute_shocks_and_unsupported_family_gate(self):
        problem = VJTIPublicAllocationProblem(self.config, self.model_root)
        base = problem.evaluate(self.config["reference_allocation"])
        patent = dict(self.config["reference_allocation"])
        patent["patent_ip_support"] += 500_000
        compute = dict(self.config["reference_allocation"])
        compute["compute_capacity_units"] += 2
        self.assertGreater(problem.evaluate(patent).raw_kpis["patent_applications"], base.raw_kpis["patent_applications"])
        self.assertGreater(problem.evaluate(compute).raw_kpis["patent_applications"], base.raw_kpis["patent_applications"])
        invalid = copy.deepcopy(self.config)
        invalid["objective_families"]["innovation"]["enabled"] = False
        with self.assertRaises(PublicAllocationConfigurationError):
            VJTIPublicAllocationProblem(invalid, self.model_root)

    def test_workflow_recommendations_are_separate_and_feasible(self):
        with tempfile.TemporaryDirectory() as temp:
            config = copy.deepcopy(self.config)
            config["prompt14_root"] = str(REPO_ROOT / "artifacts/public_data/vjti_ceit_v1")
            config["prompt15_root"] = str(self.model_root)
            config["output_root"] = str(Path(temp) / "allocation")
            for track in config["target_cost_tracks"]:
                track["random_candidates"] = 50
            path = Path(temp) / "config.json"
            path.write_text(json.dumps(config))
            result = run_public_allocation(path)
            self.assertTrue(result["checks_passed"])
            self.assertEqual(result["target_recommendations"], 2)
            root = Path(result["output_root"])
            self.assertTrue((root / "target_cost/public_informed_student_targets/recommendation.json").is_file())
            self.assertTrue((root / "target_cost/scenario_four_family_targets/recommendation.json").is_file())


if __name__ == "__main__":
    unittest.main()
