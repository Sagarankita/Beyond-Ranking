import unittest

import numpy as np
import pandas as pd

from department_optimizer.efficiency.dea import (
    DEAConfig,
    DEADataError,
    run_input_vrs_dea,
)


def fixture():
    return pd.DataFrame(
        {
            "dmu": ["A", "B", "C"],
            "period": ["2026", "2026", "2026"],
            "input": [1.0, 2.0, 2.0],
            "output": [1.0, 1.0, 2.0],
        }
    )


def config():
    return DEAConfig(
        dmu_column="dmu",
        input_columns=("input",),
        output_columns=("output",),
        cohort_name="hand-fixture",
        cohort_columns=("period",),
    )


class DEAMathematicalTests(unittest.TestCase):
    def test_hand_solvable_vrs_frontier(self):
        analysis = run_input_vrs_dea(fixture(), config())
        scores = analysis.efficiency.set_index("dmu")
        self.assertAlmostEqual(scores.loc["A", "efficiency_score"], 1.0, places=7)
        self.assertAlmostEqual(scores.loc["B", "efficiency_score"], 0.5, places=7)
        self.assertAlmostEqual(scores.loc["C", "efficiency_score"], 1.0, places=7)
        self.assertAlmostEqual(scores.loc["B", "target_input__input"], 1.0, places=7)
        self.assertAlmostEqual(scores.loc["B", "target_output__output"], 1.0, places=7)
        b_peers = analysis.peers[analysis.peers["evaluated_dmu"] == "B"]
        self.assertEqual(b_peers["peer_dmu"].tolist(), ["A"])
        self.assertAlmostEqual(b_peers["lambda_weight"].iloc[0], 1.0, places=7)
        self.assertTrue(all(scores["solver_status"] == "optimal"))

    def test_efficiency_is_invariant_to_positive_unit_rescaling(self):
        original = run_input_vrs_dea(fixture(), config()).efficiency
        scaled = fixture()
        scaled["input"] *= 1_000_000
        scaled["output"] *= 100
        converted = run_input_vrs_dea(scaled, config()).efficiency
        np.testing.assert_allclose(
            original["efficiency_score"], converted["efficiency_score"], atol=1e-8
        )

    def test_small_cohort_reports_poor_discrimination(self):
        summary = run_input_vrs_dea(fixture(), config()).summary
        self.assertGreaterEqual(len(summary["discrimination_warnings"]), 1)
        self.assertEqual(summary["discrimination_heuristic_minimum_dmus"], 6)


class DEAValidationTests(unittest.TestCase):
    def assert_data_error(self, frame, pattern):
        with self.assertRaisesRegex(DEADataError, pattern):
            run_input_vrs_dea(frame, config())

    def test_missing_values_are_rejected(self):
        frame = fixture()
        frame.loc[0, "input"] = np.nan
        self.assert_data_error(frame, "missing or non-numeric")

    def test_nonfinite_values_are_rejected(self):
        frame = fixture()
        frame.loc[0, "output"] = np.inf
        self.assert_data_error(frame, "non-finite")

    def test_zero_and_negative_inputs_are_rejected(self):
        for value in (0.0, -1.0):
            with self.subTest(value=value):
                frame = fixture()
                frame.loc[0, "input"] = value
                self.assert_data_error(frame, "strictly positive inputs")

    def test_negative_and_all_zero_outputs_are_rejected(self):
        negative = fixture()
        negative.loc[0, "output"] = -1.0
        self.assert_data_error(negative, "non-negative")
        zero = fixture()
        zero.loc[0, "output"] = 0.0
        self.assert_data_error(zero, "at least one positive output")

    def test_constant_variables_are_rejected(self):
        frame = fixture()
        frame["input"] = 1.0
        self.assert_data_error(frame, "no discrimination")

    def test_incomparable_cohorts_are_rejected(self):
        frame = fixture()
        frame.loc[2, "period"] = "2025"
        self.assert_data_error(frame, "incomparable cohort")

    def test_duplicate_dmu_identifiers_are_rejected(self):
        frame = fixture()
        frame.loc[1, "dmu"] = "A"
        self.assert_data_error(frame, "must be unique")


if __name__ == "__main__":
    unittest.main()
