from __future__ import annotations

import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

import uvicorn

from streamlit_app.api.app import create_app
from streamlit_app.api.explanations import ExplanationService, ProviderResponse
from streamlit_app.api.schemas import RunCreateRequest
from streamlit_app.api.service import DashboardRunService


class UiExplanationProvider:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, _fact_packet):
        self.calls += 1
        return ProviderResponse(
            content={
                "headline": "A modeled option for faculty review",
                "plain_language_summary": "This modeled option restates the documented selection without changing it.",
                "why_this_option": ["The wording follows the verified profile selection."],
                "tradeoffs": ["The modeled objectives move differently, as shown in the structured evidence."],
                "assumptions_and_caveats": ["The relationships are synthetic and do not establish causation."],
                "source_fact_ids": ["profile_selection", "evidence_boundary"],
            },
            provider="test_provider",
            model="test_model",
            provider_version="test_version",
        )


class AppSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.explanation_provider = UiExplanationProvider()
        cls.service = DashboardRunService(
            Path(cls.temporary_directory.name) / "runs",
            synchronous=True,
            explanation_service=ExplanationService(
                provider=cls.explanation_provider, enabled=True
            ),
        )
        socket_handle = socket.socket()
        socket_handle.bind(("127.0.0.1", 0))
        cls.port = socket_handle.getsockname()[1]
        socket_handle.close()
        cls.server = uvicorn.Server(
            uvicorn.Config(
                create_app(cls.service),
                host="127.0.0.1",
                port=cls.port,
                log_level="error",
            )
        )
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        deadline = time.monotonic() + 5
        while not cls.server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        if not cls.server.started:
            raise RuntimeError("The test API did not start.")
        cls.previous_api_url = os.environ.get("DASHBOARD_API_URL")
        os.environ["DASHBOARD_API_URL"] = f"http://127.0.0.1:{cls.port}"
        cls.live_status = cls.service.create_run(
            RunCreateRequest(
                overrides={"budget_limit": 30_000_000},
                algorithm="nsga2",
                seed=19001,
                evaluation_budget=16,
            )
        )

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.previous_api_url is None:
            os.environ.pop("DASHBOARD_API_URL", None)
        else:
            os.environ["DASHBOARD_API_URL"] = cls.previous_api_url
        cls.server.should_exit = True
        cls.thread.join(timeout=5)
        cls.service.close()
        cls.temporary_directory.cleanup()

    def test_streamlit_app_renders_without_exceptions(self) -> None:
        from streamlit.testing.v1 import AppTest

        app_path = Path(__file__).resolve().parents[1] / "app.py"
        app = AppTest.from_file(str(app_path), default_timeout=30).run()
        self.assertEqual([], list(app.exception))
        self.assertTrue(any(button.label == "Plan resource changes" for button in app.button))
        self.assertTrue(any("Available budget" in metric.label for metric in app.metric))

    def test_professor_can_change_budget_run_and_select_real_strategy(self) -> None:
        from streamlit.testing.v1 import AppTest

        harness = Path(__file__).resolve().parent / "planner_harness.py"
        app = AppTest.from_file(str(harness), default_timeout=30).run()
        budget = next(item for item in app.number_input if item.label == "Available budget (₹ crore)")
        seed = next(item for item in app.number_input if item.label == "Reproducibility seed")
        budget.set_value(3.0)
        seed.set_value(19001)
        run_button = next(item for item in app.button if item.label == "Run optimization")
        app = run_button.click().run(timeout=30)

        self.assertEqual([], list(app.exception))
        self.assertTrue(
            any("Feasible and independently revalidated" in item.value for item in app.success)
        )
        strategy = next(item for item in app.selectbox if item.label == "Selected validated strategy")
        self.assertIsNotNone(strategy.value)
        self.assertTrue(any("Budget headroom" in metric.label for metric in app.metric))

    def test_advisor_traces_recommendation_and_runs_factor_case(self) -> None:
        from streamlit.testing.v1 import AppTest

        harness = Path(__file__).resolve().parent / "advisor_harness.py"
        app = AppTest.from_file(str(harness), default_timeout=30)
        app.session_state["br_run_status"] = self.live_status
        app = app.run()
        self.assertEqual([], list(app.exception))
        self.assertTrue(any(item.label == "Decision profile" for item in app.selectbox))
        expected_sections = {
            "Why was this strategy selected?",
            "Modeled trade-offs and uncertainty",
            "Detailed allocation table",
            "Technical constraints and identifiers",
            "Explain in plain language (optional)",
        }
        self.assertTrue(expected_sections.issubset({item.label for item in app.expander}))
        self.assertTrue(any("Recommended Changes" in item.value for item in app.markdown))
        self.assertEqual(
            5, sum("br-action-card" in item.value for item in app.markdown)
        )
        objective_view = next(item for item in app.radio if item.label == "Objective chart view")
        self.assertEqual("Objective Scores", objective_view.value)
        app = objective_view.set_value("Score Changes").run()
        self.assertEqual([], list(app.exception))
        self.assertTrue(any("How to interpret this chart" in item.value for item in app.markdown))
        self.assertTrue(any("not a measured outcome change" in item.value for item in app.info))

        wording = next(item for item in app.radio if item.label == "Explanation wording")
        app = wording.set_value("AI-written wording").run()
        explain_button = next(
            item for item in app.button if item.label == "Explain in plain language"
        )
        app = explain_button.click().run(timeout=30)
        self.assertEqual([], list(app.exception))
        self.assertTrue(any("AI-written wording" in item.value for item in app.success))
        self.assertEqual(1, self.explanation_provider.calls)

        factor = next(item for item in app.selectbox if item.label == "Factor")
        app = factor.set_value("faculty_total").run()
        new_capacity = next(
            item
            for item in app.number_input
            if item.label == "Test faculty capacity (annual FTE)"
        )
        new_capacity.set_value(16.0)
        run_button = next(
            item for item in app.button if item.label == "Run controlled sensitivity"
        )
        app = run_button.click().run(timeout=30)
        self.assertEqual([], list(app.exception))
        self.assertTrue(any("Tested Faculty Total" in item.value for item in app.success))
        self.assertTrue(any(item.label == "Held fixed, no repair" for item in app.metric))
        self.assertTrue(any(item.label == "Reoptimized scenario" for item in app.metric))

    def test_experiment_lab_renders_saved_benchmark_without_live_run_mixing(self) -> None:
        from streamlit.testing.v1 import AppTest

        harness = Path(__file__).resolve().parent / "experiment_harness.py"
        app = AppTest.from_file(str(harness), default_timeout=30).run()
        self.assertEqual([], list(app.exception))
        self.assertTrue(any(item.label == "Completed jobs" and item.value == "150 / 150" for item in app.metric))
        self.assertEqual(
            {"Performance distributions", "Paired statistics", "How the methods search"},
            {item.label for item in app.tabs},
        )
        self.assertTrue(any("Synthetic method comparison only" in item.value for item in app.warning))
        metric = next(item for item in app.selectbox if item.label == "Paired comparison metric")
        self.assertIn(metric.value, {"hypervolume", "igd"})
        self.assertTrue(any("Wilcoxon p" in column for frame in app.dataframe for column in frame.value.columns))

    def test_evidence_view_renders_dea_kpi_robustness_and_audit_sections(self) -> None:
        from streamlit.testing.v1 import AppTest

        harness = Path(__file__).resolve().parent / "evidence_harness.py"
        app = AppTest.from_file(str(harness), default_timeout=30).run()
        self.assertEqual([], list(app.exception))
        self.assertEqual(
            {"Evidence map", "KPI models", "Robustness", "Reproduction audit"},
            {item.label for item in app.tabs},
        )
        self.assertTrue(any("0 complete comparable public DMUs" in item.value for item in app.error))
        self.assertTrue(any("30 optimal solves" in item.value for item in app.warning))
        self.assertTrue(any(item.label == "Audit checks" and item.value == "23" for item in app.metric))


if __name__ == "__main__":
    unittest.main()
