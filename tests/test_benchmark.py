import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from department_optimizer.benchmark.metrics import hypervolume, igd, nondominated, spacing
from department_optimizer.benchmark.runner import _configured_budget, run_benchmark


REPO_ROOT = Path(__file__).resolve().parents[1]


class MetricFixtureTests(unittest.TestCase):
    def test_known_two_point_hypervolume(self):
        points = np.array([[0.2, 0.8], [0.8, 0.2]])
        self.assertAlmostEqual(hypervolume(points, [1.0, 1.0]), 0.28)
        self.assertAlmostEqual(
            hypervolume([[0.2, 0.2, 0.2, 0.2]], [1.0, 1.0, 1.0, 1.0]),
            0.8**4,
        )

    def test_dominated_and_duplicate_points_do_not_change_hypervolume(self):
        points = np.array([[0.2, 0.8], [0.8, 0.2], [0.9, 0.9], [0.2, 0.8]])
        self.assertEqual(len(nondominated(points)), 2)
        self.assertAlmostEqual(hypervolume(points, [1.0, 1.0]), 0.28)

    def test_igd_and_spacing_known_front(self):
        reference = np.array([[0.0, 1.0], [0.5, 0.5], [1.0, 0.0]])
        self.assertEqual(igd(reference, reference), 0.0)
        self.assertAlmostEqual(spacing(reference), 0.0)
        self.assertTrue(np.isnan(igd(np.empty((0, 2)), reference)))
        self.assertEqual(hypervolume(np.empty((0, 2)), [1.1, 1.1]), 0.0)


class BenchmarkProtocolTests(unittest.TestCase):
    def test_smoke_algorithms_have_identical_candidate_budgets(self):
        config = json.loads(
            (REPO_ROOT / "configs/benchmark/smoke_synthetic.json").read_text()
        )
        budgets = {
            name: _configured_budget(name, settings)
            for name, settings in config["algorithms"].items()
            if settings["enabled"]
        }
        self.assertEqual(set(budgets.values()), {config["evaluation_budget"]})

    def test_final_seed_set_has_target_size_and_is_separate_from_smoke(self):
        smoke = json.loads(
            (REPO_ROOT / "configs/benchmark/smoke_synthetic.json").read_text()
        )
        final = json.loads(
            (REPO_ROOT / "configs/benchmark/final_synthetic_25seeds.json").read_text()
        )
        self.assertEqual(len(final["seeds"]), 25)
        self.assertEqual(len(set(final["seeds"])), 25)
        self.assertTrue(set(smoke["seeds"]).isdisjoint(final["seeds"]))

    def test_interrupted_resume_and_complete_skip_do_not_duplicate_metric_row(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = {
                "schema_version": 1,
                "benchmark_id": "resume-fixture",
                "data_role": "smoke",
                "allocation_config": str(
                    REPO_ROOT / "configs/allocation/legacy_synthetic_method_fixture.json"
                ),
                "seeds": [777],
                "evaluation_budget": 4,
                "budget_definition": "test candidate budget",
                "minimum_runs_for_inference": 10,
                "reference_front_version": "resume-fixture-v1",
                "objective_scaling": {
                    "objective_order": ["research", "innovation", "student", "societal"],
                    "lower": [-1.0, -1.0, -1.0, -1.0],
                    "upper": [0.0, 0.0, 0.0, 0.0],
                    "clip": True,
                    "status": "fixture",
                },
                "hypervolume_reference_point": [1.1, 1.1, 1.1, 1.1],
                "algorithms": {"random_search": {"enabled": True, "evaluations": 4}},
                "output_root": str(root / "output"),
            }
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config))
            output = run_benchmark(config_path)
            first = json.loads((output / "completion.json").read_text())
            status_path = output / "runs/random_search/seed_777/status.json"
            first_status = json.loads(status_path.read_text())
            interrupted = {**first_status, "status": "running"}
            status_path.write_text(json.dumps(interrupted))
            run_benchmark(config_path)
            resumed_status = json.loads(status_path.read_text())
            run_benchmark(config_path)
            final = json.loads((output / "completion.json").read_text())
            final_status = json.loads(status_path.read_text())
            metrics = pd.read_csv(output / "per_seed_metrics.csv")
            self.assertEqual(first["complete_jobs"], 1)
            self.assertEqual(resumed_status["attempt"], first_status["attempt"] + 1)
            self.assertEqual(final["events_this_invocation"][0]["action"], "skipped_complete")
            self.assertEqual(final_status["attempt"], resumed_status["attempt"])
            self.assertEqual(len(metrics), 1)


if __name__ == "__main__":
    unittest.main()
