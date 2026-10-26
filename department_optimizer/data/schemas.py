"""Named, order-independent data schemas for the proposed project."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


PROVENANCE_VALUES = ("observed", "derived", "assumed", "synthetic")
VARIABLE_ROLES = (
    "identifier",
    "metadata",
    "decision",
    "context",
    "outcome",
    "evaluation",
)


@dataclass(frozen=True)
class FieldSpec:
    name: str
    role: str
    unit: str
    kind: str = "number"
    required: bool = True
    nullable: bool = False
    minimum: float | None = None
    maximum: float | None = None
    allowed_values: tuple[Any, ...] | None = None
    description: str = ""

    def to_dict(self):
        result = asdict(self)
        if result["allowed_values"] is not None:
            result["allowed_values"] = list(result["allowed_values"])
        return result


@dataclass(frozen=True)
class DatasetSchema:
    name: str
    description: str
    fields: tuple[FieldSpec, ...]
    primary_key: tuple[str, ...]
    source_column: str | None = "source_id"
    allow_extra_columns: bool = True

    @property
    def field_map(self):
        return {field.name: field for field in self.fields}

    def to_dict(self):
        return {
            "name": self.name,
            "description": self.description,
            "primary_key": list(self.primary_key),
            "source_column": self.source_column,
            "allow_extra_columns": self.allow_extra_columns,
            "fields": [field.to_dict() for field in self.fields],
        }


def field(name, role, unit, **kwargs):
    if role not in VARIABLE_ROLES:
        raise ValueError(f"unknown variable role: {role}")
    return FieldSpec(name=name, role=role, unit=unit, **kwargs)


COMMON_RECORD_FIELDS = (
    field("department_id", "identifier", "identifier", kind="string"),
    field("institution_id", "identifier", "identifier", kind="string"),
    field("period_start", "metadata", "ISO-8601 date", kind="date"),
    field("period_end", "metadata", "ISO-8601 date", kind="date"),
    field("source_id", "metadata", "source identifier", kind="string"),
    field(
        "provenance",
        "metadata",
        "category",
        kind="string",
        allowed_values=PROVENANCE_VALUES,
    ),
    field("is_imputed", "metadata", "boolean", kind="boolean"),
)


OBSERVED_DEPARTMENT_PERIOD = DatasetSchema(
    name="observed_department_period",
    description="Observed or derived CE/IT department inputs, context, and outcomes by period.",
    primary_key=("department_id", "period_start", "period_end"),
    fields=COMMON_RECORD_FIELDS
    + (
        field("currency", "metadata", "ISO-4217 code", kind="string", allowed_values=("INR",)),
        field("currency_base_year", "metadata", "year", kind="integer", minimum=2000),
        field("faculty_phd", "context", "headcount", kind="integer", minimum=0),
        field("faculty_other", "context", "headcount", kind="integer", minimum=0),
        field("faculty_research_fte", "context", "annual FTE", minimum=0),
        field("research_budget", "decision", "INR at currency_base_year", minimum=0),
        field("teaching_load_per_faculty", "context", "hours/week", minimum=0),
        field("student_count", "context", "headcount", kind="integer", minimum=0),
        field("q1_publications", "outcome", "count", kind="integer", minimum=0, required=False),
        field("normalized_citation_impact", "outcome", "index", minimum=0, required=False),
        field("patent_applications", "outcome", "count", kind="integer", minimum=0, required=False),
        field("industry_projects", "outcome", "count", kind="integer", minimum=0, required=False),
        field("student_research_participants", "outcome", "headcount", kind="integer", minimum=0, required=False),
        field("placements", "outcome", "headcount", kind="integer", minimum=0, required=False),
        field("higher_studies", "outcome", "headcount", kind="integer", minimum=0, required=False),
        field("open_access_publications", "outcome", "count", kind="integer", minimum=0, required=False),
        field("outreach_participants", "outcome", "headcount", kind="integer", minimum=0, required=False),
        field("reported_rank", "evaluation", "ordinal rank", kind="integer", minimum=1, required=False),
    ),
)


INSTITUTIONAL_PEER_BENCHMARK = DatasetSchema(
    name="institutional_peer_benchmark",
    description="Institution-period records used only for comparable efficiency/ranking benchmarks.",
    primary_key=("institution_id", "period_start", "period_end"),
    fields=(
        field("institution_id", "identifier", "identifier", kind="string"),
        field("period_start", "metadata", "ISO-8601 date", kind="date"),
        field("period_end", "metadata", "ISO-8601 date", kind="date"),
        field("source_id", "metadata", "source identifier", kind="string"),
        field("provenance", "metadata", "category", kind="string", allowed_values=PROVENANCE_VALUES),
        field("is_imputed", "metadata", "boolean", kind="boolean"),
        field("currency", "metadata", "ISO-4217 code", kind="string", allowed_values=("INR",)),
        field("currency_base_year", "metadata", "year", kind="integer", minimum=2000),
        field("research_expenditure", "context", "INR at currency_base_year", minimum=0),
        field("faculty_research_fte", "context", "annual FTE", minimum=0),
        field("q1_publications", "outcome", "count", kind="integer", minimum=0),
        field("normalized_citation_impact", "outcome", "index", minimum=0, required=False),
        field("patent_applications", "outcome", "count", kind="integer", minimum=0, required=False),
        field("student_outcome_index", "outcome", "documented index", minimum=0, required=False),
        field("societal_outcome_index", "outcome", "documented index", minimum=0, required=False),
        field("reported_rank", "evaluation", "ordinal rank", kind="integer", minimum=1, required=False),
    ),
)


CURRENT_ALLOCATION = DatasetSchema(
    name="current_allocation",
    description="Observed current departmental allocation used as an optimization baseline.",
    primary_key=("department_id", "period_start", "period_end"),
    fields=COMMON_RECORD_FIELDS
    + (
        field("currency", "metadata", "ISO-4217 code", kind="string", allowed_values=("INR",)),
        field("currency_base_year", "metadata", "year", kind="integer", minimum=2000),
        field("research_seed_funding", "decision", "INR at currency_base_year", minimum=0),
        field("conference_support", "decision", "INR at currency_base_year", minimum=0),
        field("patent_ip_support", "decision", "INR at currency_base_year", minimum=0),
        field("industry_collaboration_funding", "decision", "INR at currency_base_year", minimum=0),
        field("student_research_funding", "decision", "INR at currency_base_year", minimum=0),
        field("open_access_funding", "decision", "INR at currency_base_year", minimum=0),
        field("outreach_sdg_funding", "decision", "INR at currency_base_year", minimum=0),
        field("research_faculty_effort", "decision", "annual FTE", minimum=0),
        field("student_support_faculty_effort", "decision", "annual FTE", minimum=0),
        field("service_faculty_effort", "decision", "annual FTE", minimum=0),
        field("research_assistant_count", "decision", "headcount", kind="integer", minimum=0),
        field("compute_capacity_units", "decision", "configured compute unit", kind="integer", minimum=0),
    ),
)


SYNTHETIC_SCENARIO_RECORD = DatasetSchema(
    name="synthetic_scenario_record",
    description="Explicitly synthetic allocation/outcome rows for pipeline and scenario tests.",
    primary_key=("scenario_id", "synthetic_record_id"),
    fields=(
        field("scenario_id", "identifier", "identifier", kind="string"),
        field("synthetic_record_id", "identifier", "identifier", kind="string"),
        field("department_id", "identifier", "identifier", kind="string"),
        field("period_start", "metadata", "ISO-8601 date", kind="date"),
        field("period_end", "metadata", "ISO-8601 date", kind="date"),
        field("source_id", "metadata", "source identifier", kind="string"),
        field("provenance", "metadata", "category", kind="string", allowed_values=("synthetic",)),
        field("is_imputed", "metadata", "boolean", kind="boolean"),
        field("generator_seed", "metadata", "integer seed", kind="integer", minimum=0),
        field("generator_version", "metadata", "version", kind="string"),
        field("response_model_id", "metadata", "assumption identifier", kind="string"),
    ),
)


LEGACY_SYNTHETIC_RESEARCH = DatasetSchema(
    name="legacy_synthetic_research",
    description="Unmodified 521-row senior-project synthetic research/rank fixture.",
    primary_key=("college_id",),
    source_column=None,
    allow_extra_columns=False,
    fields=(
        field("college_id", "identifier", "synthetic identifier", kind="string"),
        field("faculty_phd", "context", "headcount", kind="integer", minimum=0),
        field("faculty_other", "context", "headcount", kind="integer", minimum=0),
        field("frac_research_phd", "decision", "fraction", minimum=0, maximum=1),
        field("frac_research_other", "decision", "fraction", minimum=0, maximum=1),
        field("research_budget", "decision", "nominal INR (synthetic)", minimum=0),
        field("centres_of_excellence_count", "context", "count", kind="integer", minimum=0),
        field("teaching_load_per_faculty", "context", "synthetic load index", minimum=0),
        field("diversity_index", "context", "fraction", minimum=0, maximum=1),
        field("industry_collaborations", "context", "count", kind="integer", minimum=0),
        field("student_count", "context", "headcount", kind="integer", minimum=0),
        field("num_courses", "context", "count", kind="integer", minimum=0),
        field("papers_t1", "outcome", "synthetic count", kind="integer", minimum=0),
        field("citation_percentile_avg", "outcome", "fraction", minimum=0, maximum=1),
        field("overall_rank", "evaluation", "synthetic ordinal rank", kind="integer", minimum=1),
    ),
)


SCHEMAS = {
    schema.name: schema
    for schema in (
        OBSERVED_DEPARTMENT_PERIOD,
        INSTITUTIONAL_PEER_BENCHMARK,
        CURRENT_ALLOCATION,
        SYNTHETIC_SCENARIO_RECORD,
        LEGACY_SYNTHETIC_RESEARCH,
    )
}


def get_schema(name: str) -> DatasetSchema:
    try:
        return SCHEMAS[name]
    except KeyError as exc:
        raise KeyError(f"unknown schema {name!r}; choose from {sorted(SCHEMAS)}") from exc


def data_dictionary():
    return {name: schema.to_dict() for name, schema in SCHEMAS.items()}
