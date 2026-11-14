from __future__ import annotations

import json
import tempfile
import unittest
import warnings
from pathlib import Path

warnings.filterwarnings(
    "ignore",
    message="Using `httpx` with `starlette.testclient` is deprecated.*",
)

from fastapi.testclient import TestClient

from streamlit_app.api.app import create_app
from streamlit_app.api.service import DashboardRunService


VALID_RUN = {
    "track_id": "vjti_public_plus_synthetic",
    "overrides": {
        "budget_limit": 36_000_000,
        "budget_unit": "INR",
        "faculty_total": 15,
        "faculty_unit": "annual FTE",
        "cost_multipliers": {},
    },
    "algorithm": "mopso",
    "seed": 18001,
    "evaluation_budget": 16,
}


class DashboardApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.run_root = Path(self.temporary.name)
        self.service = DashboardRunService(self.run_root, synchronous=True)
        self.client = TestClient(create_app(self.service))

    def tearDown(self):
        self.client.close()
        self.service.close()
        self.temporary.cleanup()

    def _complete_run(self):
        response = self.client.post("/runs", json=VALID_RUN)
        self.assertEqual(response.status_code, 202, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "complete")
        return payload

    def test_defaults_and_evidence_are_backend_derived(self):
        defaults = self.client.get("/config/defaults").json()
        self.assertEqual(defaults["defaults"]["budget_limit"], 36_000_000)
        self.assertEqual(defaults["defaults"]["faculty_total"], 15)
        self.assertEqual(len(defaults["decision_variables"]), 12)
        self.assertEqual(defaults["interactive_evaluation_budget"], 16)

        evidence = self.client.get("/evidence/summary").json()
        self.assertEqual(evidence["public_dea"]["complete_dmus"], 0)
        self.assertEqual(evidence["public_dea"]["required_dmus"], 12)
        self.assertEqual(evidence["synthetic_dea"]["successful_solves"], 30)
        self.assertEqual(len(evidence["sources"]), 7)
        self.assertEqual(evidence["model_target_count"], 9)
        self.assertEqual(len(evidence["interval_calibration"]), 9)
        self.assertEqual(len(evidence["robustness"]["fixed_vs_reoptimized"]), 20)
        self.assertEqual(len(evidence["audit_checks"]), 23)

    def test_valid_scenario_and_changed_input_change_hash(self):
        base = self.client.post("/scenarios/validate", json={"overrides": {}}).json()
        changed = self.client.post(
            "/scenarios/validate", json={"overrides": {"budget_limit": 30_000_000}}
        ).json()
        repeated = self.client.post("/scenarios/validate", json={"overrides": {}}).json()
        self.assertTrue(base["valid"])
        self.assertTrue(changed["valid"])
        self.assertEqual(base["scenario_hash"], repeated["scenario_hash"])
        self.assertNotEqual(base["scenario_hash"], changed["scenario_hash"])

    def test_invalid_units_budget_and_faculty_return_field_errors(self):
        unit = self.client.post(
            "/scenarios/validate", json={"overrides": {"budget_unit": "USD"}}
        )
        self.assertEqual(unit.status_code, 422)

        budget = self.client.post(
            "/scenarios/validate", json={"overrides": {"budget_limit": 1_000_000}}
        ).json()
        self.assertFalse(budget["valid"])
        self.assertIn("budget_limit", budget["field_errors"])

        faculty = self.client.post(
            "/scenarios/validate", json={"overrides": {"faculty_total": 10}}
        ).json()
        self.assertFalse(faculty["valid"])
        self.assertIn("faculty_total", faculty["field_errors"])

    def test_unsupported_field_and_evaluation_budget_are_rejected(self):
        unsupported = self.client.post(
            "/runs", json={**VALID_RUN, "overrides": {"arbitrary_parameter": 3}}
        )
        self.assertEqual(unsupported.status_code, 422)

        wrong_budget = self.client.post(
            "/runs", json={**VALID_RUN, "evaluation_budget": 20}
        )
        self.assertEqual(wrong_budget.status_code, 422)
        self.assertEqual(wrong_budget.json()["detail"]["code"], "unsupported_evaluation_budget")

    def test_run_persists_accounting_manifest_and_revalidated_candidates(self):
        run = self._complete_run()
        run_path = self.run_root / run["run_id"]
        accounting = json.loads((run_path / "evaluation_accounting.json").read_text())
        manifest = json.loads((run_path / "manifest.json").read_text())
        candidates = self.client.get(f"/runs/{run['run_id']}/candidates")

        self.assertEqual(accounting["candidate_evaluations_total"], 16)
        self.assertEqual(manifest["run_id"], run["run_id"])
        self.assertEqual(manifest["scenario_hash"], run["scenario_hash"])
        self.assertEqual(candidates.status_code, 200)
        records = candidates.json()["candidates"]
        self.assertGreater(len(records), 0)
        self.assertTrue(all(item["revalidated"] and item["feasible"] for item in records))
        self.assertTrue(all(item["run_id"] == run["run_id"] for item in records))
        self.assertTrue(all(item["scenario_hash"] == run["scenario_hash"] for item in records))

    def test_changed_budget_reaches_evaluator_and_bounds_results(self):
        request = {
            **VALID_RUN,
            "algorithm": "nsga2",
            "seed": 18200,
            "overrides": {**VALID_RUN["overrides"], "budget_limit": 30_000_000},
        }
        run = self.client.post("/runs", json=request).json()
        self.assertEqual(run["status"], "complete", run)
        config = json.loads(
            (self.run_root / run["run_id"] / "scenario_config.json").read_text()
        )
        candidates = self.client.get(f"/runs/{run['run_id']}/candidates").json()["candidates"]
        self.assertEqual(config["budget_limit"], 30_000_000)
        self.assertGreater(len(candidates), 0)
        self.assertTrue(all(item["total_cost"] <= 30_000_000 for item in candidates))
        self.assertTrue(
            all(item["constraints"]["budget"]["satisfied"] for item in candidates)
        )

    def test_duplicate_submission_and_seed_are_deterministic(self):
        first = self._complete_run()
        duplicate = self.client.post("/runs", json=VALID_RUN).json()
        self.assertEqual(first["run_id"], duplicate["run_id"])
        self.assertTrue(duplicate["duplicate_submission"])

        with tempfile.TemporaryDirectory() as other_root:
            other_service = DashboardRunService(Path(other_root), synchronous=True)
            other_client = TestClient(create_app(other_service))
            try:
                other = other_client.post("/runs", json=VALID_RUN).json()
                first_candidates = self.client.get(
                    f"/runs/{first['run_id']}/candidates"
                ).json()["candidates"]
                other_candidates = other_client.get(
                    f"/runs/{other['run_id']}/candidates"
                ).json()["candidates"]
                self.assertEqual(first["run_id"], other["run_id"])
                self.assertEqual(first_candidates, other_candidates)
            finally:
                other_client.close()
                other_service.close()

    def test_candidate_comparison_stays_within_run_and_units(self):
        run = self._complete_run()
        records = self.client.get(f"/runs/{run['run_id']}/candidates").json()["candidates"]
        first = records[0]["candidate_id"]
        second = records[-1]["candidate_id"]
        comparison = self.client.post(
            "/comparisons",
            json={
                "run_id": run["run_id"],
                "first_candidate_id": first,
                "second_candidate_id": second,
            },
        )
        self.assertEqual(comparison.status_code, 200, comparison.text)
        body = comparison.json()
        self.assertEqual(body["scenario_hash"], run["scenario_hash"])
        self.assertEqual(len(body["decision_deltas"]), 12)
        self.assertTrue(all(item["unit"] for item in body["decision_deltas"]))

        missing = self.client.post(
            "/comparisons",
            json={
                "run_id": run["run_id"],
                "first_candidate_id": "0" * 24,
                "second_candidate_id": second,
            },
        )
        self.assertEqual(missing.status_code, 404)

    def test_restart_marks_unfinished_run_interrupted_and_retry_completes(self):
        run = self._complete_run()
        status_path = self.run_root / run["run_id"] / "status.json"
        status = json.loads(status_path.read_text())
        status.update(status="running", phase="optimization")
        status_path.write_text(json.dumps(status), encoding="utf-8")

        recovered = DashboardRunService(self.run_root, synchronous=True)
        recovered_client = TestClient(create_app(recovered))
        try:
            interrupted = recovered_client.get(f"/runs/{run['run_id']}").json()
            self.assertEqual(interrupted["status"], "interrupted")
            self.assertEqual(interrupted["error"]["code"], "service_restart")
            retried = recovered_client.post(f"/runs/{run['run_id']}/retry")
            self.assertEqual(retried.status_code, 202, retried.text)
            self.assertEqual(retried.json()["status"], "complete")
            self.assertEqual(retried.json()["attempt"], 2)
        finally:
            recovered_client.close()
            recovered.close()

    def test_completed_benchmark_is_separate_from_interactive_run(self):
        benchmark = self.client.get("/benchmarks/final").json()
        self.assertEqual(benchmark["complete_jobs"], 150)
        self.assertEqual(len(benchmark["algorithms"]), 6)
        self.assertEqual(len(benchmark["seeds"]), 25)
        self.assertEqual(benchmark["evaluation_budget"], 100)
        self.assertFalse(benchmark["native_rion_openmp_built"])
        self.assertEqual(len(benchmark["per_seed_metrics"]), 150)
        self.assertEqual(len(benchmark["statistical_tests"]), 60)
        self.assertEqual(len(benchmark["summary"]), 48)
        self.assertEqual(benchmark["metric_definitions"]["hypervolume"]["direction"], "higher")

    def test_every_approved_algorithm_uses_the_declared_interactive_budget(self):
        for offset, algorithm in enumerate(
            ("nsga2", "nsga3", "moead", "mopso", "rion", "random_search")
        ):
            request = {**VALID_RUN, "algorithm": algorithm, "seed": 18100 + offset}
            response = self.client.post("/runs", json=request)
            self.assertEqual(response.status_code, 202, response.text)
            run = response.json()
            self.assertEqual(run["status"], "complete", run)
            accounting = json.loads(
                (self.run_root / run["run_id"] / "evaluation_accounting.json").read_text()
            )
            self.assertEqual(accounting["candidate_evaluations_total"], 16)


if __name__ == "__main__":
    unittest.main()
