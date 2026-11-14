from __future__ import annotations

import copy
import json
import unittest

import pandas as pd

from department_optimizer.public_allocation.problem import VJTIPublicAllocationProblem
from streamlit_app.data.integration_contract import (
    FINAL_BENCHMARK_METRICS_PATH,
    FIXTURE_PATH,
    REPOSITORY_ROOT,
    VJTI_ARCHIVE_PATH,
    VJTI_CONFIG_PATH,
    VJTI_MODEL_ROOT,
    build_vjti_contract_fixture,
    canonical_sha256,
    file_sha256,
    validate_contract_fixture,
)


class DashboardIntegrationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_committed_fixture_schema_and_source_hashes(self):
        validate_contract_fixture(self.fixture)
        for relative, expected_hash in self.fixture["source_hashes"].items():
            self.assertEqual(file_sha256(REPOSITORY_ROOT / relative), expected_hash)

    def test_real_saved_candidate_reaches_canonical_evaluator(self):
        config = json.loads((REPOSITORY_ROOT / VJTI_CONFIG_PATH).read_text(encoding="utf-8"))
        problem = VJTIPublicAllocationProblem(config, REPOSITORY_ROOT / VJTI_MODEL_ROOT)
        decisions = {
            item["name"]: item["value"] for item in self.fixture["candidate"]["decisions"]
        }
        result = problem.evaluate_fixed(decisions)
        saved = self.fixture["candidate"]["evaluation"]

        self.assertTrue(result.feasible)
        self.assertAlmostEqual(result.total_cost, saved["total_cost"], places=6)
        self.assertAlmostEqual(result.budget_remaining, saved["budget_remaining"], places=6)
        self.assertEqual(result.support_flags["out_of_model_support"], saved["out_of_model_support"])
        for objective in saved["objectives"]:
            self.assertAlmostEqual(
                result.objective_benefits[objective["name"]], objective["benefit"], places=10
            )
        for interval in saved["uncertainty"]:
            self.assertAlmostEqual(
                result.raw_kpis[interval["kpi"]], interval["prediction"], places=10
            )

    def test_frozen_fixture_matches_saved_archive_record(self):
        archive = pd.read_csv(REPOSITORY_ROOT / VJTI_ARCHIVE_PATH)
        saved_row = archive.iloc[self.fixture["candidate"]["source_row"]]
        candidate = self.fixture["candidate"]
        evaluation = candidate["evaluation"]

        for decision in candidate["decisions"]:
            self.assertAlmostEqual(saved_row[decision["name"]], decision["value"], places=10)
        self.assertAlmostEqual(saved_row["cost"], evaluation["total_cost"], places=6)
        self.assertEqual(bool(saved_row["feasible"]), evaluation["feasible"])
        for objective in evaluation["objectives"]:
            self.assertAlmostEqual(
                saved_row[f"objective_benefit__{objective['name']}"],
                objective["benefit"],
                places=10,
            )
        for interval in evaluation["uncertainty"]:
            kpi = interval["kpi"]
            self.assertAlmostEqual(saved_row[f"kpi__{kpi}"], interval["prediction"], places=10)
            self.assertAlmostEqual(saved_row[f"lower__{kpi}"], interval["lower"], places=10)
            self.assertAlmostEqual(saved_row[f"upper__{kpi}"], interval["upper"], places=10)
        for constraint in evaluation["constraints"]:
            self.assertAlmostEqual(
                saved_row[f"constraint__{constraint['name']}"], constraint["residual"], places=10
            )

    def test_units_and_evidence_come_from_real_config(self):
        config = json.loads((REPOSITORY_ROOT / VJTI_CONFIG_PATH).read_text(encoding="utf-8"))
        specs = {item["name"]: item for item in config["decision_variables"]}
        for decision in self.fixture["candidate"]["decisions"]:
            spec = specs[decision["name"]]
            self.assertEqual(decision["unit"], spec["unit"])
            self.assertEqual(decision["evidence"], spec["provenance"])
            self.assertGreaterEqual(decision["value"], spec["lower"])
            self.assertLessEqual(decision["value"], spec["upper"])

    def test_scenario_hash_is_stable_and_changes_with_supported_inputs(self):
        current = build_vjti_contract_fixture()
        self.assertEqual(current["scenario"]["scenario_hash"], self.fixture["scenario"]["scenario_hash"])
        payload = {"budget_limit": 36_000_000, "faculty_total": 15}
        reordered = {"faculty_total": 15, "budget_limit": 36_000_000}
        changed = {"budget_limit": 30_000_000, "faculty_total": 15}
        self.assertEqual(canonical_sha256(payload), canonical_sha256(reordered))
        self.assertNotEqual(canonical_sha256(payload), canonical_sha256(changed))

    def test_final_benchmark_is_150_matched_budget_jobs(self):
        benchmark = self.fixture["benchmark"]
        metrics = pd.read_csv(REPOSITORY_ROOT / FINAL_BENCHMARK_METRICS_PATH)
        self.assertEqual((benchmark["configured_jobs"], benchmark["complete_jobs"]), (150, 150))
        self.assertEqual(len(metrics), 150)
        self.assertTrue((metrics["status"] == "complete").all())
        self.assertTrue((metrics["candidate_evaluations"] == benchmark["evaluation_budget"]).all())

    def test_cross_scenario_candidate_is_rejected(self):
        bad = copy.deepcopy(self.fixture)
        bad["candidate"]["scenario_hash"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "different scenario"):
            validate_contract_fixture(bad)


if __name__ == "__main__":
    unittest.main()
