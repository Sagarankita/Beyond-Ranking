# Department-Rank-Improver
Optimisation Techniques to improve the ranking of department in terms of research papers, publications and other miscellaneous stuff

## Optimisation Techniques and Parallel Computing
This project aims to suggest a hybrid algorithm to perform Multi Objective Optimisation to increase the department rankings based on the research papers published and shown at major tier-1 conferences. We define the following three fitness functions:
1. $\max O_1(x) = \text{Tier 1 Papers} /
\text{research}_{FTE}$

2. $\max O_2(x) = \cfrac{1}{\text{research}_{FTE}}\cdot\sum_i w_i \cdot \text{cite}\%$

3. $\min O_3(x) = \cfrac{\text{research budget}}{O_2(x) + \epsilon}$

The optimiser must explore feasible solutions that satisfy constraints such as:
* Minimum faculty strength
* Valid research time fractions
* Reasonable student-faculty ratios
* Non-negative budgets

The result is a set of optimised departmental configurations that maximise research impact while minimizing cost.

### Approach
The RION (Research Innovation Societal Optimisation Network) is a hybrid multi-objective optimisation framework that integrates NSGA-II with a PSO-based mutation mechanism. This approach enhances the global search (via NSGA-II) while respecting constraints defined on each variable.

1. Initialisation: Generate a population by sampling randomly from the dataset.
2. NSGA-II Evolution Loop: Each generation performs:

    1. Parent Selection and Crossover: Tournament selection is used and crossover is a simple random chance to swap the values of a single objective of the parents.
    2. Population merging: Parents and offspring are now combined into a single population.
    3. Fast-non dominated sorting: Sort the new population into pareto fronts
    4. Crowding distance calculations and next generation selection: Fronts are added in order until population limit is reached. If the final front overflows, its individuals are sorted by crowding distance to select the most diverse solutions.
3. PSO-Driven mutation: Instead of classical random mutation, RION introduces targeted PSO optimisation:
    * One attribute (column) is randomly chosen.
    * All offspring values in that column act as particles in a PSO swarm.
    * PSO updates particle positions for a fixed number of iterations.

    PSO Objective function:
    
    $$\mathrm{PSO\_fitness}(x) = \sum_{i=1}^3 O_i(x) + p \cdot \mathrm{cv}(x)$$
    
    where $p$ is the penalty for violating constraints (scaling factor) and $\mathrm{cv}(x)$ is the constraint violation function, the fraction of the budget violated.

    $$\mathrm{cv}(x) = \sum_{a \in \text{columns}(x)}\min\left(0,\,\frac{\mathrm{minv}[a] - x[a]}{|\mathrm{minv}[a]|}\right)+\max\left(0,\,\frac{x[a] - \mathrm{maxv}[a]}{|\mathrm{maxv}[a]|}\right)$$


4. Final output: After all generations:
    * The final population contains bounded candidates selected by Pareto rank and crowding distance.
    * The feasible rank-zero subset is exported separately as the approximate Pareto front.

## Experimental native backend

The repository includes an optional, validated OpenMP implementation of the Particle
Swarm mutation step. It is loaded only when `--pso-backend native` is selected. The
serial backend remains the portable default. Build, semantics, validation status, and
timing results are documented in `docs/native_backend.md`.

Since we just require basic for-loop unrolling for the parallelisation, we make use of the `OpenMP` API for the C programming language. To call the parallel optimisation function written in C we make use of an interface called `ctypes` in our Python code. The following is the main driving part of the Python code which calls the optimisation function written in C.

```py
import ctypes
from ctypes import CFUNCTYPE, POINTER, c_double, c_int, c_void_p
# Load the precompiled shared library
lib = ctypes.cdll.LoadLibrary('./libRION/libpso.so')

# Define the arguments and return type for the optimisation function
lib.optimize.argtypes = [c_void_p, c_void_p]
lib.optimize.restype = None

# call the function with the required parameters
lib.optimize(self._params, self._result)
```

On the C side, the function `optimize` corresponds to the function binding with the same name in Python.
```c
// Main optimization function with OpenMP parallelization
void optimize(PSOParams *params, PSOResult *result) {
    int num_particles = params->num_particles;
    int dim = params->dim;
    
    for (int iter = 0; iter < params->max_iter; iter++) {
        // Parallel particle update loop
        #pragma omp parallel
        {
            // Thread-local storage for potential global best updates
            double local_best_score = INFINITY;
            double *local_best_pos = (double*)malloc(dim * sizeof(double));
            
            #pragma omp for
            for (int p = 0; p < num_particles; p++) {
                double *pos = &params->positions[p * dim];
                double *vel = &params->velocities[p * dim];
                double *pbest = &params->personal_best_pos[p * dim];
                
                // Generate random values (thread-safe with OpenMP >= 3.0)
                unsigned int seed = omp_get_thread_num() + iter * 1000 + p;
                double r1 = (double)rand_r(&seed) / RAND_MAX;
                double r2 = (double)rand_r(&seed) / RAND_MAX;
                
                // Update velocity and position with bounds
                for (int d = 0; d < dim; d++) {
                    double cognitive = params->cognitive_coeff * r1 * (pbest[d] - pos[d]);
                    double social = params->social_coeff * r2 * (params->global_best_pos[d] - pos[d]);
                    vel[d] = params->inertia_weight * vel[d] + cognitive + social;
                    
                    // Velocity clamping
                    if (vel[d] > params->vmax[d]) vel[d] = params->vmax[d];
                    if (vel[d] < -params->vmax[d]) vel[d] = -params->vmax[d];
                    
                    pos[d] += vel[d];
                    
                    // Position clamping
                    if (pos[d] > params->upper_bounds[d]) pos[d] = params->upper_bounds[d];
                    if (pos[d] < params->lower_bounds[d]) pos[d] = params->lower_bounds[d];
                }
                
                // Evaluate new position
                double new_score = params->obj_func(pos, dim);
                
                // Update personal best
                if (new_score < params->personal_best_scores[p]) {
                    params->personal_best_scores[p] = new_score;
                    memcpy(pbest, pos, dim * sizeof(double));
                    
                    // Track local best for global update
                    if (new_score < local_best_score) {
                        local_best_score = new_score;
                        memcpy(local_best_pos, pos, dim * sizeof(double));
                    }
                }
            }
            
            // Critical section to update global best
            #pragma omp critical
            {
                if (local_best_score < params->global_best_score) {
                    params->global_best_score = local_best_score;
                    memcpy(params->global_best_pos, local_best_pos, dim * sizeof(double));
                }
            }
            
            free(local_best_pos);
        }
    }
    
    // Copy results
    memcpy(result->best_position, params->global_best_pos, dim * sizeof(double));
    result->best_score = params->global_best_score;
    memcpy(result->final_positions, params->positions, num_particles * dim * sizeof(double));
}
```
The excerpt above illustrates the original interface. The current wrapper adds seeded
execution, row-aware callbacks, status codes, safe cleanup, and package-relative loading;
use `libRION/libPSO_parallel.py` as the authoritative interface.

## Running the corrected serial baseline

The default workflow uses the portable Python PSO backend. It does not load or require
the optional OpenMP shared library. Python 3.10 or newer is recommended.

1. Create a virtual environment and activate it:
```sh
python -m venv .venv
source .venv/bin/activate
```

2. Navigate to the directory where you have cloned this repository and install the libraries from the `requirements.txt` file
```
pip install -r requirements.txt
```

3. Run the reproducible baseline:
```
make
```

To run the focused correctness checks:

```
make test
```

Arguments allow small or custom runs, for example:

```sh
python main.py --seed 42 --generations 3 --population-size 10 --pso-iterations 3
```

Each run writes to `results/baseline_seed_<seed>/` unless `--output-dir` is supplied:

- `population.csv`: the full final population with objectives, violation, feasibility,
  Pareto rank, crowding distance, and run seed.
- `pareto_front.csv`: the feasible rank-zero subset.
- `config.json`: data path, algorithm settings, objective convention, bounds, integer
  columns, and zero-impact policy.

The historical `results/optimized_population.csv` is retained unchanged. The corrected
cost-per-impact objective gives candidates with impact below one a deliberately poor
finite score (`1e15 + budget`); `--legacy-zero-impact` restores the historical `1e5`
score for comparison. Objective-range normalization is used only for PSO mutation
scalarization; Pareto selection always uses the original three objective values.

The `native` Make target is optional. After building it, run the native workflow with
`python main.py --pso-backend native`. Missing or incompatible native libraries produce
an actionable error and never prevent importing or using the serial backend.

## Data contracts and audit

Phase 1 data schemas, provenance rules, scenario configuration, and acquisition gaps are
documented in `docs/data_layer.md`. Run `make data-audit` to reproduce the existing CSV
audit. Run `make generate-synthetic` to create an explicitly labeled synthetic dataset
without overwriting the committed legacy fixture.

## DEA methodology fixture

After installing `requirements.txt`, run `make dea` to reproduce the input-oriented VRS
DEA methodology fixture. Model assumptions, validation rules, interpretation, limitations,
and Network DEA deferral are documented in `docs/dea_benchmark.md`. Current scores are
synthetic pipeline evidence and must not be interpreted as institutional efficiency.

## Synthetic KPI response-model fixture

Run `make train-models` to train the Phase 3 mean, linear, and Random Forest candidates,
select each KPI model on validation data, calibrate residual intervals separately, and
evaluate on an untouched test split. The versioned prediction interface and limitations
are documented in `docs/response_models.md`. This track uses only the legacy synthetic
fixture and is not evidence of real intervention effectiveness.

## Shared allocation evaluator

Run `make allocation-evaluator` after training the synthetic KPI models to reproduce the
Prompt 6 reference evaluation. The decision vector, repair order, objective definitions,
constraint residuals, uncertainty policy, unsupported inputs, and method-fixture results
are documented in `docs/allocation_problem.md`. All future optimizer adapters should call
this evaluator instead of duplicating prediction or constraint logic.

## End-to-end allocation workflow

Run `make allocation-small` for the Prompt 7 synthetic workflow. Canonical NSGA-II and
RION use the same evaluator and export separate full populations, feasible nondominated
archives, independent feasibility checks, evaluation accounting, reference comparisons,
and run metadata. Commands, artifact schemas, results, and limitations are documented in
`docs/allocation_workflow.md`. The legacy `python main.py` workflow remains available.

## Phase 5 algorithm integration

Run `make allocation-phase5` to execute canonical NSGA-II, NSGA-III, MOEA/D, genuine
archive-based MOPSO, RION, and the random-search sanity baseline on the same evaluator.
Reference directions, decomposition neighborhoods, MOPSO archive behavior, pilot-budget
accounting, tests, and current synthetic results are documented in
`docs/phase5_algorithms.md`.

## Phase 6 repeated benchmark

Run `make benchmark-smoke` for the resumable three-seed integration benchmark. All six
algorithms receive the same 100-candidate budget, including RION's inner PSO work. The
25-seed final benchmark has been completed and remains resumable through
`make benchmark-final`. Metric
definitions, failure and resume behavior, pooled-front limitations, statistics, and
artifact schemas are documented in `docs/phase6_benchmark.md`.

## Phase 6B scenarios and robustness

Run `make robustness-smoke` to reoptimize three budget levels and supported resource
shocks, apply four post-optimization policy preferences, and compare held-fixed base
strategies with scenario-specific reoptimization. The workflow uses shared Monte Carlo
draws for predictive and unit-cost sensitivity. Unsupported patent, compute, innovation,
and student effects remain explicit. See `docs/phase6b_robustness.md`.

## Phase 7 strategy portfolio

Run `make strategy-report` to build the decision portfolio and technical report entirely
from saved benchmark, robustness, reference, and model artifacts. It exports allocation
and KPI comparisons, resource and constraint checks, concrete actions, scenario and
algorithm tables, SVG figures, and proposal traceability. Selection rules and synthetic
evidence limits are documented in `docs/phase7_strategy_report.md`.

## Phase 12 completion audit

Run `make completion-audit` to verify the data/model hash chain, leakage controls,
feasibility, objective signs, front validity, matched evaluation accounting, uncertainty,
selection rules, saved-report sources, and optional native status. The command also runs
a small benchmark in a clean temporary source copy and independently recomputes its
hypervolume and IGD. See `docs/phase12_completion_audit.md`.

## Optional extensions

Run `make target-cost` for reverse minimum-cost optimization under configured KPI
targets. It reuses the shared evaluator, reports total and incremental cost, and rejects
unsupported innovation/student targets without spending evaluations. See
`docs/optional_target_cost.md`.

Run `make extension-assessment` to evaluate whether the audited data support Network
DEA or multi-period planning. Both are currently deferred because the synthetic
cross-section has neither observed stage links nor repeated periods. See
`docs/optional_advanced_extensions.md`.
