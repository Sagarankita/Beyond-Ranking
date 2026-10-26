import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from department_optimizer.evidence_modeling.workflow import run_evidence_modeling


REPO_ROOT = Path(__file__).resolve().parents[1]


class EvidenceModelingTests(unittest.TestCase):
    def _config(self, temp):
        config = json.loads(
            (REPO_ROOT / "configs/evidence_modeling/vjti_evidence_models_v1.json").read_text()
        )
        config["prompt14_root"] = str(REPO_ROOT / "artifacts/public_data/vjti_ceit_v1")
        config["output_root"] = str(Path(temp) / "evidence")
        config["dea"]["synthetic_dmus"] = 15
        config["models"]["random_forest_trees"] = 20
        path = Path(temp) / "config.json"
        path.write_text(json.dumps(config))
        return path

    def test_tracks_are_labeled_and_leakage_checks_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            result = run_evidence_modeling(self._config(temp))
            self.assertTrue(result["checks_passed"])
            root = Path(result["output_root"])
            public = json.loads((root / "public_evidence_assessment.json").read_text())
            self.assertEqual(public["public_dea_status"], "unsupported")
            self.assertFalse(public["public_test_set_retained"])
            leakage = json.loads((root / "leakage_checks.json").read_text())
            self.assertTrue(leakage["passed"])
            manifest = json.loads((root / "model_manifest.json").read_text())
            self.assertTrue(manifest["raw_source_hashes"])
            self.assertTrue(all(model["model_sha256"] for model in manifest["selected_models"].values()))
            registry = pd.read_csv(root / "kpi_evidence_registry.csv")
            self.assertTrue(set(registry.status).issubset(
                {"public_validated", "public_descriptive", "synthetic_scenario", "unsupported"}
            ))
            self.assertNotIn("public_validated", set(registry.status))

    def test_dea_outputs_solver_peers_slacks_and_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            result = run_evidence_modeling(self._config(temp))
            root = Path(result["output_root"])
            efficiency = pd.read_csv(root / "dea_efficiency.csv")
            self.assertTrue((efficiency.solver_status == "optimal").all())
            self.assertTrue(any(name.startswith("input_slack__") for name in efficiency.columns))
            self.assertTrue(any(name.startswith("target_output__") for name in efficiency.columns))
            provenance = pd.read_csv(root / "dea_variable_provenance.csv")
            self.assertTrue((provenance.synthetic_calibrated_fraction == 1.0).all())
            summary = json.loads((root / "dea_summary.json").read_text())
            self.assertEqual(summary["evidence_label"], "synthetic_scenario")


if __name__ == "__main__":
    unittest.main()
