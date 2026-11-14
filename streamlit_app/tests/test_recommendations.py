from __future__ import annotations

import copy
import tempfile
import unittest
import warnings
from pathlib import Path

warnings.filterwarnings(
    "ignore",
    message="Using `httpx` with `starlette.testclient` is deprecated.*",
)

from fastapi.testclient import TestClient

from department_optimizer.public_allocation.problem import FAMILIES, VJTIPublicAllocationProblem
from streamlit_app.api.app import create_app
from streamlit_app.api.recommendations import build_recommendations
from streamlit_app.api.schemas import RunCreateRequest, SensitivityRequest
from streamlit_app.api.service import DashboardRunService, DashboardServiceError
from streamlit_app.data.integration_contract import REPOSITORY_ROOT, VJTI_MODEL_ROOT
from streamlit_app.pages.advisor import build_action_cards, objective_interpretation_example


class RecommendationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.service = DashboardRunService(
            Path(cls.temporary_directory.name) / "runs", synchronous=True
        )
        cls.request = RunCreateRequest(
            overrides={"budget_limit": 30_000_000},
            algorithm="nsga2",
            seed=19001,
            evaluation_budget=16,
        )
        cls.status = cls.service.create_run(cls.request)
        if cls.status["status"] != "complete":
            raise RuntimeError(cls.status)
        cls.package = cls.service.recommendations(cls.status["run_id"])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.service.close()
        cls.temporary_directory.cleanup()

    def test_profiles_are_deterministic_and_duplicates_are_disclosed(self) -> None:
        repeated = self.service.recommendations(self.status["run_id"])
        self.assertEqual(self.package, repeated)
        self.assertEqual("supported", self.package["status"])
        self.assertEqual(
            {"balanced", "research_focused", "innovation_focused", "student_focused", "robust"},
            {item["profile"] for item in self.package["profile_results"]},
        )
        self.assertTrue(any(item["status"] == "duplicate" for item in self.package["profile_results"]))

    def test_actions_and_totals_reconcile_without_mixing_units(self) -> None:
        for recommendation in self.package["recommendations"]:
            monetary_effect = sum(
                item["budget_effect"] or 0.0 for item in recommendation["decision_changes"]
            )
            self.assertAlmostEqual(recommendation["budget"]["delta"], monetary_effect)
            self.assertLessEqual(
                recommendation["budget"]["proposed"], recommendation["budget"]["limit"]
            )
            for item in recommendation["decision_changes"]:
                if item["unit"] == "annual FTE":
                    self.assertIsNone(item["budget_effect"])
            self.assertTrue(recommendation["nominal_feasible"])
            self.assertIn("robust_feasible", recommendation)
            self.assertNotEqual(
                "Monte Carlo robustness probability", recommendation["robustness_definition"]
            )

    def test_action_cards_rank_verified_changes_and_preserve_units(self) -> None:
        recommendation = self.package["recommendations"][0]
        cards = build_action_cards(recommendation)
        changed_count = sum(
            item["action"] != "retain" for item in recommendation["decision_changes"]
        )
        self.assertEqual(min(changed_count, 5), len(cards))
        self.assertEqual(
            sorted((item["impact_score"] for item in cards), reverse=True),
            [item["impact_score"] for item in cards],
        )
        self.assertTrue(all(item["action"] in {"increase", "decrease"} for item in cards))
        self.assertTrue(all(item["before_display"] and item["after_display"] for item in cards))
        self.assertTrue(all(item["uncertainty_warning"] for item in cards))

    def test_objective_metadata_reconstructs_exact_displayed_scores(self) -> None:
        recommendation = self.package["recommendations"][0]
        for objective in recommendation["objective_deltas"]:
            self.assertEqual("normalized modeled benefit [0, 1]", objective["scale"])
            self.assertEqual("higher_is_preferred", objective["display_direction"])
            self.assertEqual("minimize_negative_benefit", objective["optimizer_direction"])
            self.assertTrue(objective["bounded"])
            self.assertAlmostEqual(
                objective["proposed"],
                sum(item["proposed_weighted_benefit"] for item in objective["components"]),
            )
            self.assertAlmostEqual(
                1.0, sum(item["weight"] for item in objective["components"])
            )
            self.assertAlmostEqual(
                objective["difference"],
                objective["proposed"] - objective["reference"],
            )
        example = objective_interpretation_example(recommendation["objective_deltas"])
        self.assertIsNotNone(example)
        largest = max(
            recommendation["objective_deltas"],
            key=lambda item: abs(item["difference"]),
        )
        self.assertIn(f"{largest['difference']:+.6f}", example)
        self.assertIn("not a measured outcome change", example)

    def test_action_cards_handle_zero_reference_missing_evidence_and_no_change(self) -> None:
        recommendation = copy.deepcopy(self.package["recommendations"][0])
        recommendation["decision_changes"] = [
            {
                "variable": "unmapped_activity",
                "action": "increase",
                "before": 0.0,
                "after": 2.0,
                "delta": 2.0,
                "unit": "headcount",
                "budget_effect": None,
                "cost_mode": "non_monetary",
                "provenance": "synthetic_calibrated",
            }
        ]
        recommendation["objective_deltas"] = []
        recommendation["constraint_evidence"] = []
        recommendation["uncertainty"] = []
        recommendation["support_warnings"] = []
        cards = build_action_cards(recommendation)
        self.assertEqual(1, len(cards))
        self.assertIsNone(cards[0]["percentage_change"])
        self.assertIn("no outcome rationale is inferred", cards[0]["explanation"].lower())
        self.assertIn("no stored kpi interval", cards[0]["uncertainty_warning"].lower())

        recommendation["decision_changes"][0].update(
            action="retain", before=2.0, after=2.0, delta=0.0
        )
        self.assertEqual([], build_action_cards(recommendation))

    def test_invalid_candidate_and_missing_reference_abstain(self) -> None:
        config = self.service.base_config
        problem = VJTIPublicAllocationProblem(config, REPOSITORY_ROOT / VJTI_MODEL_ROOT)
        invalid = copy.deepcopy(self.service.candidates(self.status["run_id"])[0])
        invalid["revalidated"] = False
        result = build_recommendations(
            run_status=self.status,
            candidates=[invalid],
            problem=problem,
            experiment_config=self.service.experiment_config,
        )
        self.assertEqual("no_supported_recommendation", result["status"])
        no_reference_config = copy.deepcopy(config)
        no_reference_config.pop("reference_allocation")
        no_reference_problem = VJTIPublicAllocationProblem(
            no_reference_config, REPOSITORY_ROOT / VJTI_MODEL_ROOT
        )
        result = build_recommendations(
            run_status=self.status,
            candidates=self.service.candidates(self.status["run_id"]),
            problem=no_reference_problem,
            experiment_config=self.service.experiment_config,
        )
        self.assertEqual("no_supported_recommendation", result["status"])
        self.assertIn("reference", result["reason"].lower())

    def test_out_of_support_candidate_has_visible_warning(self) -> None:
        config = copy.deepcopy(self.service.base_config)
        config["budget_limit"] = 100_000_000
        problem = VJTIPublicAllocationProblem(config, REPOSITORY_ROOT / VJTI_MODEL_ROOT)
        decisions = copy.deepcopy(config["reference_allocation"])
        for variable in config["decision_variables"]:
            if variable["cost_mode"] != "non_monetary":
                decisions[variable["name"]] = variable["upper"]
        decisions["research_faculty_effort"] = 6.0
        decisions["student_support_faculty_effort"] = 1.5
        decisions["service_faculty_effort"] = 2.0
        evaluation = problem.evaluate_fixed(decisions)
        self.assertTrue(evaluation.feasible)
        self.assertTrue(evaluation.support_flags["out_of_model_support"])
        candidate = {
            "candidate_id": "f" * 24,
            "run_id": self.status["run_id"],
            "scenario_hash": self.status["scenario_hash"],
            "revalidated": True,
            "feasible": True,
            "robust_feasible": True,
            "decisions": decisions,
            "objectives": {
                family: {"benefit": evaluation.objective_benefits[family]}
                for family in FAMILIES
            },
        }
        package = build_recommendations(
            run_status=self.status,
            candidates=[candidate],
            problem=problem,
            experiment_config=self.service.experiment_config,
        )
        warnings = package["recommendations"][0]["support_warnings"]
        self.assertTrue(any(item["code"] == "out_of_model_support" for item in warnings))

    def test_sensitivity_keeps_held_fixed_and_reoptimization_separate(self) -> None:
        context = self.service.create_sensitivity(
            self.status["run_id"],
            SensitivityRequest(factor="faculty_total", new_value=16, profile="balanced"),
        )
        result = self.service.sensitivity_result(
            self.status["run_id"], context["sensitivity_run_id"]
        )
        self.assertEqual("complete", result["status"])
        self.assertEqual("held_fixed_without_repair", result["held_fixed"]["assessment_mode"])
        self.assertEqual("reoptimized", result["reoptimized"]["assessment_mode"])
        self.assertEqual(self.status["algorithm"], result["algorithm"])
        self.assertEqual(self.status["seed"], result["seed"])
        self.assertEqual(self.status["evaluation_budget"], result["evaluation_budget"])
        self.assertIn("causal effect", result["interpretation"].lower())

    def test_structured_endpoints_return_ids_rules_and_provenance(self) -> None:
        with TestClient(create_app(self.service)) as client:
            response = client.get(f"/runs/{self.status['run_id']}/recommendations")
            self.assertEqual(200, response.status_code)
            recommendation = response.json()["recommendations"][0]
            self.assertEqual(self.status["run_id"], recommendation["source_run_id"])
            self.assertEqual(self.status["scenario_hash"], recommendation["scenario_id"])
            self.assertTrue(recommendation["selection_rule"])
            self.assertTrue(recommendation["candidate_id"])
            self.assertTrue(recommendation["recommendation_id"])
            self.assertEqual(
                "VJTIPublicAllocationProblem",
                recommendation["data_dependencies"]["evaluator"],
            )
        with self.assertRaises(DashboardServiceError):
            self.service.sensitivity_result(self.status["run_id"], "../../outside")


if __name__ == "__main__":
    unittest.main()
