import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from department_optimizer.reporting.runner import build_report, select_portfolio


REPO_ROOT = Path(__file__).resolve().parents[1]


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.config_path = REPO_ROOT / "configs/reporting/phase7_synthetic.json"
        self.config = json.loads(self.config_path.read_text())

    def test_portfolio_flags_duplicates_and_unavailable_knee(self):
        robustness = REPO_ROOT / self.config["robustness_root"]
        allocation = json.loads((REPO_ROOT / self.config["allocation_config"]).read_text())
        reference = json.loads((REPO_ROOT / self.config["reference_evaluation"]).read_text())
        portfolio = select_portfolio(
            self.config,
            allocation,
            pd.read_csv(robustness / "selected_strategies.csv"),
            pd.read_csv(robustness / "reoptimized_candidates.csv"),
            pd.read_csv(robustness / "monte_carlo_summary.csv"),
            reference,
        )
        self.assertEqual(set(portfolio.strategy), {
            "conservative", "balanced", "research_first", "innovation_first",
            "student_first", "compromise",
        })
        self.assertEqual(portfolio.allocation_group.nunique(), 1)
        self.assertTrue(portfolio.duplicates_another_strategy.all())
        compromise = portfolio[portfolio.strategy == "compromise"].iloc[0]
        self.assertIn("fewer_than_two", compromise.knee_status)

    def test_report_builds_from_saved_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = build_report(self.config_path, Path(temporary))
            self.assertTrue((output / "report.md").exists())
            self.assertTrue((output / "strategy_portfolio.csv").exists())
            for name in (
                "pareto_tradeoff.svg",
                "algorithm_comparison.svg",
                "scenario_robustness.svg",
            ):
                text = (output / name).read_text()
                self.assertTrue(text.startswith("<svg"))
            report = (output / "report.md").read_text()
            self.assertIn("Synthetic methodological prototype", report)
            self.assertIn("does not implement or call a second scientific evaluator", report)


if __name__ == "__main__":
    unittest.main()
