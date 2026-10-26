"""Canonical allocation decoder, repairer, constraint system, and evaluator."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


OBJECTIVE_FAMILIES = ("research", "innovation", "student", "societal")


class ProblemConfigurationError(ValueError):
    """Raised when an allocation problem is unsupported or impossible."""


@dataclass
class EvaluationResult:
    decoded: dict[str, float]
    repaired: dict[str, float]
    repair_actions: list[str]
    model_features: dict[str, float]
    raw_kpis: dict[str, float]
    uncertainty: dict[str, dict[str, float]]
    objective_benefits: dict[str, float]
    objective_scores: dict[str, float]
    objective_supported: dict[str, bool]
    constraint_residuals: dict[str, float]
    normalized_constraint_violations: dict[str, float]
    normalized_violation: float
    nominal_feasible: bool
    robust_feasible: bool
    estimated_probability_feasible: float | None
    feasibility_probability_status: str
    support_flags: dict[str, Any]
    cost: float
    budget_remaining: float
    dea_efficiency: float | None
    dea_status: str

    def to_dict(self):
        return asdict(self)

    def objective_vector(self):
        return np.array([self.objective_scores[name] for name in OBJECTIVE_FAMILIES])


def _snap(value: float, lower: float, increment: float):
    steps = round((value - lower) / increment)
    return lower + steps * increment


class AllocationProblem:
    """One scientific evaluator shared by optimizer adapters."""

    def __init__(self, config: Mapping[str, Any], model):
        self.config = dict(config)
        self.model = model
        self.variables = list(self.config.get("decision_variables", ()))
        self.variable_names = [item["name"] for item in self.variables]
        self._validate_configuration()

    def _validate_configuration(self):
        if len(self.variables) == 0 or len(set(self.variable_names)) != len(self.variables):
            raise ProblemConfigurationError("decision variables must be non-empty and unique")
        model_features = set(self.model.manifest["feature_columns"])
        fixed = set(self.config.get("fixed_context", {}))
        required_context = {"faculty_phd", "faculty_other"}
        missing_context = sorted(required_context.difference(fixed))
        if missing_context:
            raise ProblemConfigurationError(f"fixed context is missing {missing_context}")
        required_decisions = {"frac_research_phd", "frac_research_other"}
        missing_decisions = sorted(required_decisions.difference(self.variable_names))
        if missing_decisions:
            raise ProblemConfigurationError(
                f"faculty-time accounting requires decisions {missing_decisions}"
            )
        mapped = set()
        for variable in self.variables:
            required = {"name", "model_feature", "type", "lower", "upper", "increment", "cost_mode"}
            missing = sorted(required.difference(variable))
            if missing:
                raise ProblemConfigurationError(
                    f"decision variable {variable.get('name', '<unknown>')} lacks {missing}"
                )
            if variable["type"] not in {"continuous", "integer"}:
                raise ProblemConfigurationError(f"unsupported variable type: {variable['type']}")
            if variable["lower"] > variable["upper"] or variable["increment"] <= 0:
                raise ProblemConfigurationError(f"invalid bounds/increment for {variable['name']}")
            if variable["cost_mode"] not in {"direct_money", "unit_cost", "non_monetary"}:
                raise ProblemConfigurationError(f"invalid cost mode for {variable['name']}")
            if variable["cost_mode"] == "unit_cost" and variable.get("unit_cost", 0) < 0:
                raise ProblemConfigurationError(f"unit cost must be non-negative for {variable['name']}")
            model_feature = variable["model_feature"]
            if model_feature in mapped or model_feature in fixed:
                raise ProblemConfigurationError(
                    f"model feature {model_feature} is supplied more than once"
                )
            mapped.add(model_feature)
        unknown_features = sorted((mapped | fixed).difference(model_features))
        if unknown_features:
            raise ProblemConfigurationError(
                f"scenario contains inputs unsupported by the response model: {unknown_features}"
            )
        missing_features = sorted(model_features.difference(mapped | fixed))
        if missing_features:
            raise ProblemConfigurationError(
                f"scenario does not supply required model features: {missing_features}"
            )
        families = self.config.get("objective_families", {})
        if set(families) != set(OBJECTIVE_FAMILIES):
            raise ProblemConfigurationError(
                f"objective_families must be exactly {list(OBJECTIVE_FAMILIES)}"
            )
        targets = set(self.model.manifest["target_columns"])
        for family_name in OBJECTIVE_FAMILIES:
            family = families[family_name]
            policy = family.get("missing_kpi_policy")
            if policy not in {"error", "zero_score"}:
                raise ProblemConfigurationError(
                    f"invalid missing KPI policy for {family_name}: {policy}"
                )
            components = family.get("components", [])
            if not components and policy == "error":
                raise ProblemConfigurationError(f"{family_name} has no KPI components")
            total_weight = 0.0
            for component in components:
                if component["kpi"] not in targets:
                    if policy == "error":
                        raise ProblemConfigurationError(
                            f"{family_name} requires unsupported KPI {component['kpi']}"
                        )
                    continue
                normalization = component.get("normalization", {})
                if normalization.get("method") != "minmax":
                    raise ProblemConfigurationError("only explicit minmax normalization is supported")
                if normalization["maximum"] <= normalization["minimum"]:
                    raise ProblemConfigurationError("normalization maximum must exceed minimum")
                if component.get("direction") not in {"maximize", "minimize"}:
                    raise ProblemConfigurationError("objective direction must be maximize or minimize")
                if component.get("weight", 0) < 0:
                    raise ProblemConfigurationError("objective weights must be non-negative")
                total_weight += float(component["weight"])
            if components and not np.isclose(total_weight, 1.0):
                raise ProblemConfigurationError(f"{family_name} component weights must sum to one")
        minimum_cost = self.allocation_cost(
            {variable["name"]: float(variable["lower"]) for variable in self.variables}
        )
        if minimum_cost > float(self.config["budget_limit"]):
            raise ProblemConfigurationError("minimum decision bounds exceed the budget")
        faculty = self.config["faculty_time"]
        total_faculty = float(self.config["fixed_context"]["faculty_phd"]) + float(
            self.config["fixed_context"]["faculty_other"]
        )
        reserved = sum(
            float(faculty[name])
            for name in (
                "minimum_teaching_fte",
                "minimum_student_support_fte",
                "minimum_service_fte",
            )
        )
        if reserved > total_faculty:
            raise ProblemConfigurationError("teaching/student/service floors exceed faculty supply")
        if float(faculty["capacity_fte"]) > total_faculty - reserved:
            raise ProblemConfigurationError(
                "faculty research capacity conflicts with teaching/student/service floors"
            )
        lower_allocation = {
            variable["name"]: float(variable["lower"]) for variable in self.variables
        }
        allowed_research = min(
            float(faculty["capacity_fte"]), total_faculty - reserved
        )
        if self._research_fte(lower_allocation) > allowed_research + 1e-9:
            raise ProblemConfigurationError(
                "minimum research-effort bounds violate faculty capacity or reserved floors"
            )
        variable_map = {item["name"]: item for item in self.variables}
        for dependency in self.config.get("dependencies", []):
            count_name = dependency.get("count_variable")
            funding_name = dependency.get("funding_variable")
            if count_name not in variable_map or funding_name not in variable_map:
                raise ProblemConfigurationError(
                    f"dependency {dependency.get('name')} references an unknown decision"
                )
            minimum_per_unit = float(dependency.get("minimum_funding_per_unit", -1))
            if minimum_per_unit < 0:
                raise ProblemConfigurationError("dependency funding per unit must be non-negative")
            if (
                float(variable_map[count_name]["lower"]) * minimum_per_unit
                > float(variable_map[funding_name]["upper"])
            ):
                raise ProblemConfigurationError(
                    f"dependency {dependency['name']} is impossible within decision bounds"
                )
        for constraint in self.config.get("uncertain_service_constraints", []):
            if constraint["kpi"] not in targets:
                raise ProblemConfigurationError(
                    f"uncertain service constraint requires unsupported KPI {constraint['kpi']}"
                )
            if constraint.get("rule") != "conservative_interval":
                raise ProblemConfigurationError(
                    "uncertain service constraints require rule='conservative_interval'"
                )
            if constraint.get("direction") not in {"minimum", "maximum"}:
                raise ProblemConfigurationError(
                    "uncertain service constraint direction must be minimum or maximum"
                )

    def decode(self, candidate: Sequence[float] | Mapping[str, float]):
        if isinstance(candidate, Mapping):
            missing = sorted(set(self.variable_names).difference(candidate))
            extra = sorted(set(candidate).difference(self.variable_names))
            if missing or extra:
                raise ValueError(f"candidate keys mismatch; missing={missing}, extra={extra}")
            values = [candidate[name] for name in self.variable_names]
        else:
            values = list(candidate)
            if len(values) != len(self.variables):
                raise ValueError(
                    f"candidate has {len(values)} values; expected {len(self.variables)}"
                )
        decoded = {}
        for variable, value in zip(self.variables, values):
            number = float(value)
            if not np.isfinite(number):
                raise ValueError(f"candidate value must be finite: {variable['name']}")
            decoded[variable["name"]] = number
        return decoded

    def allocation_cost(self, allocation: Mapping[str, float]):
        total = 0.0
        for variable in self.variables:
            value = float(allocation[variable["name"]])
            if variable["cost_mode"] == "direct_money":
                total += value
            elif variable["cost_mode"] == "unit_cost":
                total += value * float(variable["unit_cost"])
        return total

    def _research_fte(self, allocation):
        context = self.config["fixed_context"]
        return (
            float(context["faculty_phd"]) * allocation["frac_research_phd"]
            + float(context["faculty_other"]) * allocation["frac_research_other"]
        )

    def repair(self, candidate: Sequence[float] | Mapping[str, float]):
        decoded = self.decode(candidate)
        repaired = {}
        actions = []
        variable_map = {item["name"]: item for item in self.variables}
        for variable in self.variables:
            name = variable["name"]
            original = decoded[name]
            value = min(max(original, float(variable["lower"])), float(variable["upper"]))
            value = _snap(value, float(variable["lower"]), float(variable["increment"]))
            value = min(max(value, float(variable["lower"])), float(variable["upper"]))
            if variable["type"] == "integer":
                value = float(round(value))
            repaired[name] = value
            if not np.isclose(value, original):
                actions.append(f"{name}: {original:g} -> {value:g} (bounds/increment/type)")

        faculty = self.config["faculty_time"]
        allowed_research = min(
            float(faculty["capacity_fte"]),
            float(self.config["fixed_context"]["faculty_phd"])
            + float(self.config["fixed_context"]["faculty_other"])
            - sum(
                float(faculty[name])
                for name in (
                    "minimum_teaching_fte",
                    "minimum_student_support_fte",
                    "minimum_service_fte",
                )
            ),
        )
        for fraction_name, faculty_name in (
            ("frac_research_other", "faculty_other"),
            ("frac_research_phd", "faculty_phd"),
        ):
            excess = self._research_fte(repaired) - allowed_research
            if excess <= 1e-9:
                break
            variable = variable_map[fraction_name]
            headcount = float(self.config["fixed_context"][faculty_name])
            raw_target = max(
                float(variable["lower"]), repaired[fraction_name] - excess / headcount
            )
            target = _snap(
                raw_target, float(variable["lower"]), float(variable["increment"])
            )
            if target > raw_target + 1e-12:
                target -= float(variable["increment"])
            target = max(float(variable["lower"]), target)
            if not np.isclose(target, repaired[fraction_name]):
                actions.append(
                    f"{fraction_name}: {repaired[fraction_name]:g} -> {target:g} (faculty capacity/floors)"
                )
                repaired[fraction_name] = target

        for dependency in self.config.get("dependencies", []):
            count_name = dependency["count_variable"]
            funding = repaired[dependency["funding_variable"]]
            permitted = np.floor(funding / float(dependency["minimum_funding_per_unit"]))
            if repaired[count_name] > permitted:
                old = repaired[count_name]
                variable = variable_map[count_name]
                repaired[count_name] = max(float(variable["lower"]), float(permitted))
                actions.append(
                    f"{count_name}: {old:g} -> {repaired[count_name]:g} ({dependency['name']})"
                )

        budget = float(self.config["budget_limit"])
        for variable in sorted(
            self.variables, key=lambda item: float(item.get("repair_priority", 0))
        ):
            while self.allocation_cost(repaired) > budget + 1e-8:
                name = variable["name"]
                if variable["cost_mode"] == "non_monetary":
                    break
                lower = float(variable["lower"])
                if repaired[name] <= lower + 1e-12:
                    break
                old = repaired[name]
                if variable["cost_mode"] == "direct_money":
                    excess = self.allocation_cost(repaired) - budget
                    decrement = np.ceil(excess / float(variable["increment"])) * float(
                        variable["increment"]
                    )
                else:
                    decrement = float(variable["increment"])
                repaired[name] = max(lower, repaired[name] - decrement)
                if not np.isclose(old, repaired[name]):
                    actions.append(f"{name}: {old:g} -> {repaired[name]:g} (budget)")
        return decoded, repaired, actions

    def _model_features(self, allocation):
        values = dict(self.config["fixed_context"])
        for variable in self.variables:
            values[variable["model_feature"]] = allocation[variable["name"]]
        return values

    def _constraints(self, allocation, prediction):
        residuals = {}
        scales = {}
        for variable in self.variables:
            name = variable["name"]
            value = allocation[name]
            lower, upper = float(variable["lower"]), float(variable["upper"])
            residuals[f"bounds__{name}"] = max(lower - value, value - upper, 0.0)
            scales[f"bounds__{name}"] = max(upper - lower, 1.0)
            if variable["type"] == "integer":
                residuals[f"integrality__{name}"] = abs(value - round(value))
                scales[f"integrality__{name}"] = 1.0
            increment = float(variable["increment"])
            steps = (value - lower) / increment
            residuals[f"increment__{name}"] = abs(steps - round(steps)) * increment
            scales[f"increment__{name}"] = max(increment, 1e-12)
        cost = self.allocation_cost(allocation)
        residuals["budget"] = cost - float(self.config["budget_limit"])
        scales["budget"] = float(self.config["budget_limit"])
        research_fte = self._research_fte(allocation)
        faculty = self.config["faculty_time"]
        total_faculty = float(self.config["fixed_context"]["faculty_phd"]) + float(
            self.config["fixed_context"]["faculty_other"]
        )
        residuals["faculty_time_capacity"] = research_fte - float(faculty["capacity_fte"])
        scales["faculty_time_capacity"] = float(faculty["capacity_fte"])
        for key, config_name in (
            ("teaching_floor", "minimum_teaching_fte"),
            ("student_support_floor", "minimum_student_support_fte"),
            ("service_floor", "minimum_service_fte"),
        ):
            other_floors = sum(
                float(faculty[name])
                for name in (
                    "minimum_teaching_fte",
                    "minimum_student_support_fte",
                    "minimum_service_fte",
                )
                if name != config_name
            )
            available = total_faculty - research_fte - other_floors
            residuals[key] = float(faculty[config_name]) - available
            scales[key] = total_faculty
        for dependency in self.config.get("dependencies", []):
            residuals[f"dependency__{dependency['name']}"] = (
                allocation[dependency["count_variable"]]
                * float(dependency["minimum_funding_per_unit"])
                - allocation[dependency["funding_variable"]]
            )
            scales[f"dependency__{dependency['name']}"] = max(
                float(self.config["budget_limit"]), 1.0
            )
        robust_residuals = dict(residuals)
        for constraint in self.config.get("uncertain_service_constraints", []):
            kpi = constraint["kpi"]
            if constraint["direction"] == "minimum":
                residuals[f"uncertain_service__{constraint['name']}"] = (
                    float(constraint["threshold"]) - prediction[f"prediction__{kpi}"]
                )
                robust_residuals[f"uncertain_service__{constraint['name']}"] = (
                    float(constraint["threshold"]) - prediction[f"lower__{kpi}"]
                )
            else:
                residuals[f"uncertain_service__{constraint['name']}"] = (
                    prediction[f"prediction__{kpi}"] - float(constraint["threshold"])
                )
                robust_residuals[f"uncertain_service__{constraint['name']}"] = (
                    prediction[f"upper__{kpi}"] - float(constraint["threshold"])
                )
            scales[f"uncertain_service__{constraint['name']}"] = max(
                abs(float(constraint["threshold"])), 1.0
            )
        normalized = {
            name: (0.0 if float(value) <= 1e-9 else float(value) / scales[name])
            for name, value in residuals.items()
        }
        return residuals, robust_residuals, normalized

    def _objectives(self, prediction):
        benefits = {}
        scores = {}
        supported = {}
        targets = set(self.model.manifest["target_columns"])
        for family_name in OBJECTIVE_FAMILIES:
            family = self.config["objective_families"][family_name]
            components = family.get("components", [])
            usable = [item for item in components if item["kpi"] in targets]
            supported[family_name] = bool(usable)
            if not usable:
                if family["missing_kpi_policy"] == "error":
                    raise ProblemConfigurationError(f"missing KPI for {family_name}")
                benefits[family_name] = 0.0
                scores[family_name] = 0.0
                continue
            benefit = 0.0
            for component in usable:
                norm = component["normalization"]
                value = float(prediction[f"prediction__{component['kpi']}"])
                normalized = (value - float(norm["minimum"])) / (
                    float(norm["maximum"]) - float(norm["minimum"])
                )
                if component["direction"] == "minimize":
                    normalized = 1.0 - normalized
                benefit += float(component["weight"]) * normalized
            benefits[family_name] = benefit
            scores[family_name] = -benefit
        return benefits, scores, supported

    def evaluate(self, candidate: Sequence[float] | Mapping[str, float]):
        decoded, repaired, repair_actions = self.repair(candidate)
        features = self._model_features(repaired)
        predicted_frame = self.model.predict(pd.DataFrame([features]))
        prediction = predicted_frame.iloc[0].to_dict()
        raw_kpis = {
            target: float(prediction[f"prediction__{target}"])
            for target in self.model.manifest["target_columns"]
        }
        uncertainty = {
            target: {
                "lower": float(prediction[f"lower__{target}"]),
                "upper": float(prediction[f"upper__{target}"]),
            }
            for target in self.model.manifest["target_columns"]
        }
        benefits, scores, objective_supported = self._objectives(prediction)
        residuals, robust_residuals, normalized = self._constraints(repaired, prediction)
        nominal_feasible = all(value <= 1e-9 for value in residuals.values())
        robust_feasible = all(value <= 1e-9 for value in robust_residuals.values())
        uncertain = bool(self.config.get("uncertain_service_constraints"))
        if uncertain:
            probability = None
            probability_status = "unavailable_conformal_intervals_are_not_a_joint_probability_model"
        else:
            probability = 1.0 if nominal_feasible else 0.0
            probability_status = "deterministic_constraints_only"
        cost = self.allocation_cost(repaired)
        return EvaluationResult(
            decoded=decoded,
            repaired=repaired,
            repair_actions=repair_actions,
            model_features=features,
            raw_kpis=raw_kpis,
            uncertainty=uncertainty,
            objective_benefits=benefits,
            objective_scores=scores,
            objective_supported=objective_supported,
            constraint_residuals={name: float(value) for name, value in residuals.items()},
            normalized_constraint_violations=normalized,
            normalized_violation=float(sum(normalized.values())),
            nominal_feasible=nominal_feasible,
            robust_feasible=robust_feasible,
            estimated_probability_feasible=probability,
            feasibility_probability_status=probability_status,
            support_flags={
                "out_of_model_support": bool(prediction["out_of_support"]),
                "out_of_support_features": str(prediction["out_of_support_features"]),
                "unsupported_objective_families": [
                    name for name, is_supported in objective_supported.items() if not is_supported
                ],
            },
            cost=cost,
            budget_remaining=float(self.config["budget_limit"]) - cost,
            dea_efficiency=None,
            dea_status=self.config.get(
                "dea_reporting", "separate_not_applied_to_candidate_allocations"
            ),
        )


def evaluate(x, context, model):
    """Evaluate one candidate using a scenario context and a versioned model bundle."""
    return AllocationProblem(context, model).evaluate(x)
