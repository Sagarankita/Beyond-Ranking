import unittest
from dataclasses import replace

import numpy as np

from department_optimizer.allocation import (
    MOEADAdapter,
    MOPSOAdapter,
    NSGA3Adapter,
    RandomSearchAdapter,
)
from department_optimizer.allocation.advanced_optimizers import (
    associate_to_reference_directions,
    das_dennis_reference_directions,
    nsga3_survival,
    update_external_archive,
)
from tests.test_allocation_optimizers import problem


def evaluation(objectives, violation=0.0):
    shared = problem()
    base = shared.evaluate(shared.config["reference_allocation"]["values"])
    return replace(
        base,
        objective_scores=dict(zip(("research", "innovation", "student", "societal"), objectives)),
        normalized_violation=violation,
        nominal_feasible=violation <= 1e-12,
    )


class ReferenceDirectionTests(unittest.TestCase):
    def test_das_dennis_shape_simplex_and_extremes(self):
        directions = das_dennis_reference_directions(4, 3)
        self.assertEqual(directions.shape, (20, 4))
        np.testing.assert_allclose(directions.sum(axis=1), 1.0)
        self.assertEqual(len(np.unique(directions, axis=0)), 20)
        for axis in np.eye(4):
            self.assertTrue(np.any(np.all(np.isclose(directions, axis), axis=1)))

    def test_association_and_niching_use_distinct_underrepresented_directions(self):
        directions = np.eye(4)
        values = np.eye(4)
        niche, distance, _ = associate_to_reference_directions(values, directions)
        np.testing.assert_array_equal(niche, np.arange(4))
        np.testing.assert_allclose(distance, 0.0)
        evaluations = [evaluation(row) for row in values]
        selected = nsga3_survival(
            evaluations, 2, directions, np.random.default_rng(3)
        )
        self.assertEqual(len(selected), 2)
        self.assertEqual(len(set(niche[selected])), 2)


class ArchiveTests(unittest.TestCase):
    def test_archive_repairs_duplicates_dominance_and_capacity(self):
        vectors = np.array(
            [
                [0.0, 0.0],
                [0.0, 0.0],
                [1.0, 0.0],
                [0.0, 1.0],
                [1.0, 1.0],
            ]
        )
        evaluations = [
            evaluation((0.0, 1.0, 0.0, 0.0)),
            evaluation((0.0, 1.0, 0.0, 0.0)),
            evaluation((1.0, 0.0, 0.0, 0.0)),
            evaluation((0.5, 0.5, 0.0, 0.0)),
            evaluation((1.0, 1.0, 0.0, 0.0)),
        ]
        archive_vectors, archive_evaluations = update_external_archive(
            vectors, evaluations, archive_size=2
        )
        self.assertEqual(len(archive_vectors), 2)
        self.assertEqual(len({tuple(row) for row in archive_vectors}), 2)
        for i in range(len(archive_evaluations)):
            for j in range(len(archive_evaluations)):
                if i != j:
                    a = archive_evaluations[i].objective_vector()
                    b = archive_evaluations[j].objective_vector()
                    self.assertFalse(np.all(a <= b) and np.any(a < b))


class AdvancedAdapterTests(unittest.TestCase):
    def assert_result(self, result, expected_population, algorithm):
        self.assertEqual(len(result.population), expected_population)
        self.assertGreater(len(result.archive), 0)
        self.assertEqual(set(result.population["algorithm"]), {algorithm})
        self.assertTrue(result.population["feasible"].all())
        self.assertTrue((result.population["normalized_violation"] <= 1e-12).all())
        self.assertTrue(
            {
                "objective__research",
                "objective__innovation",
                "objective__student",
                "objective__societal",
                "constraint__budget",
                "kpi__papers_t1",
            }.issubset(result.population.columns)
        )

    def test_nsga3_contract_and_direction_accounting(self):
        result = NSGA3Adapter(reference_partitions=1, generations=1, seed=4).run(problem())
        self.assert_result(result, 4, "nsga3")
        self.assertEqual(result.accounting["reference_direction_count"], 4)

    def test_moead_contract_neighborhoods_and_decomposition(self):
        result = MOEADAdapter(
            reference_partitions=1,
            neighborhood_size=2,
            max_replacements=1,
            generations=1,
            seed=4,
        ).run(problem())
        self.assert_result(result, 4, "moead")
        self.assertEqual(result.accounting["decomposition"], "weighted_tchebycheff")
        self.assertTrue(all(len(row) == 2 for row in result.accounting["neighborhoods"]))
        for index, row in enumerate(result.accounting["neighborhoods"]):
            self.assertIn(index, row)

    def test_mopso_has_bounded_external_archive_and_particle_updates(self):
        shared = problem()
        result = MOPSOAdapter(
            population_size=6, generations=2, archive_size=3, seed=4
        ).run(shared)
        self.assert_result(result, 6, "mopso")
        self.assertLessEqual(len(result.archive), 3)
        self.assertEqual(
            len(result.archive[shared.variable_names].drop_duplicates()),
            len(result.archive),
        )
        for _, row in result.archive.iterrows():
            repaired = shared.repair({name: row[name] for name in shared.variable_names})[1]
            self.assertTrue(
                all(np.isclose(row[name], repaired[name]) for name in shared.variable_names)
            )
        self.assertEqual(result.accounting["particle_update_evaluations"], 12)
        self.assertIn("crowding", result.accounting["leader_selection"])

    def test_all_adapters_export_identical_columns(self):
        shared = problem()
        results = [
            NSGA3Adapter(reference_partitions=1, generations=0, seed=8).run(shared),
            MOEADAdapter(
                reference_partitions=1,
                neighborhood_size=2,
                generations=0,
                seed=8,
            ).run(shared),
            MOPSOAdapter(population_size=4, generations=0, archive_size=4, seed=8).run(shared),
            RandomSearchAdapter(evaluations=4, seed=8).run(shared),
        ]
        expected = list(results[0].population.columns)
        for result in results[1:]:
            self.assertEqual(list(result.population.columns), expected)

    def test_random_search_uses_same_result_schema(self):
        result = RandomSearchAdapter(evaluations=10, seed=4).run(problem())
        self.assert_result(result, 10, "random_search")
        self.assertEqual(result.accounting["configured_evaluations"], 10)
        self.assertEqual(result.accounting["candidate_evaluations_total"], 10)


if __name__ == "__main__":
    unittest.main()
