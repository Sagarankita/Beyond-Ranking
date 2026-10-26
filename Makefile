PYTHON ?= python3
UNAME_S := $(shell uname -s)

ifeq ($(UNAME_S),Darwin)
OPENMP_CC ?= gcc-16
else
OPENMP_CC ?= gcc
endif

NATIVE_CFLAGS ?= -O3 -fPIC -fopenmp -Wall -Wextra -Werror
NATIVE_LDFLAGS ?= -shared -fopenmp

.PHONY: main test native native-test clean-native data-audit generate-synthetic dea train-models allocation-evaluator allocation-small allocation-phase5

main:
	$(PYTHON) main.py

test:
	$(PYTHON) -m unittest discover -s tests -v

native: libRION/libpso.so

libRION/libpso.so: libRION/libPSO.c
	@command -v $(OPENMP_CC) >/dev/null 2>&1 || { \
		echo "OpenMP compiler '$(OPENMP_CC)' was not found."; \
		echo "macOS: brew install gcc (or set OPENMP_CC to an OpenMP compiler)."; \
		echo "Linux: install GCC with OpenMP support (or set OPENMP_CC)."; \
		exit 1; \
	}
	$(OPENMP_CC) $(NATIVE_CFLAGS) $(NATIVE_LDFLAGS) -o $@ $< -lm

native-test: native
	$(PYTHON) -m unittest discover -s tests -p 'test_native_pso.py' -v

clean-native:
	$(RM) libRION/libpso.so

data-audit:
	$(PYTHON) -m department_optimizer.data.audit

generate-synthetic:
	$(PYTHON) data/datagen.py --config configs/generator.example.json

dea:
	$(PYTHON) -m department_optimizer.efficiency.run

train-models:
	$(PYTHON) -m department_optimizer.modeling.train

allocation-evaluator:
	$(PYTHON) -m department_optimizer.allocation.run

allocation-small:
	$(PYTHON) main.py allocation --config configs/optimization/small_synthetic.json

allocation-phase5:
	$(PYTHON) main.py allocation --config configs/optimization/phase5_pilot_synthetic.json
.PHONY: benchmark-smoke benchmark-final robustness-smoke strategy-report completion-audit target-cost extension-assessment
.PHONY: public-data evidence-models public-allocation public-experiments public-completion-audit

public-data:
	$(PYTHON) -m department_optimizer.public_data.run --config configs/data/vjti_public_plus_synthetic_v1.json

evidence-models:
	$(PYTHON) -m department_optimizer.evidence_modeling.run --config configs/evidence_modeling/vjti_evidence_models_v1.json

public-allocation:
	$(PYTHON) -m department_optimizer.public_allocation.run --config configs/public_allocation/vjti_four_family_v1.json

public-experiments:
	$(PYTHON) -m department_optimizer.public_experiments.run --config configs/public_experiments/vjti_experiments_v1.json

public-completion-audit:
	$(PYTHON) -m department_optimizer.audit.public_run --config configs/audit/vjti_public_completion_v1.json

benchmark-smoke:
	$(PYTHON) -m department_optimizer.benchmark.run --config configs/benchmark/smoke_synthetic.json

benchmark-final:
	$(PYTHON) -m department_optimizer.benchmark.run --config configs/benchmark/final_synthetic_25seeds.json

robustness-smoke:
	$(PYTHON) -m department_optimizer.robustness.run --config configs/robustness/phase6b_synthetic.json

strategy-report:
	$(PYTHON) -m department_optimizer.reporting.run --config configs/reporting/phase7_synthetic.json

completion-audit:
	$(PYTHON) -m department_optimizer.audit.run --config configs/audit/phase12.json

target-cost:
	$(PYTHON) -m department_optimizer.target_cost.run --config configs/target_cost/synthetic_targets.json

extension-assessment:
	$(PYTHON) -m department_optimizer.extensions.run --config configs/extensions/evidence_assessment.json
