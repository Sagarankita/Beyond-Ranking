import json
import unittest
from dataclasses import replace
from pathlib import Path

import pandas as pd

from department_optimizer.allocation import (
    AllocationProblem,
    CanonicalNSGA2Adapter,
    RionAllocationAdapter,
)
from department_optimizer.allocation.optimizers import _dominates


REPO_ROOT = Path(__file__).resolve().parents[1]


class DeterministicModel:
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
        papers = frame["research_budget"] / 1_000_000 + frame["centres_of_excellence_count"]
        citation = 0.5 + 0.1 * frame["frac_research_phd"]
        return pd.DataFrame(
            {
                "out_of_support": False,
                "out_of_support_features": "",
                "prediction__papers_t1": papers,
                "lower__papers_t1": papers - 1,
                "upper__papers_t1": papers + 1,
                "prediction__citation_percentile_avg": citation,
                "lower__citation_percentile_avg": citation - 0.01,
                "upper__citation_percentile_avg": citation + 0.01,
            },
            index=frame.index,
        )


def problem():
    config = json.loads(
        (REPO_ROOT / "configs/allocation/legacy_synthetic_method_fixture.json").read_text()
    )
    return AllocationProblem(config, DeterministicModel())


class DominanceTests(unittest.TestCase):
    def test_feasibility_first_then_pareto_dominance(self):
        shared = problem()
        baseline = shared.evaluate(shared.config["reference_allocation"]["values"])
        better_objective = replace(
            baseline,
            objective_scores={**baseline.objective_scores, "research": baseline.objective_scores["research"] - 1},
        )
        infeasible_better = replace(
            better_objective,
            normalized_violation=0.1,
            nominal_feasible=False,
        )
        more_infeasible = replace(infeasible_better, normalized_violation=0.2)
        self.assertTrue(_dominates(baseline, infeasible_better))
        self.assertTrue(_dominates(infeasible_better, more_infeasible))
        self.assertTrue(_dominates(better_objective, baseline))


class AdapterContractTests(unittest.TestCase):
    def assert_contract(self, result, shared, algorithm):
        self.assertEqual(len(result.population), 6)
        self.assertGreater(len(result.archive), 0)
        self.assertEqual(set(result.population["algorithm"]), {algorithm})
        self.assertTrue(result.population["feasible"].all())
        self.assertTrue((result.population["normalized_violation"] <= 1e-12).all())
        self.assertTrue(
            {
                "objective__research",
                "objective__innovation",
                "objective__student",
                "objective__societal",
                "kpi__papers_t1",
                "lower__papers_t1",
                "upper__papers_t1",
                "constraint__budget",
                "cost",
                "pareto_rank",
            }.issubset(result.population.columns)
        )
        for _, row in result.archive.iterrows():
            checked = shared.evaluate({name: row[name] for name in shared.variable_names})
            self.assertTrue(checked.nominal_feasible)
            self.assertEqual(checked.normalized_violation, 0.0)

    def test_canonical_nsga2_uses_shared_contract(self):
        shared = problem()
        result = CanonicalNSGA2Adapter(
            population_size=6, generations=1, seed=7
        ).run(shared)
        self.assert_contract(result, shared, "nsga2")
        self.assertEqual(result.accounting["requested_total"], 12)
        self.assertEqual(result.accounting["inner_pso_evaluations"], 0)
        self.assertEqual(result.accounting["candidate_evaluations_total"], 12)

    def test_rion_uses_shared_contract_and_counts_inner_pso(self):
        shared = problem()
        result = RionAllocationAdapter(
            population_size=6, generations=1, pso_iterations=1, seed=7
        ).run(shared)
        self.assert_contract(result, shared, "rion")
        self.assertGreater(result.accounting["inner_pso_evaluation_requests"], 0)
        self.assertGreater(result.accounting["unique_shared_evaluator_calls_total"], 0)
        self.assertEqual(result.accounting["candidate_evaluations_total"], 24)

    def test_adapters_are_distinct_implementations(self):
        self.assertIsNot(CanonicalNSGA2Adapter, RionAllocationAdapter)
        self.assertNotEqual(CanonicalNSGA2Adapter.name, RionAllocationAdapter.name)


if __name__ == "__main__":
    unittest.main()
