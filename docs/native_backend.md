# Optional native PSO backend

The native backend accelerates the particle update loop in C/OpenMP while retaining a
Python objective callback. It is optional: importing RION and running the default serial
backend never loads `libpso.so`.

## Build

Linux needs GCC with OpenMP support:

```sh
make native
```

On macOS, `/usr/bin/gcc` is normally Apple Clang and does not enable OpenMP with
`-fopenmp`. The Makefile therefore defaults to Homebrew's versioned `gcc-16` on macOS:

```sh
brew install gcc
make native
```

If the installed executable has a different name, select it explicitly:

```sh
make native OPENMP_CC=gcc-15
```

An alternative compiler may be selected with `OPENMP_CC`, provided it accepts the
configured `NATIVE_CFLAGS` and `NATIVE_LDFLAGS`. The produced library is
`libRION/libpso.so`. Override its runtime location with `RION_PSO_LIBRARY` when needed.

Use `make clean-native native` after changing the C API. A missing compiler or library
reports how to build the backend or select `--pso-backend serial`.

## Run and test

```sh
python main.py --pso-backend native --seed 42
make native-test
```

`make test` runs serial and native tests when the native library exists. If it does not,
native execution tests are reported as skipped with the prerequisite; the missing-library
diagnostic test still runs.

The native wrapper validates shapes, particle counts, contiguous float64 buffers, finite
positions/bounds/scores, bound order, and 64-bit seeds. It propagates Python callback
exceptions after C returns, checks native status codes, supports idempotent `close()` and
context-manager cleanup, and rejects use after close.

## Update semantics and reproducibility

Both backends now use synchronous PSO iterations:

1. Freeze the global-best position at the start of the iteration.
2. Update every particle against that snapshot.
3. Evaluate candidates and update personal bests.
4. Reduce personal bests to the next global best after all particles finish.

This removes concurrent reads of a changing global-best vector. Native random values are
derived from seed, iteration, particle, dimension, and stream, so results do not depend on
OpenMP scheduling or thread count. The serial backend uses NumPy's generator; identical
seeds reproduce within each backend but do not imply identical serial/native trajectories.

Objective callbacks enter Python and therefore acquire the GIL. Particle math can run in
parallel, but cheap Python objectives can make callback overhead dominate. Performance
must be measured for the actual workload rather than inferred from OpenMP use.

## Validation status on 26 October 2026

The backend was built on arm64 macOS with Homebrew GCC 16 and tested with four OpenMP
threads. Six native execution tests plus one loading/error test passed, covering:

- sphere-function convergence and bounds;
- exact seeded repeatability;
- row-aware particle indices;
- callback exception and non-finite result propagation;
- dimension validation, idempotent cleanup, and use-after-close;
- actionable missing-library handling.

A repeated full test run passed 16 tests. A small native RION run produced 10 feasible
candidates and two feasible rank-zero candidates. Repeats with one and four OpenMP
threads produced byte-identical population and Pareto CSV files.

Diagnostic timing with `OMP_NUM_THREADS=4`, three repeats, 100 particles, 10 dimensions,
and 20 PSO iterations produced these medians on this machine:

| Measurement | Serial | Native |
| --- | ---: | ---: |
| Cheap sphere PSO | 0.01224 s | 0.01678 s |
| Time per objective evaluation | 5.83 us | 7.99 us |
| Small end-to-end RION workflow | 0.24286 s | 0.24596 s |

These are diagnostic measurements, not a native speedup claim. They show that the Python
callback cost outweighs native particle-update savings for this small, cheap-objective
workload. Reproduce them with:

```sh
OMP_NUM_THREADS=4 python -m benchmarks.native_timing \
  --repeats 3 --output results/native_backend_timing.json
```

The machine-readable measurement is stored in `results/native_backend_timing.json`.
