import unittest

from department_optimizer.audit.completion import (
    Audit,
    independent_hypervolume,
    independent_igd,
)


class IndependentMetricAuditTests(unittest.TestCase):
    def test_inclusion_exclusion_hypervolume_fixture(self):
        points = [[0.2, 0.8], [0.8, 0.2]]
        self.assertAlmostEqual(independent_hypervolume(points, [1.0, 1.0]), 0.28)
        self.assertAlmostEqual(
            independent_hypervolume([[0.2, 0.2, 0.2, 0.2]], [1.0] * 4),
            0.8**4,
        )

    def test_independent_igd_fixture(self):
        front = [[0.0, 1.0], [0.5, 0.5], [1.0, 0.0]]
        self.assertEqual(independent_igd(front, front), 0.0)

    def test_audit_preserves_gaps_separately_from_failures(self):
        audit = Audit()
        audit.add("configured_not_run", "completion", "gap", "fixture")
        audit.check(True, "verified", "test", "fixture", "failure")
        self.assertEqual(list(audit.frame().status), ["gap", "pass"])


if __name__ == "__main__":
    unittest.main()
