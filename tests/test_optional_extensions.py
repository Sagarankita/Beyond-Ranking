import json
import unittest
from types import SimpleNamespace

import pandas as pd

from department_optimizer.extensions.assessment import assess_extensions
from department_optimizer.target_cost.optimizer import TargetCostOptimizer


class LinearTargetProblem:
    variable_names = ["spend"]
    variables = [
        {
            "name": "spend",
            "lower": 0.0,
            "upper": 10.0,
            "increment": 1.0,
            "type": "continuous",
            "cost_mode": "direct_money",
        }
    ]
    model = SimpleNamespace(manifest={"target_columns": ["outcome"]})
    config = {
        "objective_families": {
            "research": {"components": [{"kpi": "outcome"}]},
            "innovation": {"components": []},
            "student": {"components": []},
            "societal": {"components": []},
        }
    }

    def evaluate(self, candidate):
        value = float(candidate[0] if not isinstance(candidate, dict) else candidate["spend"])
        value = min(10.0, max(0.0, round(value)))
        return SimpleNamespace(
            repaired={"spend": value},
            raw_kpis={"outcome": value},
            objective_benefits={"research": value / 10.0},
            normalized_violation=0.0,
            nominal_feasible=True,
            cost=value,
        )


class TargetCostTests(unittest.TestCase):
    def test_hand_solvable_minimum_cost_target(self):
        target = [{"kind": "kpi", "name": "outcome", "direction": "minimum", "value": 4.0}]
        result = TargetCostOptimizer(
            population_size=8, generations=3, evaluation_budget=60, seed=9
        ).run(LinearTargetProblem(), target)
        self.assertEqual(result.status, "target_feasible")
        self.assertEqual(result.evaluation.cost, 4.0)
        self.assertLessEqual(result.accounting["candidate_evaluations_total"], 60)

    def test_unsupported_objective_target_does_not_run_search(self):
        target = [
            {
                "kind": "objective_benefit",
                "name": "innovation",
                "direction": "minimum",
                "value": 0.2,
            }
        ]
        result = TargetCostOptimizer(seed=1).run(LinearTargetProblem(), target)
        self.assertEqual(result.status, "unsupported_targets")
        self.assertEqual(result.accounting["candidate_evaluations_total"], 0)


class ExtensionEvidenceTests(unittest.TestCase):
    def test_cross_section_without_links_is_deferred(self):
        frame = pd.DataFrame({"college_id": [1, 2], "papers": [3, 4]})
        provenance = {"datasets": [{"provenance": "synthetic"}]}
        config = {
            "required_network_dea": {
                "unit_identifier_candidates": ["college_id"],
                "stage_link_candidates": ["projects_completed"],
                "minimum_comparable_units": 2,
            },
            "required_multiperiod": {
                "unit_identifier_candidates": ["college_id"],
                "period_candidates": ["year"],
                "minimum_periods_per_unit": 2,
                "minimum_distinct_periods": 2,
            },
        }
        result = assess_extensions(frame, provenance, config)
        self.assertEqual(result["network_dea"]["status"], "deferred_evidence_gap")
        self.assertEqual(
            result["multi_period_planning"]["status"], "deferred_evidence_gap"
        )

    def test_observed_linked_longitudinal_fixture_passes_evidence_gate(self):
        frame = pd.DataFrame(
            {
                "department_id": [1, 1, 2, 2],
                "year": [2024, 2025, 2024, 2025],
                "projects_completed": [1, 2, 2, 3],
            }
        )
        provenance = {"datasets": [{"provenance": "observed"}]}
        config = {
            "required_network_dea": {
                "unit_identifier_candidates": ["department_id"],
                "stage_link_candidates": ["projects_completed"],
                "minimum_comparable_units": 2,
            },
            "required_multiperiod": {
                "unit_identifier_candidates": ["department_id"],
                "period_candidates": ["year"],
                "minimum_periods_per_unit": 2,
                "minimum_distinct_periods": 2,
            },
        }
        result = assess_extensions(frame, provenance, config)
        self.assertEqual(result["network_dea"]["status"], "supported")
        self.assertEqual(result["multi_period_planning"]["status"], "supported")


if __name__ == "__main__":
    unittest.main()
