from __future__ import annotations

import unittest

from streamlit_app.data.adapters import adapt_overview
from streamlit_app.data.loaders import load_catalog, load_snapshot


class AdapterTests(unittest.TestCase):
    def test_saved_snapshot_parity(self) -> None:
        catalog = load_catalog()
        expected = {
            "synthetic-phase7-v1": (6, 30, 12, "6"),
            "vjti-public-synthetic-v1": (5, 60, 45, "5"),
            "vjti-empirical-v1": (0, 0, 0, "7"),
        }
        for snapshot_id, values in expected.items():
            with self.subTest(snapshot=snapshot_id):
                view = adapt_overview(load_snapshot(snapshot_id, catalog))
                self.assertEqual(values[0], len(view.strategies))
                self.assertEqual(values[1], len(view.allocations))
                self.assertEqual(values[2], len(view.kpis))
                self.assertEqual(values[3], view.base_metrics[0].value)

    def test_empirical_lane_has_no_optimizer_outputs(self) -> None:
        view = adapt_overview(load_snapshot("vjti-empirical-v1"))
        self.assertEqual([], view.strategies)
        self.assertTrue(view.allocations.empty)
        self.assertTrue(view.kpis.empty)
        self.assertTrue(view.resources.empty)
        self.assertTrue(view.constraints.empty)
        metric = next(metric for metric in view.base_metrics if metric.label == "Empirical optimizer runs")
        self.assertEqual("0", metric.value)


if __name__ == "__main__":
    unittest.main()
