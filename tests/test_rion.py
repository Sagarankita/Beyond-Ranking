import unittest

import numpy as np
import pandas as pd

from libRION.libPSO import PSO
from libRION.libRION import RionOptimiser


class RionTests(unittest.TestCase):
    def make_optimizer(self, **kwargs):
        optimizer = RionOptimiser(pop_size=kwargs.pop("pop_size", 4), seed=7, **kwargs)
        optimizer.data = pd.DataFrame({"x": [0.0], "y": [0.0]})
        optimizer.optimiser_funcs = [lambda row: row["x"], lambda row: row["y"]]
        optimizer.constraints = [(0.0, 10.0), (0.0, 10.0)]
        optimizer.integer_columns = set()
        return optimizer

    def test_known_fronts_and_ties(self):
        optimizer = self.make_optimizer()
        population = pd.DataFrame(
            {"x": [1.0, 2.0, 1.0, 3.0], "y": [2.0, 1.0, 2.0, 3.0]}
        )
        fronts, ranks = optimizer._fast_non_dominated_sort(population)
        self.assertEqual(fronts, [[0, 1, 2], [3]])
        self.assertEqual(ranks, [0, 0, 0, 1])
        self.assertFalse(optimizer._dominates(population.iloc[0], population.iloc[2]))

    def test_no_worse_in_all_dominance(self):
        optimizer = self.make_optimizer()
        self.assertTrue(
            optimizer._dominates(
                pd.Series({"x": 1.0, "y": 2.0}),
                pd.Series({"x": 1.0, "y": 3.0}),
            )
        )

    def test_feasible_beats_infeasible_and_violations_are_ordered(self):
        optimizer = self.make_optimizer()
        feasible = pd.Series({"x": 9.0, "y": 9.0})
        slightly_infeasible = pd.Series({"x": 10.5, "y": 9.0})
        very_infeasible = pd.Series({"x": 12.0, "y": 9.0})
        self.assertTrue(optimizer._dominates(feasible, slightly_infeasible))
        self.assertTrue(optimizer._dominates(slightly_infeasible, very_infeasible))

    def test_exact_and_odd_population_sizes(self):
        data = pd.DataFrame({"x": [1, 2, 3], "y": [3, 2, 1]})
        optimizer = RionOptimiser(
            generations=2, pop_size=5, pso_iterations=0, seed=11
        )
        result = optimizer.optimise(
            data,
            [lambda row: row["x"], lambda row: row["y"]],
            [[0, 10], [0, 10]],
            integer_columns=["x", "y"],
        )
        self.assertEqual(len(result), 5)
        self.assertTrue(all(pd.api.types.is_integer_dtype(result[c]) for c in result))

    def test_survivor_rank_alignment(self):
        optimizer = self.make_optimizer(pop_size=2)
        combined = pd.DataFrame({"x": [4.0, 1.0, 2.0, 3.0], "y": [4.0, 1.0, 2.0, 3.0]})
        survivors = optimizer._select_survivors(combined)
        self.assertEqual(list(survivors["x"]), [1.0, 2.0])

    def test_row_aware_pso_objective(self):
        calls = []

        def objective(position, particle_index):
            calls.append(particle_index)
            return (position[0] - particle_index) ** 2

        pso = PSO(
            objective,
            np.array([[0.0], [1.0], [2.0]]),
            max_iter=1,
            lower_bounds=[0.0],
            upper_bounds=[2.0],
            seed=3,
            objective_uses_particle_index=True,
        )
        pso.optimize()
        self.assertEqual(set(calls), {0, 1, 2})

    def test_reproducibility_and_integer_repair(self):
        data = pd.DataFrame({"x": [0, 2, 4, 6], "y": [6.0, 4.0, 2.0, 0.0]})

        def run():
            optimizer = RionOptimiser(
                generations=2, pop_size=5, pso_iterations=2, seed=19
            )
            return optimizer.optimise(
                data,
                [lambda row: row["x"], lambda row: row["y"]],
                [[0, 6], [0, 6]],
                integer_columns=["x"],
            )

        first, second = run(), run()
        pd.testing.assert_frame_equal(first, second)
        self.assertTrue(pd.api.types.is_integer_dtype(first["x"]))
        self.assertTrue(((first >= 0) & (first <= 6)).all().all())

    def test_rejects_unsupported_small_population(self):
        with self.assertRaisesRegex(ValueError, "at least 2"):
            RionOptimiser(pop_size=1)


class PSOTests(unittest.TestCase):
    def test_sphere_converges_near_known_optimum(self):
        rng = np.random.default_rng(5)
        data = rng.uniform(-5, 5, size=(40, 2))
        pso = PSO(
            lambda x: float(np.dot(x, x)),
            data,
            max_iter=100,
            lower_bounds=[-5, -5],
            upper_bounds=[5, 5],
            seed=23,
        )
        position, score = pso.optimize()
        self.assertLess(score, 1e-6)
        self.assertTrue(np.allclose(position, [0, 0], atol=1e-3))


if __name__ == "__main__":
    unittest.main()
