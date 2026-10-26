"""Input-oriented variable-returns-to-scale DEA using linear programming."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd


class DEADataError(ValueError):
    """Raised when a cohort cannot support the configured DEA model."""


@dataclass(frozen=True)
class DEAConfig:
    dmu_column: str
    input_columns: tuple[str, ...]
    output_columns: tuple[str, ...]
    cohort_name: str
    cohort_columns: tuple[str, ...] = ()
    peer_tolerance: float = 1e-7
    efficiency_tolerance: float = 1e-7

    def __post_init__(self):
        if not self.dmu_column:
            raise ValueError("dmu_column is required")
        if not self.input_columns or not self.output_columns:
            raise ValueError("DEA needs at least one input and one output")
        if not self.cohort_name:
            raise ValueError("cohort_name is required")
        selected = (*self.input_columns, *self.output_columns)
        if len(set(selected)) != len(selected):
            raise ValueError("input and output columns must be distinct")


@dataclass
class DEAAnalysis:
    efficiency: pd.DataFrame
    peers: pd.DataFrame
    summary: dict
    explanations: list[str]


def _linprog():
    try:
        from scipy.optimize import linprog
    except ImportError as exc:
        raise RuntimeError(
            "SciPy is required for DEA. Install project requirements with "
            "`pip install -r requirements.txt`."
        ) from exc
    return linprog


def _validate_cohort(frame: pd.DataFrame, config: DEAConfig):
    required = {
        config.dmu_column,
        *config.input_columns,
        *config.output_columns,
        *config.cohort_columns,
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise DEADataError(f"missing DEA columns: {missing}")
    if len(frame) < 2:
        raise DEADataError("DEA requires at least two decision-making units")
    if frame[config.dmu_column].isna().any():
        raise DEADataError("DMU identifiers must not be missing")
    duplicates = frame[config.dmu_column].duplicated(keep=False)
    if duplicates.any():
        values = frame.loc[duplicates, config.dmu_column].astype(str).unique().tolist()
        raise DEADataError(f"DMU identifiers must be unique; duplicates: {values[:10]}")
    if config.cohort_columns:
        cohort_count = frame[list(config.cohort_columns)].drop_duplicates().shape[0]
        if cohort_count != 1:
            raise DEADataError(
                f"incomparable cohort: {cohort_count} combinations found across "
                f"{list(config.cohort_columns)}; filter to one cohort before DEA"
            )

    selected = [*config.input_columns, *config.output_columns]
    numeric = frame[selected].apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any():
        bad = numeric.columns[numeric.isna().any()].tolist()
        raise DEADataError(f"DEA variables contain missing or non-numeric values: {bad}")
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        bad = numeric.columns[
            ~np.isfinite(numeric.to_numpy(dtype=float)).all(axis=0)
        ].tolist()
        raise DEADataError(f"DEA variables contain non-finite values: {bad}")

    inputs = numeric[list(config.input_columns)]
    outputs = numeric[list(config.output_columns)]
    if (inputs <= 0).any().any():
        bad = inputs.columns[(inputs <= 0).any()].tolist()
        raise DEADataError(
            f"input-oriented radial DEA requires strictly positive inputs; invalid: {bad}"
        )
    if (outputs < 0).any().any():
        bad = outputs.columns[(outputs < 0).any()].tolist()
        raise DEADataError(f"DEA outputs must be non-negative: {bad}")
    zero_output_rows = outputs.sum(axis=1) <= 0
    if zero_output_rows.any():
        dmus = frame.loc[zero_output_rows, config.dmu_column].astype(str).tolist()
        raise DEADataError(f"each DMU needs at least one positive output; invalid: {dmus[:10]}")
    constant = [column for column in selected if numeric[column].nunique() <= 1]
    if constant:
        raise DEADataError(
            f"constant DEA variables provide no discrimination and must be removed: {constant}"
        )
    return numeric


def _positive_scale(values: np.ndarray):
    median = float(np.median(values[values > 0]))
    return median if np.isfinite(median) and median > 0 else 1.0


def _solve_one(inputs, outputs, evaluated_index, config, linprog):
    count, input_count = inputs.shape
    output_count = outputs.shape[1]
    objective = np.zeros(count + 1)
    objective[-1] = 1.0

    input_constraints = np.column_stack(
        [inputs.T, -inputs[evaluated_index].reshape(input_count, 1)]
    )
    output_constraints = np.column_stack(
        [-outputs.T, np.zeros((output_count, 1))]
    )
    a_ub = np.vstack([input_constraints, output_constraints])
    b_ub = np.concatenate(
        [np.zeros(input_count), -outputs[evaluated_index]]
    )
    a_eq = np.concatenate([np.ones(count), [0.0]]).reshape(1, -1)
    result = linprog(
        objective,
        A_ub=a_ub,
        b_ub=b_ub,
        A_eq=a_eq,
        b_eq=np.array([1.0]),
        bounds=[(0.0, None)] * count + [(0.0, 1.0)],
        method="highs",
    )
    return result


def run_input_vrs_dea(frame: pd.DataFrame, config: DEAConfig) -> DEAAnalysis:
    """Run the input-oriented BCC/VRS envelopment model for one comparable cohort."""
    numeric = _validate_cohort(frame, config)
    linprog = _linprog()
    raw_inputs = numeric[list(config.input_columns)].to_numpy(dtype=float)
    raw_outputs = numeric[list(config.output_columns)].to_numpy(dtype=float)
    input_scales = np.array([_positive_scale(raw_inputs[:, i]) for i in range(raw_inputs.shape[1])])
    output_scales = np.array([_positive_scale(raw_outputs[:, i]) for i in range(raw_outputs.shape[1])])
    inputs = raw_inputs / input_scales
    outputs = raw_outputs / output_scales
    dmus = frame[config.dmu_column].astype(str).tolist()

    records = []
    peer_records = []
    explanations = []
    for evaluated_index, dmu in enumerate(dmus):
        solved = _solve_one(inputs, outputs, evaluated_index, config, linprog)
        base = {
            config.dmu_column: dmu,
            "cohort_name": config.cohort_name,
            "solver_status_code": int(solved.status),
            "solver_status": "optimal" if solved.success else "failed",
            "solver_message": str(solved.message),
            "solver_iterations": int(getattr(solved, "nit", 0)),
        }
        if not solved.success:
            base.update(
                efficiency_score=np.nan,
                radial_input_reduction=np.nan,
                radially_efficient=False,
                strongly_efficient=False,
                peer_count=0,
            )
            records.append(base)
            explanations.append(f"- **{dmu}:** solver failed: {solved.message}")
            continue

        lambdas = np.asarray(solved.x[:-1], dtype=float)
        theta = float(np.clip(solved.x[-1], 0.0, 1.0))
        reference_inputs = lambdas @ raw_inputs
        reference_outputs = lambdas @ raw_outputs
        input_close = (
            np.abs(reference_inputs - raw_inputs[evaluated_index])
            <= input_scales * config.efficiency_tolerance
        )
        output_close = (
            np.abs(reference_outputs - raw_outputs[evaluated_index])
            <= output_scales * config.efficiency_tolerance
        )
        reference_inputs[input_close] = raw_inputs[evaluated_index][input_close]
        reference_outputs[output_close] = raw_outputs[evaluated_index][output_close]
        radial_targets = theta * raw_inputs[evaluated_index]
        input_slacks = np.maximum(radial_targets - reference_inputs, 0.0)
        output_slacks = np.maximum(reference_outputs - raw_outputs[evaluated_index], 0.0)
        input_slacks[input_slacks < input_scales * config.efficiency_tolerance] = 0.0
        output_slacks[output_slacks < output_scales * config.efficiency_tolerance] = 0.0
        peers = np.flatnonzero(lambdas > config.peer_tolerance)
        radial_efficiency = theta >= 1.0 - config.efficiency_tolerance
        strong_efficiency = bool(
            radial_efficiency
            and np.all(input_slacks / input_scales <= config.efficiency_tolerance)
            and np.all(output_slacks / output_scales <= config.efficiency_tolerance)
        )
        base.update(
            efficiency_score=theta,
            radial_input_reduction=max(0.0, 1.0 - theta),
            radially_efficient=bool(radial_efficiency),
            strongly_efficient=strong_efficiency,
            peer_count=int(len(peers)),
        )
        for position, column in enumerate(config.input_columns):
            original = raw_inputs[evaluated_index, position]
            target = reference_inputs[position]
            base[f"input__{column}"] = original
            base[f"target_input__{column}"] = target
            base[f"input_slack__{column}"] = input_slacks[position]
            base[f"input_reduction_pct__{column}"] = max(0.0, (original - target) / original)
        for position, column in enumerate(config.output_columns):
            original = raw_outputs[evaluated_index, position]
            target = reference_outputs[position]
            base[f"output__{column}"] = original
            base[f"target_output__{column}"] = target
            base[f"output_slack__{column}"] = output_slacks[position]
            base[f"output_expansion_pct__{column}"] = (
                max(0.0, (target - original) / original) if original > 0 else np.nan
            )
        records.append(base)
        peer_labels = []
        for peer_index in peers:
            peer_records.append(
                {
                    "evaluated_dmu": dmu,
                    "peer_dmu": dmus[peer_index],
                    "lambda_weight": float(lambdas[peer_index]),
                }
            )
            peer_labels.append(f"{dmus[peer_index]} ({lambdas[peer_index]:.3f})")
        largest_gaps = sorted(
            (
                (
                    column,
                    max(
                        0.0,
                        float(
                            (raw_inputs[evaluated_index, p] - reference_inputs[p])
                            / raw_inputs[evaluated_index, p]
                        ),
                    ),
                )
                for p, column in enumerate(config.input_columns)
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        gap_text = ", ".join(f"{name}: {value:.1%}" for name, value in largest_gaps)
        explanations.append(
            f"- **{dmu}:** efficiency {theta:.4f}; modeled input gaps [{gap_text}]; "
            f"reference peers: {', '.join(peer_labels) or 'none'}."
        )

    efficiency = pd.DataFrame(records)
    peers = pd.DataFrame(
        peer_records, columns=["evaluated_dmu", "peer_dmu", "lambda_weight"]
    )
    successful = efficiency[efficiency["solver_status"] == "optimal"]
    input_count = len(config.input_columns)
    output_count = len(config.output_columns)
    heuristic_minimum = max(3 * (input_count + output_count), input_count * output_count)
    efficient_share = (
        float(successful["strongly_efficient"].mean()) if len(successful) else None
    )
    warnings = []
    if len(frame) < heuristic_minimum:
        warnings.append(
            f"cohort has {len(frame)} DMUs; heuristic minimum is {heuristic_minimum} "
            f"for {input_count} inputs and {output_count} outputs"
        )
    if efficient_share is not None and efficient_share > 0.30:
        warnings.append(
            f"{efficient_share:.1%} of solved DMUs are strongly efficient; discrimination may be weak"
        )
    duplicate_profiles = int(
        numeric[[*config.input_columns, *config.output_columns]].duplicated(keep=False).sum()
    )
    if duplicate_profiles:
        warnings.append(f"{duplicate_profiles} DMUs share duplicate input/output profiles")
    summary = {
        "model": "input-oriented variable-returns-to-scale DEA (BCC envelopment)",
        "cohort_name": config.cohort_name,
        "dmu_count": len(frame),
        "input_columns": list(config.input_columns),
        "output_columns": list(config.output_columns),
        "input_scaling_factors": dict(zip(config.input_columns, input_scales.tolist())),
        "output_scaling_factors": dict(zip(config.output_columns, output_scales.tolist())),
        "successful_solves": int(len(successful)),
        "failed_solves": int(len(efficiency) - len(successful)),
        "strongly_efficient_count": int(successful["strongly_efficient"].sum()) if len(successful) else 0,
        "radially_efficient_count": int(successful["radially_efficient"].sum()) if len(successful) else 0,
        "strongly_efficient_share": efficient_share,
        "efficiency_score_summary": (
            {
                "minimum": float(successful["efficiency_score"].min()),
                "median": float(successful["efficiency_score"].median()),
                "mean": float(successful["efficiency_score"].mean()),
                "maximum": float(successful["efficiency_score"].max()),
            }
            if len(successful)
            else None
        ),
        "discrimination_heuristic_minimum_dmus": heuristic_minimum,
        "discrimination_warnings": warnings,
        "interpretation": "Efficiency is relative to this cohort and selected variables; it is not causal evidence or an outcome multiplier.",
    }
    return DEAAnalysis(efficiency, peers, summary, explanations)
