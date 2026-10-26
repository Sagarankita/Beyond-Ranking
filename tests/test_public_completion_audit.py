import json
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from department_optimizer.audit.public_completion import independent_hypervolume
from department_optimizer.benchmark.metrics import hypervolume


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "artifacts/public_audit/vjti_v1"


class PublicCompletionAuditTests(unittest.TestCase):
    def test_independent_hypervolume_matches_frozen_metric(self):
        points = np.array([[-0.8, -0.3, -0.4, -0.2], [-0.4, -0.7, -0.5, -0.3]])
        reference = np.full(4, 0.05)
        self.assertAlmostEqual(independent_hypervolume(points, reference), hypervolume(points, reference), places=12)

    def test_saved_audit_preserves_claim_boundaries(self):
        manifest = json.loads((AUDIT / "manifest.json").read_text())
        self.assertEqual(manifest["audit_id"], "vjti-public-plus-synthetic-completion-audit-v1")
        self.assertFalse(manifest["empirical_validation_claim"])
        self.assertFalse(manifest["causal_claim"])

    def test_matrix_and_independent_recomputations_are_complete(self):
        matrix = pd.read_csv(AUDIT / "implementation_evidence_matrix.csv")
        self.assertTrue({"publicly_validated", "public_descriptive", "synthetic_scenario",
                         "optional", "deferred", "unsupported"}.issubset(set(matrix.evidence_status)))
        prediction = pd.read_csv(AUDIT / "independent_prediction_check.csv")
        constraints = pd.read_csv(AUDIT / "independent_constraint_check.csv")
        metrics = pd.read_csv(AUDIT / "independent_reproduction_metrics.csv")
        self.assertTrue(np.allclose(prediction.absolute_difference, 0, atol=1e-12))
        self.assertTrue(np.allclose(constraints.absolute_difference, 0, atol=1e-10))
        self.assertTrue(np.allclose(metrics.independent_hypervolume, metrics.recorded_hypervolume, atol=1e-12))
        self.assertTrue(np.allclose(metrics.independent_igd, metrics.recorded_igd, atol=1e-12, equal_nan=True))


if __name__ == "__main__":
    unittest.main()
