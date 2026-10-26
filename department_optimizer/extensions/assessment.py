"""Assess whether source evidence supports Network DEA or multi-period planning."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _present(columns, candidates):
    return [name for name in candidates if name in columns]


def assess_extensions(frame, provenance, config):
    columns = set(frame.columns)
    network = config["required_network_dea"]
    longitudinal = config["required_multiperiod"]
    network_units = _present(columns, network["unit_identifier_candidates"])
    stage_links = _present(columns, network["stage_link_candidates"])
    period_columns = _present(columns, longitudinal["period_candidates"])
    longitudinal_units = _present(columns, longitudinal["unit_identifier_candidates"])
    synthetic = provenance["datasets"][0]["provenance"] == "synthetic"

    network_reasons = []
    if synthetic:
        network_reasons.append("rows are synthetic and not a documented comparable peer cohort")
    if not network_units:
        network_reasons.append("no documented department/institution unit identifier")
    if not stage_links:
        network_reasons.append("no observed intermediate stage-link variables")
    if len(frame) < int(network["minimum_comparable_units"]):
        network_reasons.append("insufficient comparable units")

    multiperiod_reasons = []
    if synthetic:
        multiperiod_reasons.append("rows are synthetic rather than observed longitudinal records")
    if not longitudinal_units:
        multiperiod_reasons.append("no stable department/institution identifier")
    if not period_columns:
        multiperiod_reasons.append("no period/year column")
    repeated_counts = None
    distinct_periods = 0
    if longitudinal_units and period_columns:
        unit, period = longitudinal_units[0], period_columns[0]
        repeated_counts = frame.groupby(unit)[period].nunique()
        distinct_periods = int(frame[period].nunique())
        if (repeated_counts < int(longitudinal["minimum_periods_per_unit"])).any():
            multiperiod_reasons.append("some units lack repeated periods")
        if distinct_periods < int(longitudinal["minimum_distinct_periods"]):
            multiperiod_reasons.append("insufficient distinct periods")

    return {
        "network_dea": {
            "status": "supported" if not network_reasons else "deferred_evidence_gap",
            "implementation_performed": False,
            "implementation_authorized_by_evidence": not network_reasons,
            "unit_identifier_columns": network_units,
            "stage_link_columns": stage_links,
            "reasons": network_reasons,
            "required_before_implementation": [
                "documented comparable DMUs",
                "observed stage inputs, intermediate links, and final outputs",
                "defensible stage-link assumptions without double counting",
            ],
        },
        "multi_period_planning": {
            "status": "supported" if not multiperiod_reasons else "deferred_evidence_gap",
            "implementation_performed": False,
            "implementation_authorized_by_evidence": not multiperiod_reasons,
            "unit_identifier_columns": longitudinal_units,
            "period_columns": period_columns,
            "distinct_periods": distinct_periods,
            "minimum_observed_periods_per_unit": (
                int(repeated_counts.min()) if repeated_counts is not None else 0
            ),
            "reasons": multiperiod_reasons,
            "required_before_implementation": [
                "stable departmental identifiers",
                "at least two ordered observed periods per unit",
                "documented carry-over resources and outcome time lags",
            ],
        },
    }


def run_assessment(config_path, output_root=None):
    config_path = Path(config_path)
    config = json.loads(config_path.read_text())
    data_path = Path(config["data_path"])
    provenance_path = Path(config["provenance_path"])
    frame = pd.read_csv(data_path)
    provenance = json.loads(provenance_path.read_text())
    assessment = assess_extensions(frame, provenance, config)
    output = Path(output_root or config["output_root"])
    output.mkdir(parents=True, exist_ok=True)
    payload = {
        "assessment_id": config["assessment_id"],
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_path": str(data_path),
        "data_sha256": _sha256(data_path),
        "provenance_path": str(provenance_path),
        "provenance_sha256": _sha256(provenance_path),
        "row_count": len(frame),
        "columns": list(frame.columns),
        "assessment": assessment,
    }
    (output / "assessment.json").write_text(json.dumps(payload, indent=2) + "\n")
    network = assessment["network_dea"]
    multiperiod = assessment["multi_period_planning"]
    lines = [
        "# Optional Network DEA and multi-period planning assessment",
        "",
        "The evidence gate was evaluated before implementing either extension.",
        "",
        f"## Network DEA: `{network['status']}`",
        "",
    ]
    lines.extend(f"- {reason}" for reason in network["reasons"])
    lines += [
        "",
        "Network DEA was not implemented because the data contain no observed intermediate stage links and do not represent a documented comparable peer cohort. Creating stage links from the existing cross-sectional synthetic columns would add unsupported assumptions.",
        "",
        f"## Multi-period planning: `{multiperiod['status']}`",
        "",
    ]
    lines.extend(f"- {reason}" for reason in multiperiod["reasons"])
    lines += [
        "",
        "Multi-period optimization was not implemented because there are no period identifiers, repeated units, observed carry-over resources, or defensible time-lag estimates. Replicating a single synthetic cross-section would not create longitudinal evidence.",
        "",
        "## Evidence needed to resume",
        "",
        "For Network DEA, collect comparable units with stage-specific inputs, observed intermediate links, final outputs, and an agreed treatment of shared resources. For multi-period planning, collect repeated departmental periods with stable identifiers, per-period constraints, carry-over resources, and documented outcome lags.",
    ]
    (output / "assessment_report.md").write_text("\n".join(lines) + "\n")
    return output, assessment


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default="configs/extensions/evidence_assessment.json"
    )
    parser.add_argument("--output-root")
    return parser.parse_args()


def main():
    args = parse_args()
    output, assessment = run_assessment(
        Path(args.config), Path(args.output_root) if args.output_root else None
    )
    print(
        f"Extension evidence assessment: Network DEA={assessment['network_dea']['status']}, "
        f"multi-period={assessment['multi_period_planning']['status']}; {output}"
    )


if __name__ == "__main__":
    main()
