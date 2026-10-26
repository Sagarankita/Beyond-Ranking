"""Run a configured DEA benchmark and write reproducible artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from department_optimizer.data.schemas import get_schema
from department_optimizer.data.validation import validate_dataframe

from .dea import DEAConfig, run_input_vrs_dea


def _sha256(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _derive_columns(frame: pd.DataFrame, names: list[str]):
    result = frame.copy()
    supported = {"research_fte"}
    unknown = sorted(set(names).difference(supported))
    if unknown:
        raise ValueError(f"unsupported derived DEA columns: {unknown}")
    if "research_fte" in names:
        required = {
            "faculty_phd",
            "faculty_other",
            "frac_research_phd",
            "frac_research_other",
        }
        missing = sorted(required.difference(result.columns))
        if missing:
            raise ValueError(f"cannot derive research_fte; missing {missing}")
        result["research_fte"] = (
            result["faculty_phd"] * result["frac_research_phd"]
            + result["faculty_other"] * result["frac_research_other"]
        )
    return result


def run_configured_dea(config_path: Path, output_dir: Path):
    raw_config = json.loads(config_path.read_text())
    if raw_config.get("orientation") != "input":
        raise ValueError("Prompt 04 runner currently supports orientation='input' only")
    if raw_config.get("returns_to_scale") != "variable":
        raise ValueError("Prompt 04 runner currently supports returns_to_scale='variable' only")
    data_path = Path(raw_config["data_path"])
    source = pd.read_csv(data_path)
    schema = get_schema(raw_config["data_schema"])
    validation = validate_dataframe(source, schema)
    if validation.has_errors:
        raise ValueError(f"source data failed Phase 1 validation: {validation.to_dict()}")
    frame = _derive_columns(source, raw_config.get("derived_columns", []))
    model_config = DEAConfig(
        dmu_column=raw_config["dmu_column"],
        input_columns=tuple(raw_config["input_columns"]),
        output_columns=tuple(raw_config["output_columns"]),
        cohort_name=raw_config["cohort_name"],
        cohort_columns=tuple(raw_config.get("cohort_columns", [])),
    )
    analysis = run_input_vrs_dea(frame, model_config)
    summary = {
        **analysis.summary,
        "analysis_id": raw_config["analysis_id"],
        "data_path": str(data_path),
        "data_sha256": _sha256(data_path),
        "config_path": str(config_path),
        "config_sha256": _sha256(config_path),
        "data_schema": raw_config["data_schema"],
        "cohort_status": raw_config["cohort_status"],
        "evidence_status": raw_config["evidence_status"],
        "assumptions": raw_config["assumptions"],
        "network_dea_status": "deferred: no observed intermediate production-stage/linking data are present",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis.efficiency.to_csv(output_dir / "efficiency.csv", index=False)
    analysis.peers.to_csv(output_dir / "peers.csv", index=False)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    explanation_header = [
        "# DEA peer-gap explanations",
        "",
        "These are relative synthetic-fixture comparisons, not causal or empirical recommendations.",
        "Input gaps compare each row with the convex peer target returned by the VRS model.",
        "",
    ]
    (output_dir / "peer_gap_explanations.md").write_text(
        "\n".join(explanation_header + analysis.explanations) + "\n"
    )
    return analysis, summary


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default="configs/dea/legacy_synthetic_method_fixture.json"
    )
    parser.add_argument("--output-dir", default="artifacts/dea/legacy_synthetic")
    return parser.parse_args()


def main():
    args = parse_args()
    analysis, summary = run_configured_dea(Path(args.config), Path(args.output_dir))
    print(
        f"DEA complete: {summary['successful_solves']}/{summary['dmu_count']} solves; "
        f"{summary['strongly_efficient_count']} strongly efficient"
    )
    print(f"Evidence status: {summary['evidence_status']}")
    if summary["discrimination_warnings"]:
        for warning in summary["discrimination_warnings"]:
            print(f"Discrimination warning: {warning}")
    print(f"Outputs: {args.output_dir}")


if __name__ == "__main__":
    main()
