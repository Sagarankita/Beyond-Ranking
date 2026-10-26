"""Shared-feasibility VJTI evaluator with four evidence-labeled objective families."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

import joblib
import numpy as np
import pandas as pd


FAMILIES = ("research", "innovation", "student_development", "societal_contribution")


class PublicAllocationConfigurationError(ValueError):
    """Raised before optimization when an objective or constraint is unsupported."""


@dataclass
class PublicAllocationResult:
    decoded: dict
    repaired: dict
    repair_actions: list[str]
    cost_components: dict
    total_cost: float
    budget_remaining: float
    model_features: dict
    raw_kpis: dict
    intervals: dict
    response_adjustments: dict
    score_components: dict
    objective_benefits: dict
    objective_scores: dict
    objective_evidence: dict
    support_flags: dict
    constraint_residuals: dict
    normalized_constraint_violations: dict
    normalized_violation: float
    feasible: bool
    synthetic_coverage: dict
    dea_status: str

    def to_dict(self):
        return asdict(self)

    def objective_vector(self):
        return np.asarray([self.objective_scores[name] for name in FAMILIES], dtype=float)

    @property
    def uncertainty(self):
        return self.intervals

    @property
    def nominal_feasible(self):
        return self.feasible

    @property
    def robust_feasible(self):
        # Service constraints already use conservative prediction-interval bounds.
        return self.feasible

    @property
    def cost(self):
        return self.total_cost


class EvidenceModelBundle:
    def __init__(self, root: Path):
        self.root = root
        self.manifest = json.loads((root / "model_manifest.json").read_text(encoding="utf-8"))
        self.models = {
            target: joblib.load(root / details["model_file"])
            for target, details in self.manifest["selected_models"].items()
        }

    def predict(self, features: dict):
        frame = pd.DataFrame([features], columns=self.manifest["feature_columns"])
        support = next(iter(self.manifest["training_support_by_target"].values()))
        outside = [name for name, value in features.items()
                   if name in support and not (support[name]["minimum"] <= value <= support[name]["maximum"])]
        predictions, intervals = {}, {}
        for target, model in self.models.items():
            value = max(0.0, float(model.predict(frame)[0]))
            radius = float(self.manifest["conformal_radii"][target])
            predictions[target] = value
            intervals[target] = {"lower": max(0.0, value - radius), "upper": value + radius,
                                 "radius": radius,
                                 "validation_type": "synthetic_generator_validation"}
        return predictions, intervals, outside


class VJTIPublicAllocationProblem:
    """Extends the shared allocation contract with the Prompt 15 model bundle."""

    def __init__(self, config: Mapping, model_root: str | Path):
        self.config = dict(config)
        self.variables = list(self.config["decision_variables"])
        self.names = [item["name"] for item in self.variables]
        self.variable_names = self.names
        self.model = EvidenceModelBundle(Path(model_root))
        self._validate()

    def _validate(self):
        if len(self.names) != len(set(self.names)) or not self.names:
            raise PublicAllocationConfigurationError("decision variables must be non-empty and unique")
        if self.config.get("allocation_semantics") != "totals":
            raise PublicAllocationConfigurationError("Prompt 16 requires allocation_semantics='totals'")
        currency = self.config.get("currency", {})
        if currency.get("code") != "INR" or not currency.get("base_year"):
            raise PublicAllocationConfigurationError("currency must be INR with an explicit base year")
        for variable in self.variables:
            required = {"name", "type", "unit", "lower", "upper", "increment", "cost_mode"}
            missing = required.difference(variable)
            if missing:
                raise PublicAllocationConfigurationError(f"{variable.get('name')} missing {sorted(missing)}")
            if variable["type"] not in {"continuous", "integer"}:
                raise PublicAllocationConfigurationError(f"unsupported type for {variable['name']}")
            if variable["lower"] > variable["upper"] or variable["increment"] <= 0:
                raise PublicAllocationConfigurationError(f"invalid bounds for {variable['name']}")
            if variable["cost_mode"] == "unit_cost" and variable.get("unit_cost", 0) <= 0:
                raise PublicAllocationConfigurationError(f"missing unit cost for {variable['name']}")
        families = self.config.get("objective_families", {})
        if set(families) != set(FAMILIES):
            raise PublicAllocationConfigurationError(f"objective families must be {FAMILIES}")
        targets = set(self.model.manifest["target_columns"])
        for family, details in families.items():
            if not details.get("enabled"):
                raise PublicAllocationConfigurationError(f"unsupported family {family} must fail before optimization")
            components = details.get("components", [])
            if not components or not np.isclose(sum(item["weight"] for item in components), 1.0):
                raise PublicAllocationConfigurationError(f"{family} weights must sum to one")
            for component in components:
                if component["kpi"] not in targets:
                    raise PublicAllocationConfigurationError(f"{family} requires unsupported KPI {component['kpi']}")
                bounds = component["normalization"]
                if bounds["maximum"] <= bounds["minimum"]:
                    raise PublicAllocationConfigurationError("normalization maximum must exceed minimum")

    @staticmethod
    def _snap(value, lower, increment):
        return lower + round((value - lower) / increment) * increment

    def decode(self, candidate):
        if isinstance(candidate, Mapping):
            missing, extra = sorted(set(self.names) - set(candidate)), sorted(set(candidate) - set(self.names))
            if missing or extra:
                raise ValueError(f"candidate keys mismatch; missing={missing}, extra={extra}")
            values = candidate
        else:
            if len(candidate) != len(self.names):
                raise ValueError(f"candidate has {len(candidate)} values; expected {len(self.names)}")
            values = dict(zip(self.names, candidate))
        decoded = {name: float(values[name]) for name in self.names}
        if not np.isfinite(list(decoded.values())).all():
            raise ValueError("candidate values must be finite")
        return decoded

    def cost_components(self, allocation):
        result = {}
        for variable in self.variables:
            value = allocation[variable["name"]]
            if variable["cost_mode"] == "direct_money":
                result[variable["name"]] = value * variable.get("cost_multiplier", 1.0)
            elif variable["cost_mode"] == "unit_cost":
                result[variable["name"]] = (
                    value * variable["unit_cost"] * variable.get("cost_multiplier", 1.0)
                )
            else:
                result[variable["name"]] = 0.0
        return result

    def total_cost(self, allocation):
        return float(sum(self.cost_components(allocation).values()))

    def repair(self, candidate):
        decoded = self.decode(candidate)
        repaired, actions = {}, []
        variable_map = {item["name"]: item for item in self.variables}
        for variable in self.variables:
            name = variable["name"]
            value = np.clip(decoded[name], variable["lower"], variable["upper"])
            value = self._snap(value, variable["lower"], variable["increment"])
            value = float(np.clip(value, variable["lower"], variable["upper"]))
            if variable["type"] == "integer":
                value = float(round(value))
            repaired[name] = value
            if not np.isclose(value, decoded[name]):
                actions.append(f"{name}: {decoded[name]:g} -> {value:g} (bounds/increment/type)")
        for dependency in self.config.get("dependencies", []):
            count = repaired[dependency["count_variable"]]
            funding_name = dependency["funding_variable"]
            needed = count * dependency["minimum_funding_per_unit"]
            if repaired[funding_name] < needed:
                old = repaired[funding_name]
                spec = variable_map[funding_name]
                repaired[funding_name] = min(spec["upper"], self._snap(needed, spec["lower"], spec["increment"]))
                actions.append(f"{funding_name}: {old:g} -> {repaired[funding_name]:g} ({dependency['name']})")
        budget = float(self.config["budget_limit"])
        for variable in sorted(self.variables, key=lambda item: item.get("repair_priority", 0)):
            name = variable["name"]
            while self.total_cost(repaired) > budget + 1e-6 and variable["cost_mode"] != "non_monetary" and repaired[name] > variable["lower"]:
                old = repaired[name]
                repaired[name] = max(variable["lower"], repaired[name] - variable["increment"])
                if variable["type"] == "integer":
                    repaired[name] = float(round(repaired[name]))
                if not np.isclose(old, repaired[name]):
                    actions.append(f"{name}: {old:g} -> {repaired[name]:g} (budget)")
        return decoded, repaired, actions

    def _features(self, allocation):
        research_budget = sum(allocation[name] for name in self.config["model_mapping"]["research_budget_components"])
        context = self.config["fixed_context"]
        return {
            "research_budget": research_budget,
            "lagged_research_budget": context["lagged_research_budget"],
            "faculty_research_fte": allocation["research_faculty_effort"],
            "faculty_phd": context["faculty_phd"],
            "student_count": context["student_count"],
            "teaching_load_per_faculty": context["teaching_load_per_faculty"],
        }

    def _adjust(self, allocation, predictions, intervals):
        response = self.config["synthetic_response_adjustments"]
        baseline = self.config["reference_allocation"]
        changes = {name: allocation[name] - baseline[name] for name in self.names}
        adjustments = {
            "patent_applications": changes["patent_ip_support"] * response["patents_per_inr"] + changes["compute_capacity_units"] * response["patents_per_compute_unit"],
            "industry_projects": changes["industry_collaboration_funding"] * response["industry_projects_per_inr"],
            "student_research_participants": changes["student_research_funding"] * response["participants_per_inr"] + changes["student_support_faculty_effort"] * response["participants_per_student_support_fte"],
            "placements": changes["student_research_funding"] * response["placements_per_inr"],
            "higher_studies": changes["student_research_funding"] * response["higher_studies_per_inr"],
            "open_access_publications": changes["open_access_funding"] * response["open_access_per_inr"],
            "outreach_participants": changes["outreach_sdg_funding"] * response["outreach_per_inr"] + changes["service_faculty_effort"] * response["outreach_per_service_fte"],
        }
        for kpi, delta in adjustments.items():
            predictions[kpi] = max(0.0, predictions[kpi] + delta)
            intervals[kpi]["lower"] = max(0.0, intervals[kpi]["lower"] + delta)
            intervals[kpi]["upper"] = max(intervals[kpi]["lower"], intervals[kpi]["upper"] + delta)
        return adjustments

    def _constraints(self, allocation, intervals):
        residuals, scales = {}, {}
        for variable in self.variables:
            name, value = variable["name"], allocation[variable["name"]]
            residuals[f"bounds__{name}"] = max(variable["lower"] - value, value - variable["upper"], 0.0)
            scales[f"bounds__{name}"] = max(variable["upper"] - variable["lower"], 1.0)
            residuals[f"increment__{name}"] = abs((value - variable["lower"]) / variable["increment"] - round((value - variable["lower"]) / variable["increment"])) * variable["increment"]
            scales[f"increment__{name}"] = variable["increment"]
            if variable["type"] == "integer":
                residuals[f"integrality__{name}"] = abs(value - round(value))
                scales[f"integrality__{name}"] = 1.0
        total = self.total_cost(allocation)
        residuals["budget"] = max(0.0, total - self.config["budget_limit"])
        scales["budget"] = self.config["budget_limit"]
        effort_names = ["research_faculty_effort", "student_support_faculty_effort", "service_faculty_effort"]
        allocated_effort = sum(allocation[name] for name in effort_names)
        available = self.config["fixed_context"]["faculty_total"] - self.config["service_commitments"]["minimum_teaching_fte"]
        residuals["faculty_effort_conservation"] = max(0.0, allocated_effort - available)
        scales["faculty_effort_conservation"] = available
        for name, minimum in (("student_support_faculty_effort", self.config["service_commitments"]["minimum_student_support_fte"]),
                              ("service_faculty_effort", self.config["service_commitments"]["minimum_service_fte"])):
            residuals[f"service_floor__{name}"] = max(0.0, minimum - allocation[name])
            scales[f"service_floor__{name}"] = max(minimum, 1.0)
        for dependency in self.config.get("dependencies", []):
            required = allocation[dependency["count_variable"]] * dependency["minimum_funding_per_unit"]
            residuals[f"dependency__{dependency['name']}"] = max(0.0, required - allocation[dependency["funding_variable"]])
            scales[f"dependency__{dependency['name']}"] = max(required, 1.0)
        for service in self.config.get("conservative_kpi_services", []):
            residuals[f"service_kpi__{service['kpi']}"] = max(0.0, service["minimum_lower_bound"] - intervals[service["kpi"]]["lower"])
            scales[f"service_kpi__{service['kpi']}"] = max(service["minimum_lower_bound"], 1.0)
        normalized = {name: max(0.0, value) / scales[name] for name, value in residuals.items()}
        return residuals, normalized

    def _evaluate_allocation(self, decoded, repaired, actions):
        features = self._features(repaired)
        predictions, intervals, outside = self.model.predict(features)
        adjustments = self._adjust(repaired, predictions, intervals)
        score_components, benefits, scores, evidence = {}, {}, {}, {}
        for family, details in self.config["objective_families"].items():
            benefit = 0.0
            score_components[family] = []
            labels = []
            for component in details["components"]:
                value = predictions[component["kpi"]]
                norm = component["normalization"]
                normalized = float(np.clip((value - norm["minimum"]) / (norm["maximum"] - norm["minimum"]), 0, 1))
                weighted = normalized * component["weight"]
                benefit += weighted
                labels.append(component["evidence_label"])
                score_components[family].append({"kpi": component["kpi"], "raw_value": value,
                                                  "normalized_value": normalized,
                                                  "weight": component["weight"],
                                                  "weighted_benefit": weighted,
                                                  "evidence_label": component["evidence_label"]})
            benefits[family], scores[family] = benefit, -benefit
            evidence[family] = "synthetic_scenario" if "synthetic_scenario" in labels else "public_descriptive"
        residuals, normalized = self._constraints(repaired, intervals)
        coverage = {family: float(np.mean([item["evidence_label"] == "synthetic_scenario" for item in components]))
                    for family, components in score_components.items()}
        return PublicAllocationResult(
            decoded, repaired, actions, self.cost_components(repaired), self.total_cost(repaired),
            self.config["budget_limit"] - self.total_cost(repaired), features, predictions,
            intervals, adjustments, score_components, benefits, scores, evidence,
            {"out_of_support": bool(outside), "out_of_model_support": bool(outside),
             "out_of_support_features": outside,
             "extrapolation_rule": self.config["extrapolation_rule"]},
            residuals, normalized, float(sum(normalized.values())),
            bool(all(value <= 1e-9 for value in residuals.values())), coverage,
            "DEA retained as descriptive context only; not used as a causal multiplier",
        )

    def evaluate(self, candidate):
        decoded, repaired, actions = self.repair(candidate)
        return self._evaluate_allocation(decoded, repaired, actions)

    def evaluate_fixed(self, candidate):
        """Evaluate an unchanged strategy under a scenario, without repair or reoptimization."""
        decoded = self.decode(candidate)
        return self._evaluate_allocation(decoded, dict(decoded), [])
