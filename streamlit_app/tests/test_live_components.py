from __future__ import annotations

import unittest

from streamlit_app.components.charts import (
    live_allocation_figure,
    objective_score_figure,
    recommendation_objective_figure,
)
from streamlit_app.components.live import allocation_rows, candidate_label


class LiveComponentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validation = {
            "config": {
                "decision_variables": [
                    {"name": "research_seed_funding", "unit": "INR"},
                    {"name": "research_faculty_effort", "unit": "annual FTE"},
                ],
                "reference_allocation": {
                    "research_seed_funding": 3_000_000,
                    "research_faculty_effort": 2.5,
                },
            }
        }
        self.candidate = {
            "candidate_id": "abcdef1234567890",
            "decisions": {
                "research_seed_funding": 4_000_000,
                "research_faculty_effort": 3.0,
            },
            "objectives": {
                "research": {"benefit": 0.7, "evidence": "synthetic_scenario"},
                "student_development": {"benefit": 0.8, "evidence": "synthetic_scenario"},
            },
        }

    def test_allocation_rows_preserve_exact_values_and_units(self) -> None:
        rows = allocation_rows(self.validation, self.candidate)
        funding = rows[rows["variable"] == "research_seed_funding"].iloc[0]
        self.assertEqual(3_000_000, funding["reference"])
        self.assertEqual(4_000_000, funding["proposed"])
        self.assertEqual(1_000_000, funding["delta"])
        self.assertEqual("INR", funding["unit"])

    def test_allocation_chart_never_mixes_units(self) -> None:
        rows = allocation_rows(self.validation, self.candidate)
        figure = live_allocation_figure(rows, "annual FTE")
        self.assertEqual("annual FTE", figure.layout.xaxis.title.text)
        for trace in figure.data:
            self.assertEqual(["Research Faculty Effort"], list(trace.y))

    def test_candidate_label_and_objective_scale_are_explainable(self) -> None:
        label = candidate_label(self.candidate, 0)
        self.assertIn("Student Development emphasis", label)
        figure = objective_score_figure(self.candidate)
        self.assertEqual((0, 1), tuple(figure.layout.xaxis.range))

    def test_objective_toggle_uses_exact_backend_differences(self) -> None:
        rows = [
            {
                "name": "research",
                "reference": 0.412345678,
                "proposed": 0.501234567,
                "difference": 0.088888889,
                "scale": "normalized modeled benefit [0, 1]",
                "evidence": "synthetic_scenario",
                "components": [{"kpi": "q1_publications", "weight": 0.55}],
            },
            {
                "name": "innovation",
                "reference": 0.6,
                "proposed": 0.55,
                "difference": -0.05,
                "scale": "normalized modeled benefit [0, 1]",
                "evidence": "synthetic_scenario",
                "components": [{"kpi": "patent_applications", "weight": 0.55}],
            },
        ]
        scores = recommendation_objective_figure(rows, mode="scores")
        changes = recommendation_objective_figure(rows, mode="changes")
        self.assertEqual((0, 1), tuple(scores.layout.xaxis.range))
        self.assertEqual(
            [item["difference"] for item in rows], list(changes.data[0].x)
        )
        self.assertEqual("#14785b", changes.data[0].marker.color[0])
        self.assertEqual("#b55d43", changes.data[0].marker.color[1])
        self.assertIn("score points", changes.layout.xaxis.title.text)

    def test_objective_chart_handles_non_comparable_rows(self) -> None:
        figure = recommendation_objective_figure(
            [
                {
                    "name": "research",
                    "reference": None,
                    "proposed": 0.4,
                    "difference": None,
                    "scale": "unsupported",
                }
            ],
            mode="changes",
        )
        self.assertEqual(1, len(figure.layout.annotations))


if __name__ == "__main__":
    unittest.main()
