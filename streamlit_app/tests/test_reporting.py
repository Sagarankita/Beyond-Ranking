from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from streamlit_app.api.schemas import RunCreateRequest
from streamlit_app.api.service import DashboardRunService
from streamlit_app.reporting import build_professor_summary


class ProfessorReportTests(unittest.TestCase):
    def test_summary_contains_structured_facts_and_reproduction_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = DashboardRunService(Path(directory), synchronous=True)
            try:
                status = service.create_run(
                    RunCreateRequest(
                        overrides={"budget_limit": 30_000_000},
                        algorithm="nsga2",
                        seed=19301,
                        evaluation_budget=16,
                    )
                )
                recommendation = service.recommendations(status["run_id"])[
                    "recommendations"
                ][0]
                summary = build_professor_summary(
                    run_status=status,
                    recommendation=recommendation,
                )
            finally:
                service.close()

        self.assertIn(status["run_id"], summary)
        self.assertIn(status["scenario_hash"], summary)
        self.assertIn(recommendation["candidate_id"], summary)
        self.assertIn("Proposed allocation changes", summary)
        self.assertIn("Modeled objective trade-offs", summary)
        self.assertIn("Uncertainty and assumptions", summary)
        self.assertIn("not a policy directive or causal impact estimate", summary)
        self.assertNotIn("—", summary)


if __name__ == "__main__":
    unittest.main()
