import copy
import json
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from department_optimizer.allocation import (
    AllocationProblem,
    ProblemConfigurationError,
    evaluate,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class FakePredictionModel:
    def __init__(self):
        self.manifest = {
            "feature_columns": [
                "faculty_phd",
                "faculty_other",
                "frac_research_phd",
                "frac_research_other",
                "research_budget",
                "centres_of_excellence_count",
                "teaching_load_per_faculty",
                "diversity_index",
                "industry_collaborations",
                "student_count",
                "num_courses",
            ],
            "target_columns": ["papers_t1", "citation_percentile_avg"],
        }

    def predict(self, records):
        frame = pd.DataFrame(records)
        papers = frame["research_budget"] / 1_000_000 + 2 * frame["centres_of_excellence_count"]
        citation = 0.5 + 0.1 * frame["frac_research_phd"]
        return pd.DataFrame(
            {
                "out_of_support": False,
                "out_of_support_features": "",
                "prediction__papers_t1": papers,
                "lower__papers_t1": papers - 1,
                "upper__papers_t1": papers + 1,
                "prediction__citation_percentile_avg": citation,
                "lower__citation_percentile_avg": citation - 0.02,
                "upper__citation_percentile_avg": citation + 0.02,
            },
            index=frame.index,
        )


def fixture_config():
    return json.loads(
        (REPO_ROOT / "configs/allocation/legacy_synthetic_method_fixture.json").read_text()
    )


class AllocationEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.config = fixture_config()
        self.model = FakePredictionModel()
        self.problem = AllocationProblem(self.config, self.model)

    def test_hand_calculated_reference_cost_predictions_signs_and_constraints(self):
        allocation = self.config["reference_allocation"]["values"]
        result = evaluate(allocation, self.config, self.model)
        self.assertEqual(result.cost, 12_000_000)
        self.assertEqual(result.budget_remaining, 8_000_000)
        self.assertAlmostEqual(result.raw_kpis["papers_t1"], 12.0)
        self.assertAlmostEqual(result.raw_kpis["citation_percentile_avg"], 0.55)
        expected_benefit = 0.6 * (12 / 60) + 0.4 * ((0.55 - 0.5) / 0.3)
        self.assertAlmostEqual(result.objective_benefits["research"], expected_benefit)
        self.assertAlmostEqual(result.objective_scores["research"], -expected_benefit)
        self.assertEqual(result.objective_scores["innovation"], 0.0)
        self.assertEqual(result.objective_vector().shape, (4,))
        self.assertTrue(result.nominal_feasible)
        self.assertTrue(result.robust_feasible)
        self.assertEqual(result.normalized_violation, 0.0)
        self.assertEqual(result.estimated_probability_feasible, 1.0)
        self.assertIsNone(result.dea_efficiency)
        self.assertIn("separate", result.dea_status)

    def test_mixed_candidate_is_clipped_snapped_repaired_and_revalidated(self):
        result = self.problem.evaluate([30_040_000, 0.91, 0.91, 7.4, 12.8])
        repaired = result.repaired
        self.assertLessEqual(result.cost, self.config["budget_limit"])
        self.assertEqual(repaired["centres_of_excellence_count"], round(repaired["centres_of_excellence_count"]))
        self.assertEqual(
            repaired["industry_collaboration_support_count"],
            round(repaired["industry_collaboration_support_count"]),
        )
        research_fte = 80 * repaired["frac_research_phd"] + 40 * repaired["frac_research_other"]
        self.assertLessEqual(research_fte, 80.0 + 1e-9)
        self.assertTrue(result.nominal_feasible, result.constraint_residuals)
        self.assertEqual(result.normalized_violation, 0.0)
        self.assertTrue(result.repair_actions)

    def test_candidate_shape_nonfinite_and_keys_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "expected"):
            self.problem.decode([1.0])
        with self.assertRaisesRegex(ValueError, "finite"):
            self.problem.decode([np.nan, 0.5, 0.2, 1, 1])
        invalid = self.config["reference_allocation"]["values"].copy()
        invalid["unsupported"] = 1
        with self.assertRaisesRegex(ValueError, "keys mismatch"):
            self.problem.decode(invalid)

    def test_each_constraint_family_uses_positive_violation_residuals(self):
        prediction = {
            "prediction__papers_t1": 10.0,
            "lower__papers_t1": 9.0,
            "upper__papers_t1": 11.0,
            "prediction__citation_percentile_avg": 0.6,
            "lower__citation_percentile_avg": 0.58,
            "upper__citation_percentile_avg": 0.62,
        }
        overloaded = {
            "research_budget": 20_000_000.0,
            "frac_research_phd": 0.8,
            "frac_research_other": 0.6,
            "centres_of_excellence_count": 5.0,
            "industry_collaboration_support_count": 10.0,
        }
        residuals, _, normalized = self.problem._constraints(overloaded, prediction)
        self.assertGreater(residuals["budget"], 0)
        self.assertGreater(residuals["faculty_time_capacity"], 0)
        self.assertGreater(residuals["teaching_floor"], 0)
        self.assertGreater(residuals["student_support_floor"], 0)
        self.assertGreater(residuals["service_floor"], 0)
        self.assertGreater(sum(normalized.values()), 0)

        underfunded = dict(overloaded)
        underfunded["research_budget"] = 1_000_000.0
        residuals, _, _ = self.problem._constraints(underfunded, prediction)
        self.assertGreater(residuals["dependency__centre_funding"], 0)
        self.assertFalse(residuals["dependency__collaboration_funding"] > 0)

        mixed = dict(underfunded)
        mixed["centres_of_excellence_count"] = 2.5
        mixed["research_budget"] = 950_000.0
        residuals, _, _ = self.problem._constraints(mixed, prediction)
        self.assertGreater(residuals["bounds__research_budget"], 0)
        self.assertGreater(residuals["integrality__centres_of_excellence_count"], 0)
        self.assertGreater(residuals["increment__centres_of_excellence_count"], 0)

    def test_uncertain_service_uses_conservative_bound_without_fake_probability(self):
        config = copy.deepcopy(self.config)
        config["uncertain_service_constraints"] = [
            {
                "name": "minimum_publications_service",
                "kpi": "papers_t1",
                "direction": "minimum",
                "threshold": 12.5,
                "rule": "conservative_interval",
            }
        ]
        result = AllocationProblem(config, self.model).evaluate(
            config["reference_allocation"]["values"]
        )
        self.assertFalse(result.nominal_feasible)
        self.assertFalse(result.robust_feasible)
        self.assertIsNone(result.estimated_probability_feasible)
        self.assertIn("not_a_joint_probability", result.feasibility_probability_status)


class AllocationConfigurationTests(unittest.TestCase):
    def test_unsupported_model_input_and_missing_kpi_error(self):
        config = fixture_config()
        config["fixed_context"]["compute_capacity_units"] = 2
        with self.assertRaisesRegex(ProblemConfigurationError, "unsupported"):
            AllocationProblem(config, FakePredictionModel())

        config = fixture_config()
        config["objective_families"]["innovation"] = {
            "missing_kpi_policy": "error",
            "components": [
                {
                    "kpi": "patents",
                    "direction": "maximize",
                    "weight": 1.0,
                    "normalization": {"method": "minmax", "minimum": 0, "maximum": 10},
                }
            ],
        }
        with self.assertRaisesRegex(ProblemConfigurationError, "unsupported KPI"):
            AllocationProblem(config, FakePredictionModel())

    def test_impossible_budget_faculty_floor_and_dependency_are_rejected(self):
        config = fixture_config()
        config["budget_limit"] = 1
        with self.assertRaisesRegex(ProblemConfigurationError, "minimum decision bounds"):
            AllocationProblem(config, FakePredictionModel())

        config = fixture_config()
        config["faculty_time"]["minimum_teaching_fte"] = 200
        with self.assertRaisesRegex(ProblemConfigurationError, "floors exceed"):
            AllocationProblem(config, FakePredictionModel())

        config = fixture_config()
        variable = next(
            item for item in config["decision_variables"] if item["name"] == "centres_of_excellence_count"
        )
        variable["lower"] = 5
        config["dependencies"][0]["minimum_funding_per_unit"] = 5_000_000
        with self.assertRaisesRegex(ProblemConfigurationError, "impossible within"):
            AllocationProblem(config, FakePredictionModel())


if __name__ == "__main__":
    unittest.main()
