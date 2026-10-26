"""Safe ctypes wrapper for the optional OpenMP PSO backend."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Callable

import numpy as np


class NativeBackendUnavailable(RuntimeError):
    """Raised when the optional native PSO library cannot be loaded."""


OBJECTIVE_FUNC = ctypes.CFUNCTYPE(
    ctypes.c_double,
    ctypes.POINTER(ctypes.c_double),
    ctypes.c_int,
    ctypes.c_int,
)
_LIBRARIES: dict[Path, ctypes.CDLL] = {}
_STATUS_MESSAGES = {
    1: "invalid native PSO argument or result dimensions",
    2: "native PSO memory allocation failed",
    3: "objective callback returned a non-finite value or raised an exception",
}


def default_library_path() -> Path:
    configured = os.environ.get("RION_PSO_LIBRARY")
    return Path(configured).expanduser() if configured else Path(__file__).with_name("libpso.so")


def _configure_library(lib: ctypes.CDLL) -> ctypes.CDLL:
    double_pointer = ctypes.POINTER(ctypes.c_double)
    lib.pso_create.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        double_pointer,
        double_pointer,
        double_pointer,
        double_pointer,
        ctypes.c_uint64,
        OBJECTIVE_FUNC,
    ]
    lib.pso_create.restype = ctypes.c_void_p
    lib.pso_free.argtypes = [ctypes.c_void_p]
    lib.pso_free.restype = None
    lib.result_create.argtypes = [ctypes.c_int, ctypes.c_int]
    lib.result_create.restype = ctypes.c_void_p
    lib.result_free.argtypes = [ctypes.c_void_p]
    lib.result_free.restype = None
    lib.optimize.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    lib.optimize.restype = ctypes.c_int
    lib.get_results.argtypes = [
        ctypes.c_void_p,
        double_pointer,
        double_pointer,
        double_pointer,
        ctypes.c_int,
        ctypes.c_int,
    ]
    lib.get_results.restype = ctypes.c_int
    lib.pso_openmp_enabled.argtypes = []
    lib.pso_openmp_enabled.restype = ctypes.c_int
    return lib


def load_native_library(path: str | Path | None = None) -> ctypes.CDLL:
    library_path = (Path(path) if path is not None else default_library_path()).resolve()
    if library_path in _LIBRARIES:
        return _LIBRARIES[library_path]
    if not library_path.is_file():
        raise NativeBackendUnavailable(
            f"native PSO library not found at {library_path}. "
            "Run `make native` with an OpenMP-capable compiler, or use "
            "`--pso-backend serial`."
        )
    try:
        library = _configure_library(ctypes.CDLL(str(library_path)))
    except OSError as exc:
        raise NativeBackendUnavailable(
            f"could not load native PSO library {library_path}: {exc}. "
            "Rebuild it with `make clean-native native`, or use `--pso-backend serial`."
        ) from exc
    if library.pso_openmp_enabled() != 1:
        raise NativeBackendUnavailable(
            f"{library_path} was built without OpenMP; rebuild with `make clean-native native`"
        )
    _LIBRARIES[library_path] = library
    return library


class PSO:
    """Bounded synchronous PSO backed by C/OpenMP.

    The update semantics match the serial backend: all particles see a frozen global
    best within an iteration, followed by a deterministic best-state reduction. The
    C backend uses a counter-based random stream, so seeded runs are reproducible but
    do not follow the same trajectory as NumPy's generator in the serial backend.
    """

    def __init__(
        self,
        obj_func: Callable[..., float],
        data,
        num_particles: int | None = None,
        max_iter: int = 100,
        inertia_weight: float = 0.5,
        cognitive_coeff: float = 1.5,
        social_coeff: float = 1.5,
        lower_bounds=None,
        upper_bounds=None,
        seed: int | None = None,
        objective_uses_particle_index: bool = False,
        library_path: str | Path | None = None,
    ):
        self._lib = load_native_library(library_path)
        self._params = None
        self._result = None
        self._closed = False
        self.obj_func = obj_func
        self.objective_uses_particle_index = objective_uses_particle_index
        self.seed = 0 if seed is None else int(seed)
        if self.seed < 0 or self.seed > np.iinfo(np.uint64).max:
            raise ValueError("seed must fit in an unsigned 64-bit integer")

        positions = np.asarray(data, dtype=np.float64)
        if positions.ndim != 2 or not positions.size:
            raise ValueError("data must be a non-empty 2D array")
        self.positions = np.ascontiguousarray(positions)
        actual_particles, self.dim = self.positions.shape
        self.num_particles = actual_particles if num_particles is None else num_particles
        if self.num_particles != actual_particles:
            raise ValueError("num_particles must match the number of data rows")
        if max_iter < 0:
            raise ValueError("max_iter must be non-negative")
        self.max_iter = max_iter

        data_min = np.min(self.positions, axis=0)
        data_max = np.max(self.positions, axis=0)
        data_range = data_max - data_min
        self.lower_bounds = np.ascontiguousarray(
            data_min - 0.5 * data_range if lower_bounds is None else lower_bounds,
            dtype=np.float64,
        )
        self.upper_bounds = np.ascontiguousarray(
            data_max + 0.5 * data_range if upper_bounds is None else upper_bounds,
            dtype=np.float64,
        )
        if self.lower_bounds.shape != (self.dim,) or self.upper_bounds.shape != (self.dim,):
            raise ValueError("bounds must contain one value per dimension")
        if not np.all(np.isfinite(self.positions)) or not np.all(np.isfinite(self.lower_bounds)) or not np.all(np.isfinite(self.upper_bounds)):
            raise ValueError("positions and bounds must be finite")
        if np.any(self.lower_bounds > self.upper_bounds):
            raise ValueError("lower bounds must not exceed upper bounds")
        self.positions = np.ascontiguousarray(
            np.clip(self.positions, self.lower_bounds, self.upper_bounds)
        )

        rng = np.random.default_rng(self.seed)
        vmax = 0.2 * (self.upper_bounds - self.lower_bounds)
        self.velocities = np.ascontiguousarray(
            np.clip(rng.uniform(-1.0, 1.0, self.positions.shape), -vmax, vmax)
        )
        self._callback_error: BaseException | None = None

        @OBJECTIVE_FUNC
        def c_objective(position_pointer, dimension, particle_index):
            if self._callback_error is not None:
                return float("nan")
            try:
                if dimension != self.dim or not 0 <= particle_index < self.num_particles:
                    raise RuntimeError("native callback supplied invalid dimensions")
                position = np.ctypeslib.as_array(position_pointer, shape=(dimension,))
                value = (
                    self.obj_func(position, particle_index)
                    if self.objective_uses_particle_index
                    else self.obj_func(position)
                )
                value = float(value)
                if not np.isfinite(value):
                    raise ValueError("objective function returned a non-finite score")
                return value
            except BaseException as exc:
                self._callback_error = exc
                return float("nan")

        self._c_objective = c_objective
        pointer = ctypes.POINTER(ctypes.c_double)
        self._params = self._lib.pso_create(
            self.num_particles,
            self.dim,
            self.max_iter,
            float(inertia_weight),
            float(cognitive_coeff),
            float(social_coeff),
            self.positions.ctypes.data_as(pointer),
            self.velocities.ctypes.data_as(pointer),
            self.lower_bounds.ctypes.data_as(pointer),
            self.upper_bounds.ctypes.data_as(pointer),
            self.seed,
            self._c_objective,
        )
        if not self._params:
            if self._callback_error is not None:
                error = self._callback_error
                self.close()
                raise RuntimeError("objective callback failed during native initialization") from error
            self.close()
            raise RuntimeError("native PSO initialization rejected its arguments or ran out of memory")
        self._result = self._lib.result_create(self.num_particles, self.dim)
        if not self._result:
            self.close()
            raise MemoryError("native PSO result allocation failed")

    def optimize(self):
        if self._closed or not self._params or not self._result:
            raise RuntimeError("native PSO instance is closed")
        status = self._lib.optimize(self._params, self._result)
        if self._callback_error is not None:
            raise RuntimeError("objective callback failed during native optimization") from self._callback_error
        if status != 0:
            raise RuntimeError(_STATUS_MESSAGES.get(status, f"native PSO failed with status {status}"))

        best_position = np.empty(self.dim, dtype=np.float64)
        final_positions = np.empty((self.num_particles, self.dim), dtype=np.float64)
        best_score = ctypes.c_double()
        pointer = ctypes.POINTER(ctypes.c_double)
        status = self._lib.get_results(
            self._result,
            best_position.ctypes.data_as(pointer),
            ctypes.byref(best_score),
            final_positions.ctypes.data_as(pointer),
            self.num_particles,
            self.dim,
        )
        if status != 0:
            raise RuntimeError(_STATUS_MESSAGES.get(status, f"native result extraction failed with status {status}"))
        if not np.isfinite(best_score.value) or not np.all(np.isfinite(final_positions)):
            raise RuntimeError("native PSO returned non-finite results")
        self.positions = final_positions
        self.global_best_position = best_position
        self.global_best_score = float(best_score.value)
        return best_position.copy(), self.global_best_score

    def close(self):
        if self._closed:
            return
        if self._result:
            self._lib.result_free(self._result)
            self._result = None
        if self._params:
            self._lib.pso_free(self._params)
            self._params = None
        self._closed = True

    def __enter__(self):
        if self._closed:
            raise RuntimeError("native PSO instance is closed")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
