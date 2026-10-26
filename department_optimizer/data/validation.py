"""Validation primitives that report issues without mutating source data."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .schemas import DatasetSchema


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    message: str
    columns: tuple[str, ...] = ()
    rows: tuple[Any, ...] = ()

    def to_dict(self):
        result = asdict(self)
        result["columns"] = list(self.columns)
        result["rows"] = [value.item() if hasattr(value, "item") else value for value in self.rows]
        return result


@dataclass
class ValidationReport:
    schema_name: str
    row_count: int
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def has_errors(self):
        return any(issue.severity == "error" for issue in self.issues)

    def add(self, severity, code, message, columns=(), rows=()):
        self.issues.append(
            ValidationIssue(severity, code, message, tuple(columns), tuple(rows))
        )

    def by_code(self, code):
        return [issue for issue in self.issues if issue.code == code]

    def to_dict(self):
        counts = {
            severity: sum(issue.severity == severity for issue in self.issues)
            for severity in ("error", "warning", "info")
        }
        return {
            "schema_name": self.schema_name,
            "row_count": self.row_count,
            "has_errors": self.has_errors,
            "issue_counts": counts,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _bad_rows(mask: pd.Series):
    return tuple(mask.index[mask].tolist()[:100])


def validate_dataframe(
    frame: pd.DataFrame,
    schema: DatasetSchema,
    scenario_bounds: Mapping[str, tuple[float, float]] | None = None,
) -> ValidationReport:
    """Validate by column name and report, never reorder, clip, coerce, or impute."""
    report = ValidationReport(schema.name, len(frame))
    field_map = schema.field_map
    missing = [name for name, spec in field_map.items() if spec.required and name not in frame]
    if missing:
        report.add(
            "error",
            "missing_required_columns",
            f"missing required columns: {missing}",
            columns=missing,
        )
    extras = [column for column in frame.columns if column not in field_map]
    if extras:
        severity = "info" if schema.allow_extra_columns else "error"
        report.add(
            severity,
            "extra_columns",
            f"columns are not defined by schema {schema.name}: {extras}",
            columns=extras,
        )

    available_key = [column for column in schema.primary_key if column in frame]
    if len(available_key) == len(schema.primary_key) and available_key:
        duplicate_mask = frame.duplicated(available_key, keep=False)
        if duplicate_mask.any():
            report.add(
                "error",
                "duplicate_primary_key",
                f"duplicate records for primary key {schema.primary_key}",
                columns=available_key,
                rows=_bad_rows(duplicate_mask),
            )
            if schema.source_column and schema.source_column in frame:
                grouped = frame.loc[duplicate_mask].groupby(available_key, dropna=False)[
                    schema.source_column
                ].nunique(dropna=True)
                conflicting = grouped[grouped > 1]
                if not conflicting.empty:
                    report.add(
                        "error",
                        "source_conflict",
                        "the same primary key has records from multiple sources",
                        columns=(*available_key, schema.source_column),
                        rows=tuple(str(value) for value in conflicting.index[:100]),
                    )

    for name, spec in field_map.items():
        if name not in frame:
            continue
        series = frame[name]
        missing_mask = series.isna()
        if missing_mask.any() and not spec.nullable:
            report.add(
                "error",
                "missing_values",
                f"{name} contains {int(missing_mask.sum())} missing values",
                columns=(name,),
                rows=_bad_rows(missing_mask),
            )
        present = series[~missing_mask]
        if present.empty:
            continue

        if spec.kind in {"number", "integer"}:
            numeric = pd.to_numeric(present, errors="coerce")
            invalid = numeric.isna()
            if invalid.any():
                report.add(
                    "error",
                    "non_numeric_values",
                    f"{name} contains values that are not numeric",
                    columns=(name,),
                    rows=_bad_rows(invalid),
                )
            valid = numeric[~invalid]
            finite = pd.Series(np.isfinite(valid.to_numpy(dtype=float)), index=valid.index)
            if (~finite).any():
                report.add(
                    "error",
                    "nonfinite_values",
                    f"{name} contains non-finite values",
                    columns=(name,),
                    rows=_bad_rows(~finite),
                )
            valid = valid[finite]
            if spec.kind == "integer" and not valid.empty:
                fractional = ~np.isclose(valid.to_numpy(dtype=float), np.rint(valid))
                if fractional.any():
                    mask = pd.Series(fractional, index=valid.index)
                    report.add(
                        "error",
                        "noninteger_counts",
                        f"{name} must contain whole-number counts",
                        columns=(name,),
                        rows=_bad_rows(mask),
                    )
            if spec.minimum is not None and (valid < spec.minimum).any():
                mask = valid < spec.minimum
                report.add(
                    "error",
                    "below_schema_minimum",
                    f"{name} contains values below {spec.minimum} {spec.unit}",
                    columns=(name,),
                    rows=_bad_rows(mask),
                )
            if spec.maximum is not None and (valid > spec.maximum).any():
                mask = valid > spec.maximum
                report.add(
                    "error",
                    "above_schema_maximum",
                    f"{name} contains values above {spec.maximum} {spec.unit}",
                    columns=(name,),
                    rows=_bad_rows(mask),
                )
        elif spec.kind == "boolean":
            invalid = ~present.map(lambda value: isinstance(value, (bool, np.bool_)))
            if invalid.any():
                report.add(
                    "error",
                    "invalid_boolean",
                    f"{name} must contain boolean values",
                    columns=(name,),
                    rows=_bad_rows(invalid),
                )
        elif spec.kind == "date":
            parsed = pd.to_datetime(present, errors="coerce")
            invalid = parsed.isna()
            if invalid.any():
                report.add(
                    "error",
                    "invalid_date",
                    f"{name} must contain ISO-compatible dates",
                    columns=(name,),
                    rows=_bad_rows(invalid),
                )
        elif spec.kind == "string":
            invalid = present.map(lambda value: not isinstance(value, str) or not value.strip())
            if invalid.any():
                report.add(
                    "error",
                    "invalid_string",
                    f"{name} must contain non-empty strings",
                    columns=(name,),
                    rows=_bad_rows(invalid),
                )

        if spec.allowed_values is not None:
            invalid = ~present.isin(spec.allowed_values)
            if invalid.any():
                report.add(
                    "error",
                    "invalid_unit_or_category",
                    f"{name} must be one of {list(spec.allowed_values)}",
                    columns=(name,),
                    rows=_bad_rows(invalid),
                )

    if scenario_bounds:
        for name, (lower, upper) in scenario_bounds.items():
            if name not in frame:
                continue
            original = frame[name].copy(deep=True)
            numeric = pd.to_numeric(frame[name], errors="coerce")
            outside = (numeric < lower) | (numeric > upper)
            if outside.any():
                report.add(
                    "warning",
                    "outside_scenario_bounds",
                    f"{int(outside.sum())} historical {name} values are outside scenario bounds [{lower}, {upper}]; values were not changed",
                    columns=(name,),
                    rows=_bad_rows(outside),
                )
            if not original.equals(frame[name]):
                raise AssertionError("validation must not mutate source data")
    return report
