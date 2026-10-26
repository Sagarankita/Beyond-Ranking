import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from department_optimizer.public_data.workflow import build_public_data_package


REPO_ROOT = Path(__file__).resolve().parents[1]


class PublicDataWorkflowTests(unittest.TestCase):
    def test_package_is_reproducible_and_preserves_public_values(self):
        config = json.loads((REPO_ROOT / "configs/data/vjti_public_plus_synthetic_v1.json").read_text())
        with tempfile.TemporaryDirectory() as temp:
            config["output_root"] = str(Path(temp) / "out")
            for source in config["sources"]:
                source["snapshot_path"] = str(REPO_ROOT / source["snapshot_path"])
            path = Path(temp) / "config.json"
            path.write_text(json.dumps(config))
            result = build_public_data_package(path)
            self.assertTrue(result["checks_passed"])
            root = Path(result["output_root"])
            public = pd.read_csv(root / "public_only.csv")
            combined = pd.read_csv(root / "public_plus_synthetic.csv")
            key = (public.unit_id == "VJTI-CEIT") & (public.period == "2023-24") & (public.field == "placements")
            mixed_key = (combined.unit_id == "VJTI-CEIT") & (combined.period == "2023-24") & (combined.field == "placements")
            self.assertEqual(public.loc[key, "value"].iloc[0], 150)
            self.assertEqual(len(combined.loc[mixed_key]), 1)
            self.assertEqual(combined.loc[mixed_key, "provenance"].iloc[0], "derived_public")
            checks = pd.read_csv(root / "realism_accounting_checks.csv")
            self.assertTrue(checks["passed"].all())
            first = (root / "synthetic_only.csv").read_bytes()
            build_public_data_package(path)
            self.assertEqual(first, (root / "synthetic_only.csv").read_bytes())

    def test_institution_totals_are_not_department_values(self):
        config = json.loads((REPO_ROOT / "configs/data/vjti_public_plus_synthetic_v1.json").read_text())
        for value in config["public_values"]:
            if value["unit_id"] == "VJTI-CEIT":
                self.assertEqual(value["unit_level"], "department")
                self.assertNotIn(value["field"], {"patents_published", "sponsored_research_amount", "consultancy_amount"})


if __name__ == "__main__":
    unittest.main()
