import gc
import unittest
from pathlib import Path

import numpy as np

from libRION.libPSO_parallel import (
    NativeBackendUnavailable,
    PSO,
    default_library_path,
    load_native_library,
)


NATIVE_AVAILABLE = default_library_path().is_file()
NATIVE_REASON = "run `make native` with an OpenMP-capable compiler"


class NativeLoadingTests(unittest.TestCase):
    def test_missing_library_has_actionable_error(self):
        missing = Path(__file__).with_name("definitely_missing_libpso.so")
        with self.assertRaisesRegex(NativeBackendUnavailable, "make native"):
            load_native_library(missing)


@unittest.skipUnless(NATIVE_AVAILABLE, NATIVE_REASON)
class NativePSOTests(unittest.TestCase):
    def make_pso(self, seed=17, objective=None):
        rng = np.random.default_rng(5)
        data = rng.uniform(-5, 5, size=(40, 2))
        return PSO(
            objective or (lambda x: float(np.dot(x, x))),
            data,
            max_iter=100,
            lower_bounds=[-5, -5],
            upper_bounds=[5, 5],
            seed=seed,
        )

    def test_known_sphere_optimum_and_bounds(self):
        with self.make_pso() as pso:
            position, score = pso.optimize()
            self.assertLess(score, 1e-6)
            self.assertTrue(np.allclose(position, [0, 0], atol=1e-3))
            self.assertTrue(np.all(pso.positions >= -5))
            self.assertTrue(np.all(pso.positions <= 5))

    def test_seeded_run_is_repeatable(self):
        with self.make_pso(seed=23) as first:
            first_position, first_score = first.optimize()
            first_particles = first.positions.copy()
        with self.make_pso(seed=23) as second:
            second_position, second_score = second.optimize()
            second_particles = second.positions.copy()
        np.testing.assert_array_equal(first_position, second_position)
        np.testing.assert_array_equal(first_particles, second_particles)
        self.assertEqual(first_score, second_score)

    def test_particle_index_reaches_objective(self):
        seen = set()

        def objective(position, particle_index):
            seen.add(particle_index)
            return float((position[0] - particle_index) ** 2)

        with PSO(
            objective,
            np.array([[0.0], [1.0], [2.0]]),
            max_iter=1,
            lower_bounds=[0.0],
            upper_bounds=[2.0],
            seed=3,
            objective_uses_particle_index=True,
        ) as pso:
            pso.optimize()
        self.assertEqual(seen, {0, 1, 2})

    def test_callback_exception_is_propagated(self):
        calls = 0

        def broken(position):
            nonlocal calls
            calls += 1
            if calls > 40:
                raise LookupError("expected callback failure")
            return float(np.dot(position, position))

        with self.make_pso(objective=broken) as pso:
            with self.assertRaisesRegex(RuntimeError, "callback failed") as raised:
                pso.optimize()
        self.assertIsInstance(raised.exception.__cause__, LookupError)

    def test_nonfinite_objective_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "callback failed"):
            self.make_pso(objective=lambda position: float("nan"))

    def test_dimensions_and_lifetime_errors(self):
        with self.assertRaisesRegex(ValueError, "num_particles"):
            PSO(lambda x: 0.0, np.ones((3, 2)), num_particles=2)
        pso = self.make_pso()
        pso.close()
        pso.close()
        with self.assertRaisesRegex(RuntimeError, "closed"):
            pso.optimize()
        del pso
        gc.collect()


if __name__ == "__main__":
    unittest.main()
