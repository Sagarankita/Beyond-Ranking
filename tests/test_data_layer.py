import copy
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from data.datagen import generate_legacy_synthetic
from department_optimizer.data.audit import audit_dataset, verify_legacy_generator
from department_optimizer.data.scenario import (
    allocation_cost,
    load_scenario,
    validate_scenario_config,
)
from department_optimizer.data.schemas import get_schema
from department_optimizer.data.validation import validate_dataframe


REPO_ROOT = Path(__file__).resolve().parents[1]


def valid_observed_record():
    return {
        "department_id": "CEIT",
        "institution_id": "VJTI",
        "period_start": "2025-07-01",
        "period_end": "2026-06-30",
        "source_id": "annual-report-2026",
        "provenance": "observed",
        "is_imputed": False,
        "currency": "INR",
        "currency_base_year": 2026,
        "faculty_phd": 25,
        "faculty_other": 5,
        "faculty_research_fte": 12.5,
        "research_budget": 10000000.0,
        "teaching_load_per_faculty": 8.0,
        "student_count": 700,
    }


class SchemaValidationTests(unittest.TestCase):
    def test_validation_is_column_order_independent(self):
        record = valid_observed_record()
        reversed_frame = pd.DataFrame([{key: record[key] for key in reversed(record)}])
        report = validate_dataframe(
            reversed_frame, get_schema("observed_department_period")
        )
        self.assertFalse(report.has_errors, report.to_dict())

    def test_missing_nonfinite_fractional_unit_duplicate_and_source_conflict(self):
        first = valid_observed_record()
        second = valid_observed_record()
        first["faculty_phd"] = 2.5
        first["research_budget"] = float("inf")
        first["currency"] = "USD"
        second["source_id"] = "conflicting-source"
        del second["faculty_other"]
        frame = pd.DataFrame([first, second])
        report = validate_dataframe(frame, get_schema("observed_department_period"))
        codes = {issue.code for issue in report.issues}
        self.assertTrue(
            {
                "missing_values",
                "nonfinite_values",
                "noninteger_counts",
                "invalid_unit_or_category",
                "duplicate_primary_key",
                "source_conflict",
            }.issubset(codes),
            report.to_dict(),
        )

    def test_scenario_bounds_warn_without_mutating_history(self):
        frame = pd.read_csv(REPO_ROOT / "data/department_research_data.csv")
        before = frame.copy(deep=True)
        report = validate_dataframe(
            frame,
            get_schema("legacy_synthetic_research"),
            scenario_bounds={"teaching_load_per_faculty": (2, 15), "overall_rank": (1, 200)},
        )
        self.assertEqual(len(report.by_code("outside_scenario_bounds")), 2)
        pd.testing.assert_frame_equal(frame, before)


class ScenarioTests(unittest.TestCase):
    def setUp(self):
        self.path = REPO_ROOT / "configs/scenarios/baseline.synthetic.json"
        self.config = load_scenario(self.path)

    def test_example_scenario_is_valid_and_cost_is_unambiguous(self):
        report = validate_scenario_config(self.config)
        self.assertFalse(report.has_errors, report.to_dict())
        cost = allocation_cost(
            {"research_seed_funding": 1_000_000, "research_assistant_count": 2},
            self.config,
        )
        self.assertEqual(cost, 2_200_000)

    def test_double_counting_is_rejected(self):
        invalid = copy.deepcopy(self.config)
        invalid["decision_variables"][0]["unit_cost"] = 100
        report = validate_scenario_config(invalid)
        self.assertTrue(report.has_errors)
        self.assertTrue(report.by_code("potential_double_count"))

    def test_incremental_scenario_requires_baseline(self):
        invalid = copy.deepcopy(self.config)
        invalid["allocation_semantics"] = "incremental"
        invalid["baseline_reference"] = None
        self.assertTrue(
            validate_scenario_config(invalid).by_code("missing_baseline_reference")
        )

    def test_infeasible_minimum_capacity_is_rejected(self):
        invalid = copy.deepcopy(self.config)
        invalid["faculty_time_capacity_fte"] = 1.0
        self.assertTrue(
            validate_scenario_config(invalid).by_code(
                "infeasible_minimum_faculty_time"
            )
        )


class GeneratorAndAuditTests(unittest.TestCase):
    def test_generator_is_reproducible_and_labeled(self):
        first = generate_legacy_synthetic(20, seed=9)
        second = generate_legacy_synthetic(20, seed=9)
        pd.testing.assert_frame_equal(first, second)
        self.assertEqual(set(first["provenance"]), {"synthetic"})
        self.assertEqual(set(first["generator_seed"]), {9})
        self.assertEqual(set(first["is_imputed"]), {False})
        self.assertIn("response_model_id", first)

    def test_committed_fixture_matches_legacy_generator_values(self):
        frame = pd.read_csv(REPO_ROOT / "data/department_research_data.csv")
        verification = verify_legacy_generator(frame)
        self.assertTrue(verification["value_match"], verification)
        self.assertLessEqual(verification["maximum_absolute_difference"], 2e-7)

    def test_audit_writes_reproducible_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            audit = audit_dataset(
                REPO_ROOT / "data/department_research_data.csv",
                output,
                "legacy_synthetic_research",
                REPO_ROOT / "configs/scenarios/baseline.synthetic.json",
                REPO_ROOT / "configs/legacy_optimizer_bounds.json",
            )
            self.assertFalse(audit["validation"]["has_errors"])
            self.assertTrue(audit["generator_verification"]["value_match"])
            self.assertFalse(audit["source_data_mutated"])
            self.assertFalse(audit["scenario_validation"]["has_errors"])
            for name in (
                "audit.json",
                "column_summary.csv",
                "validation_issues.csv",
                "objective_inventory.csv",
                "data_dictionary.json",
            ):
                self.assertTrue((output / name).is_file(), name)
            reloaded = json.loads((output / "audit.json").read_text())
            self.assertEqual(reloaded["sha256"], audit["sha256"])


if __name__ == "__main__":
    unittest.main()
