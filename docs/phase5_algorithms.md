# Phase 5 multi-objective adapters

## Dependency and API decision

The implementation reviewed the current official pymoo documentation before choosing an
integration approach. The official NSGA-III interface requires supplied reference
directions and uses non-dominated sorting followed by underrepresented-niche selection.
The official MOEA/D interface exposes reference directions, neighborhood size, and
neighborhood mating probability. The official MOPSO-CD implementation uses crowding-based
leader selection and pruning of a bounded external nondominated archive. Pymoo also has a
separate mixed-variable customization layer.

Relevant official documentation:

- [NSGA-III](https://pymoo.org/algorithms/moo/nsga3.html)
- [MOEA/D](https://pymoo.org/algorithms/moo/moead.html)
- [MOPSO-CD](https://pymoo.org/algorithms/moo/mopso_cd.html)
- [Mixed-variable customization](https://pymoo.org/customization/mixed.html)

The project keeps repository-native adapters. Prompt 6 already defines mixed-variable
repair, feasibility-first constraint handling, prediction caching, and the common result
schema. Native adapters call that contract directly and avoid maintaining a second
translation of scientific constraints. No additional optimization dependency was added.

## NSGA-III

`NSGA3Adapter` uses deterministic Das-Dennis simplex-lattice directions. Four objectives
and three partitions produce 20 directions, which also sets the population size. Parent
selection and variation use tournament selection, SBX, and polynomial mutation. Survival
first fills complete nondominated fronts. The splitting front is normalized by its
population ideal/nadir range, associated by perpendicular distance, and selected from
the least occupied directions. Empty niches take their closest member; occupied niches
use a seeded random member.

The run artifact records the partition count, direction count, and full direction matrix.

## MOEA/D

`MOEADAdapter` uses the same 20 four-objective directions as decomposition weights. The
pilot config declares five nearest weight-vector neighbors and at most two population
replacements per offspring. Parents come from the owning subproblem's neighborhood.
Weighted Tchebycheff scalarization uses the evolving ideal point, while feasibility-first
dominance takes precedence over decomposition value. Every child passes through shared
mixed-variable repair before evaluation.

The artifact records the decomposition name, directions, complete neighborhood matrix,
and replacement limit.

## Genuine MOPSO

`MOPSOAdapter` is separate from RION's scalar PSO mutation. It maintains particles,
velocities, personal bests, and a bounded external nondominated archive. Each generation:

1. selects leaders through a binary tournament favoring greater crowding distance;
2. applies inertia, cognitive, and social velocity terms with a configured velocity cap;
3. repairs mixed variables using `AllocationProblem` before evaluation;
4. updates personal bests by feasibility-first dominance;
5. merges repaired particles into the archive, removes duplicate decision vectors,
   removes dominated entries, and prunes excess entries by crowding distance.

The pilot uses archive capacity 20, inertia 0.6, cognitive/social coefficients 1.5, and a
maximum velocity of 20% of each decision range. Archive tests verify capacity, uniqueness,
nondominance, and consistency with shared repair.

## Random-search baseline and pilot budget

`RandomSearchAdapter` evaluates repaired uniform samples and exports the identical
population/archive schema. It is a sanity baseline, not one of the proposal algorithms.

`configs/optimization/phase5_pilot_synthetic.json` labels this run
`pilot_calibration_only` and excludes it from the later final benchmark. The soft tuning
target is 100 unique shared-evaluator calls per algorithm. NSGA-II, NSGA-III, MOEA/D, and
MOPSO request 20 initial plus 80 evolutionary evaluations. Random search requests 100.
RION separately records unique calls, cached requests, and inner-PSO calls. No pilot
outcome was used to retune parameters.

Run all adapters with:

```sh
make allocation-phase5
```

## Current pilot result

All algorithms used seed 42 and the same synthetic allocation problem. Every final
candidate was feasible, every archive contained one recommendation, and every archived
row passed the fresh Prompt 7 feasibility check.

| Algorithm | Unique evaluator calls | Inner PSO | Cost (INR M) | Research FTE | Predicted papers | Citation percentile |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NSGA-II | 87 | 0 | 20.0 | 77.2 | 41.43 | 0.6318 |
| NSGA-III | 79 | 0 | 20.0 | 78.0 | 41.46 | 0.6320 |
| MOEA/D | 83 | 0 | 20.0 | 76.4 | 41.39 | 0.6318 |
| MOPSO | 87 | 0 | 20.0 | 80.0 | 41.58 | 0.6317 |
| RION | 96 | 50 | 20.0 | 67.6 | 41.06 | 0.6312 |
| Random search | 100 | 0 | 19.7 | 70.8 | 40.46 | 0.6320 |

These values are integration evidence, not a ranking of algorithms. Cache hits make
unique counts differ from requested counts, RION has different internal request
semantics, and Prompt 9 must enforce matched evaluation budgets across repeated seeds.
The current response model supports only research; three constant unsupported objectives
collapse the real search to one effective objective. Reference-direction diversity and
trade-off behavior are therefore established by mathematical fixtures, not by this
departmental synthetic run.
