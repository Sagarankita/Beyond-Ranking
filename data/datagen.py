"""Generate the explicitly synthetic legacy research fixture without import side effects."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


GENERATOR_VERSION = "legacy-research-v1"
RESPONSE_MODEL_ID = "legacy-hand-authored-response-v1"


def response_model_assumptions():
    return {
        "research_fte": "faculty_phd * frac_research_phd + faculty_other * frac_research_other",
        "papers_t1": "0.05 * research_fte + 0.000002 * research_budget + 0.8 * centres - 0.3 * teaching_load + Normal(0, 2), clipped at zero and converted to integer",
        "citation_percentile_avg": "0.5 + 0.05 * centres/10 + 0.1 * (diversity-0.5) + 0.05 * log10(budget/1e5) - 0.02 * teaching_load/15, clipped to [0,1]",
        "overall_rank": "1000/(1+papers_t1) + 100*(1-citation_percentile_avg) + Uniform(0,50), converted to integer",
        "unsupported_outcomes": [
            "patents",
            "technology transfer",
            "student research outcomes",
            "placements",
            "higher studies",
            "open access outcomes",
            "SDG/outreach outcomes",
        ],
    }


def generate_legacy_synthetic(
    n_records: int = 521,
    seed: int = 42,
    include_metadata: bool = True,
    scenario_id: str = "legacy-synthetic-research-v1",
    period_start: str = "2025-07-01",
    period_end: str = "2026-06-30",
) -> pd.DataFrame:
    if n_records < 1:
        raise ValueError("n_records must be positive")
    if seed < 0:
        raise ValueError("seed must be non-negative")

    # RandomState intentionally preserves the exact NumPy sequence used by the
    # original np.random.seed(42) script and therefore the committed fixture.
    rng = np.random.RandomState(seed)
    faculty_phd = rng.randint(10, 150, n_records)
    faculty_other = rng.randint(5, 80, n_records)
    frac_research_phd = rng.uniform(0.3, 0.8, n_records)
    frac_research_other = rng.uniform(0.1, 0.5, n_records)
    research_budget = 10 ** rng.uniform(5, 9, n_records)
    centres = rng.randint(0, 10, n_records)
    teaching_load = rng.uniform(6, 16, n_records)
    diversity_index = rng.uniform(0.2, 1.0, n_records)
    industry_collaborations = rng.randint(0, 15, n_records)
    student_count = rng.randint(200, 2500, n_records)
    num_courses = rng.randint(10, 120, n_records)
    research_fte = (
        faculty_phd * frac_research_phd + faculty_other * frac_research_other
    )
    papers_t1 = (
        0.05 * research_fte
        + 0.000002 * research_budget
        + 0.8 * centres
        - 0.3 * teaching_load
        + rng.normal(0, 2, n_records)
    )
    papers_t1 = np.clip(papers_t1, 0, None).astype(int)
    citation_percentile = (
        0.5
        + 0.05 * (centres / 10)
        + 0.1 * (diversity_index - 0.5)
        + 0.05 * np.log10(research_budget / 1e5)
        - 0.02 * (teaching_load / 15)
    )
    citation_percentile = np.clip(citation_percentile, 0, 1)
    overall_rank = (
        1000 / (1 + papers_t1)
        + 100 * (1 - citation_percentile)
        + rng.uniform(0, 50, n_records)
    ).astype(int)

    college_ids = [f"C{i + 1:03d}" for i in range(n_records)]
    frame = pd.DataFrame(
        {
            "college_id": college_ids,
            "faculty_phd": faculty_phd,
            "faculty_other": faculty_other,
            "frac_research_phd": frac_research_phd,
            "frac_research_other": frac_research_other,
            "research_budget": research_budget,
            "centres_of_excellence_count": centres,
            "teaching_load_per_faculty": teaching_load,
            "diversity_index": diversity_index,
            "industry_collaborations": industry_collaborations,
            "student_count": student_count,
            "num_courses": num_courses,
            "papers_t1": papers_t1,
            "citation_percentile_avg": citation_percentile,
            "overall_rank": overall_rank,
        }
    )
    if include_metadata:
        metadata = pd.DataFrame(
            {
                "scenario_id": scenario_id,
                "synthetic_record_id": [f"{scenario_id}-{i + 1:04d}" for i in range(n_records)],
                "department_id": college_ids,
                "period_start": period_start,
                "period_end": period_end,
                "source_id": f"generator:{GENERATOR_VERSION}",
                "provenance": "synthetic",
                "is_imputed": False,
                "generator_seed": seed,
                "generator_version": GENERATOR_VERSION,
                "response_model_id": RESPONSE_MODEL_ID,
            }
        )
        frame = pd.concat([metadata, frame], axis=1)
    return frame


def load_generation_config(path: str | Path | None):
    if path is None:
        return {}
    config = json.loads(Path(path).read_text())
    allowed = {
        "n_records",
        "seed",
        "include_metadata",
        "scenario_id",
        "period_start",
        "period_end",
        "output",
    }
    unknown = sorted(set(config).difference(allowed))
    if unknown:
        raise ValueError(f"unknown generator configuration keys: {unknown}")
    return config


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="JSON generator configuration")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--n-records", type=int)
    parser.add_argument("--output")
    parser.add_argument(
        "--legacy-columns-only",
        action="store_true",
        help="omit explicit synthetic provenance columns for exact legacy compatibility",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_generation_config(args.config)
    if args.seed is not None:
        config["seed"] = args.seed
    if args.n_records is not None:
        config["n_records"] = args.n_records
    if args.output is not None:
        config["output"] = args.output
    if args.legacy_columns_only:
        config["include_metadata"] = False

    output_value = config.pop("output", None)
    seed = int(config.get("seed", 42))
    output = Path(
        output_value or f"data/synthetic/department_research_data_seed_{seed}.csv"
    )
    frame = generate_legacy_synthetic(**config)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    assumptions_path = output.with_suffix(".assumptions.json")
    assumptions_path.write_text(
        json.dumps(
            {
                "generator_version": GENERATOR_VERSION,
                "response_model_id": RESPONSE_MODEL_ID,
                "provenance": "synthetic",
                "assumptions": response_model_assumptions(),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Generated {len(frame)} explicitly synthetic rows: {output}")
    print(f"Response assumptions: {assumptions_path}")


if __name__ == "__main__":
    main()
