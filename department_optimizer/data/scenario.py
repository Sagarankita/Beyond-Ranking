"""Scenario configuration loading, validation, bounds, and cost accounting."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from .validation import ValidationReport


ALLOCATION_SEMANTICS = {"total", "incremental"}
COST_MODES = {"direct_money", "unit_cost", "non_monetary"}
VARIABLE_TYPES = {"continuous", "integer"}


def load_scenario(path: str | Path):
    return json.loads(Path(path).read_text())


def validate_scenario_config(config: Mapping[str, Any]) -> ValidationReport:
    report = ValidationReport("scenario_config", 1)
    required = {
        "schema_version",
        "scenario_id",
        "period_start",
        "period_end",
        "allocation_semantics",
        "currency",
        "currency_base_year",
        "budget_limit",
        "faculty_time_capacity_fte",
        "decision_variables",
        "service_thresholds",
    }
    missing = sorted(required.difference(config))
    if missing:
        report.add("error", "missing_scenario_fields", f"missing fields: {missing}", missing)
        return report

    semantics = config["allocation_semantics"]
    if semantics not in ALLOCATION_SEMANTICS:
        report.add(
            "error",
            "invalid_allocation_semantics",
            f"allocation_semantics must be one of {sorted(ALLOCATION_SEMANTICS)}",
            ("allocation_semantics",),
        )
    if semantics == "incremental" and not config.get("baseline_reference"):
        report.add(
            "error",
            "missing_baseline_reference",
            "incremental scenarios require baseline_reference",
            ("baseline_reference",),
        )
    if config["currency"] != "INR":
        report.add(
            "error",
            "unsupported_currency_unit",
            "the current scenario contract requires currency='INR'",
            ("currency",),
        )
    try:
        period_start = date.fromisoformat(config["period_start"])
        period_end = date.fromisoformat(config["period_end"])
        if period_start > period_end:
            raise ValueError
    except (TypeError, ValueError):
        report.add(
            "error",
            "invalid_scenario_period",
            "period_start and period_end must be ordered ISO-8601 dates",
            ("period_start", "period_end"),
        )
    if not isinstance(config["currency_base_year"], int) or config["currency_base_year"] < 2000:
        report.add(
            "error",
            "invalid_currency_base_year",
            "currency_base_year must be an integer year of at least 2000",
            ("currency_base_year",),
        )
    for name in ("budget_limit", "faculty_time_capacity_fte"):
        value = config[name]
        if not isinstance(value, (int, float)) or value < 0:
            report.add("error", "invalid_capacity", f"{name} must be non-negative", (name,))

    variables = config["decision_variables"]
    if not isinstance(variables, list) or not variables:
        report.add(
            "error",
            "missing_decision_variables",
            "decision_variables must be a non-empty list",
            ("decision_variables",),
        )
        return report

    names = [variable.get("name") for variable in variables]
    duplicates = sorted({name for name in names if name and names.count(name) > 1})
    if duplicates:
        report.add(
            "error",
            "duplicate_decision_variable",
            f"decision variable names must be unique: {duplicates}",
            tuple(duplicates),
        )
    cost_keys: dict[str, str] = {}
    variable_map = {}
    minimum_monetary_cost = 0.0
    minimum_faculty_effort = 0.0
    for variable in variables:
        name = variable.get("name", "<unnamed>")
        if name != "<unnamed>":
            variable_map[name] = variable
        required_variable = {"name", "unit", "type", "lower", "upper", "increment", "cost_mode"}
        absent = sorted(required_variable.difference(variable))
        if absent:
            report.add(
                "error",
                "incomplete_decision_variable",
                f"{name} is missing {absent}",
                (name,),
            )
            continue
        if variable["type"] not in VARIABLE_TYPES:
            report.add("error", "invalid_variable_type", f"invalid type for {name}", (name,))
        if variable["cost_mode"] not in COST_MODES:
            report.add("error", "invalid_cost_mode", f"invalid cost_mode for {name}", (name,))
            continue
        lower, upper, increment = variable["lower"], variable["upper"], variable["increment"]
        if not all(isinstance(value, (int, float)) for value in (lower, upper, increment)):
            report.add("error", "invalid_variable_bounds", f"numeric bounds required for {name}", (name,))
        elif lower > upper or increment <= 0:
            report.add("error", "invalid_variable_bounds", f"invalid bounds/increment for {name}", (name,))
        elif variable["type"] == "integer" and any(float(value) % 1 for value in (lower, upper, increment)):
            report.add("error", "invalid_integer_increment", f"integer variable {name} needs whole-number bounds/increment", (name,))

        mode = variable["cost_mode"]
        unit_cost = variable.get("unit_cost")
        if mode == "direct_money":
            if variable["unit"] != "INR":
                report.add("error", "invalid_direct_money_unit", f"{name} must use INR", (name,))
            if unit_cost is not None:
                report.add(
                    "error",
                    "potential_double_count",
                    f"{name} is direct money and must not also define unit_cost",
                    (name,),
                )
        elif mode == "unit_cost":
            if not isinstance(unit_cost, (int, float)) or unit_cost <= 0:
                report.add("error", "missing_unit_cost", f"{name} needs a positive unit_cost", (name,))
        elif unit_cost is not None:
            report.add(
                "error",
                "potential_double_count",
                f"non-monetary {name} must not define unit_cost",
                (name,),
            )

        if mode in {"direct_money", "unit_cost"}:
            cost_key = variable.get("cost_key", name)
            if cost_key in cost_keys:
                report.add(
                    "error",
                    "potential_double_count",
                    f"{name} and {cost_keys[cost_key]} share cost_key {cost_key}",
                    (name, cost_keys[cost_key]),
                )
            else:
                cost_keys[cost_key] = name
        if isinstance(lower, (int, float)):
            if mode == "direct_money":
                minimum_monetary_cost += float(lower)
            elif mode == "unit_cost" and isinstance(unit_cost, (int, float)):
                minimum_monetary_cost += float(lower) * float(unit_cost)
            if variable.get("unit") == "annual FTE":
                minimum_faculty_effort += float(lower)

    if isinstance(config["budget_limit"], (int, float)) and minimum_monetary_cost > float(config["budget_limit"]):
        report.add(
            "error",
            "infeasible_minimum_budget",
            "minimum decision-variable cost exceeds budget_limit",
            ("budget_limit",),
        )
    if isinstance(config["faculty_time_capacity_fte"], (int, float)) and minimum_faculty_effort > float(config["faculty_time_capacity_fte"]):
        report.add(
            "error",
            "infeasible_minimum_faculty_time",
            "minimum annual-FTE allocations exceed faculty_time_capacity_fte",
            ("faculty_time_capacity_fte",),
        )

    thresholds = config["service_thresholds"]
    if not isinstance(thresholds, list):
        report.add("error", "invalid_service_thresholds", "service_thresholds must be a list")
    else:
        for threshold in thresholds:
            if not {"name", "unit", "minimum"}.issubset(threshold):
                report.add(
                    "error",
                    "invalid_service_threshold",
                    "each service threshold needs name, unit, and minimum",
                )
                continue
            variable = variable_map.get(threshold["name"])
            if variable is None:
                report.add(
                    "error",
                    "unknown_service_variable",
                    f"service threshold references unknown variable {threshold['name']}",
                    (threshold["name"],),
                )
            elif threshold["unit"] != variable.get("unit"):
                report.add(
                    "error",
                    "service_unit_mismatch",
                    f"service threshold unit does not match {threshold['name']}",
                    (threshold["name"],),
                )
            elif not isinstance(threshold["minimum"], (int, float)) or not (
                variable["lower"] <= threshold["minimum"] <= variable["upper"]
            ):
                report.add(
                    "error",
                    "invalid_service_minimum",
                    f"service minimum is outside bounds for {threshold['name']}",
                    (threshold["name"],),
                )
    return report


def decision_bounds(config: Mapping[str, Any]):
    return {
        variable["name"]: (float(variable["lower"]), float(variable["upper"]))
        for variable in config["decision_variables"]
    }


def allocation_cost(allocation: Mapping[str, float], config: Mapping[str, Any]) -> float:
    report = validate_scenario_config(config)
    if report.has_errors:
        raise ValueError("cannot calculate cost from an invalid scenario configuration")
    total = 0.0
    for variable in config["decision_variables"]:
        value = float(allocation.get(variable["name"], 0.0))
        if variable["cost_mode"] == "direct_money":
            total += value
        elif variable["cost_mode"] == "unit_cost":
            total += value * float(variable["unit_cost"])
    return total
