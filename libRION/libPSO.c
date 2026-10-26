#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <omp.h>

typedef double (*ObjectiveFunc)(const double *, int, int);

typedef struct {
    double *positions;
    double *velocities;
    double *personal_best_pos;
    double *personal_best_scores;
    double *global_best_pos;
    double global_best_score;
    double *lower_bounds;
    double *upper_bounds;
    double *vmax;
    int num_particles;
    int dim;
    int max_iter;
    double inertia_weight;
    double cognitive_coeff;
    double social_coeff;
    uint64_t seed;
    ObjectiveFunc obj_func;
} PSOParams;

typedef struct {
    double *best_position;
    double best_score;
    double *final_positions;
    int num_particles;
    int dim;
} PSOResult;

enum {
    PSO_OK = 0,
    PSO_ERR_ARGUMENT = 1,
    PSO_ERR_ALLOCATION = 2,
    PSO_ERR_OBJECTIVE = 3
};

static uint64_t splitmix64(uint64_t value) {
    value += UINT64_C(0x9e3779b97f4a7c15);
    value = (value ^ (value >> 30)) * UINT64_C(0xbf58476d1ce4e5b9);
    value = (value ^ (value >> 27)) * UINT64_C(0x94d049bb133111eb);
    return value ^ (value >> 31);
}

static double deterministic_random(
    uint64_t seed, int iteration, int particle, int dimension, int stream
) {
    uint64_t key = seed;
    key ^= UINT64_C(0x9e3779b97f4a7c15) * (uint64_t)(iteration + 1);
    key ^= UINT64_C(0xbf58476d1ce4e5b9) * (uint64_t)(particle + 1);
    key ^= UINT64_C(0x94d049bb133111eb) * (uint64_t)(dimension + 1);
    key ^= UINT64_C(0xd6e8feb86659fd93) * (uint64_t)(stream + 1);
    return (double)(splitmix64(key) >> 11) * (1.0 / 9007199254740992.0);
}

static int size_is_valid(int particles, int dim) {
    if (particles <= 0 || dim <= 0) return 0;
    size_t p = (size_t)particles;
    size_t d = (size_t)dim;
    return p <= SIZE_MAX / d && p * d <= SIZE_MAX / sizeof(double);
}

void pso_free(PSOParams *params) {
    if (!params) return;
    free(params->positions);
    free(params->velocities);
    free(params->personal_best_pos);
    free(params->personal_best_scores);
    free(params->global_best_pos);
    free(params->lower_bounds);
    free(params->upper_bounds);
    free(params->vmax);
    free(params);
}

PSOParams *pso_create(
    int num_particles,
    int dim,
    int max_iter,
    double inertia,
    double cognitive,
    double social,
    const double *initial_positions,
    const double *initial_velocities,
    const double *lower_bounds,
    const double *upper_bounds,
    uint64_t seed,
    ObjectiveFunc obj_func
) {
    if (!size_is_valid(num_particles, dim) || max_iter < 0 ||
        !isfinite(inertia) || !isfinite(cognitive) || !isfinite(social) ||
        !initial_positions || !initial_velocities || !lower_bounds ||
        !upper_bounds || !obj_func) {
        return NULL;
    }

    PSOParams *params = (PSOParams *)calloc(1, sizeof(PSOParams));
    if (!params) return NULL;
    params->num_particles = num_particles;
    params->dim = dim;
    params->max_iter = max_iter;
    params->inertia_weight = inertia;
    params->cognitive_coeff = cognitive;
    params->social_coeff = social;
    params->seed = seed;
    params->obj_func = obj_func;

    size_t total = (size_t)num_particles * (size_t)dim;
    params->positions = (double *)malloc(total * sizeof(double));
    params->velocities = (double *)malloc(total * sizeof(double));
    params->personal_best_pos = (double *)malloc(total * sizeof(double));
    params->personal_best_scores = (double *)malloc((size_t)num_particles * sizeof(double));
    params->global_best_pos = (double *)malloc((size_t)dim * sizeof(double));
    params->lower_bounds = (double *)malloc((size_t)dim * sizeof(double));
    params->upper_bounds = (double *)malloc((size_t)dim * sizeof(double));
    params->vmax = (double *)malloc((size_t)dim * sizeof(double));
    if (!params->positions || !params->velocities || !params->personal_best_pos ||
        !params->personal_best_scores || !params->global_best_pos ||
        !params->lower_bounds || !params->upper_bounds || !params->vmax) {
        pso_free(params);
        return NULL;
    }

    memcpy(params->lower_bounds, lower_bounds, (size_t)dim * sizeof(double));
    memcpy(params->upper_bounds, upper_bounds, (size_t)dim * sizeof(double));
    for (int d = 0; d < dim; ++d) {
        if (!isfinite(lower_bounds[d]) || !isfinite(upper_bounds[d]) ||
            lower_bounds[d] > upper_bounds[d]) {
            pso_free(params);
            return NULL;
        }
        params->vmax[d] = 0.2 * (upper_bounds[d] - lower_bounds[d]);
    }

    for (size_t i = 0; i < total; ++i) {
        int d = (int)(i % (size_t)dim);
        if (!isfinite(initial_positions[i]) || !isfinite(initial_velocities[i])) {
            pso_free(params);
            return NULL;
        }
        double position = initial_positions[i];
        if (position < lower_bounds[d]) position = lower_bounds[d];
        if (position > upper_bounds[d]) position = upper_bounds[d];
        double velocity = initial_velocities[i];
        if (velocity < -params->vmax[d]) velocity = -params->vmax[d];
        if (velocity > params->vmax[d]) velocity = params->vmax[d];
        params->positions[i] = position;
        params->velocities[i] = velocity;
        params->personal_best_pos[i] = position;
    }

    params->global_best_score = INFINITY;
    for (int p = 0; p < num_particles; ++p) {
        double score = obj_func(&params->positions[(size_t)p * dim], dim, p);
        if (!isfinite(score)) {
            pso_free(params);
            return NULL;
        }
        params->personal_best_scores[p] = score;
        if (score < params->global_best_score) {
            params->global_best_score = score;
            memcpy(
                params->global_best_pos,
                &params->positions[(size_t)p * dim],
                (size_t)dim * sizeof(double)
            );
        }
    }
    return params;
}

PSOResult *result_create(int num_particles, int dim) {
    if (!size_is_valid(num_particles, dim)) return NULL;
    PSOResult *result = (PSOResult *)calloc(1, sizeof(PSOResult));
    if (!result) return NULL;
    result->num_particles = num_particles;
    result->dim = dim;
    result->best_position = (double *)malloc((size_t)dim * sizeof(double));
    result->final_positions = (double *)malloc(
        (size_t)num_particles * (size_t)dim * sizeof(double)
    );
    if (!result->best_position || !result->final_positions) {
        free(result->best_position);
        free(result->final_positions);
        free(result);
        return NULL;
    }
    return result;
}

void result_free(PSOResult *result) {
    if (!result) return;
    free(result->best_position);
    free(result->final_positions);
    free(result);
}

int optimize(PSOParams *params, PSOResult *result) {
    if (!params || !result || result->num_particles != params->num_particles ||
        result->dim != params->dim) {
        return PSO_ERR_ARGUMENT;
    }
    int particles = params->num_particles;
    int dim = params->dim;
    double *global_snapshot = (double *)malloc((size_t)dim * sizeof(double));
    double *new_scores = (double *)malloc((size_t)particles * sizeof(double));
    if (!global_snapshot || !new_scores) {
        free(global_snapshot);
        free(new_scores);
        return PSO_ERR_ALLOCATION;
    }

    for (int iteration = 0; iteration < params->max_iter; ++iteration) {
        memcpy(global_snapshot, params->global_best_pos, (size_t)dim * sizeof(double));

        #pragma omp parallel for schedule(static)
        for (int p = 0; p < particles; ++p) {
            double *position = &params->positions[(size_t)p * dim];
            double *velocity = &params->velocities[(size_t)p * dim];
            double *personal_best = &params->personal_best_pos[(size_t)p * dim];
            for (int d = 0; d < dim; ++d) {
                double r1 = deterministic_random(params->seed, iteration, p, d, 0);
                double r2 = deterministic_random(params->seed, iteration, p, d, 1);
                double cognitive = params->cognitive_coeff * r1 *
                    (personal_best[d] - position[d]);
                double social = params->social_coeff * r2 *
                    (global_snapshot[d] - position[d]);
                velocity[d] = params->inertia_weight * velocity[d] + cognitive + social;
                if (velocity[d] < -params->vmax[d]) velocity[d] = -params->vmax[d];
                if (velocity[d] > params->vmax[d]) velocity[d] = params->vmax[d];
                position[d] += velocity[d];
                if (position[d] < params->lower_bounds[d]) position[d] = params->lower_bounds[d];
                if (position[d] > params->upper_bounds[d]) position[d] = params->upper_bounds[d];
            }
            new_scores[p] = params->obj_func(position, dim, p);
        }

        for (int p = 0; p < particles; ++p) {
            if (!isfinite(new_scores[p])) {
                free(global_snapshot);
                free(new_scores);
                return PSO_ERR_OBJECTIVE;
            }
            if (new_scores[p] < params->personal_best_scores[p]) {
                params->personal_best_scores[p] = new_scores[p];
                memcpy(
                    &params->personal_best_pos[(size_t)p * dim],
                    &params->positions[(size_t)p * dim],
                    (size_t)dim * sizeof(double)
                );
            }
        }

        int best = 0;
        for (int p = 1; p < particles; ++p) {
            if (params->personal_best_scores[p] < params->personal_best_scores[best]) {
                best = p;
            }
        }
        params->global_best_score = params->personal_best_scores[best];
        memcpy(
            params->global_best_pos,
            &params->personal_best_pos[(size_t)best * dim],
            (size_t)dim * sizeof(double)
        );
    }

    memcpy(result->best_position, params->global_best_pos, (size_t)dim * sizeof(double));
    result->best_score = params->global_best_score;
    memcpy(
        result->final_positions,
        params->positions,
        (size_t)particles * (size_t)dim * sizeof(double)
    );
    free(global_snapshot);
    free(new_scores);
    return PSO_OK;
}

int get_results(
    const PSOResult *result,
    double *best_pos_out,
    double *best_score_out,
    double *final_pos_out,
    int num_particles,
    int dim
) {
    if (!result || !best_pos_out || !best_score_out || !final_pos_out ||
        result->num_particles != num_particles || result->dim != dim) {
        return PSO_ERR_ARGUMENT;
    }
    memcpy(best_pos_out, result->best_position, (size_t)dim * sizeof(double));
    *best_score_out = result->best_score;
    memcpy(
        final_pos_out,
        result->final_positions,
        (size_t)num_particles * (size_t)dim * sizeof(double)
    );
    return PSO_OK;
}

int pso_openmp_enabled(void) {
#ifdef _OPENMP
    return 1;
#else
    return 0;
#endif
}
