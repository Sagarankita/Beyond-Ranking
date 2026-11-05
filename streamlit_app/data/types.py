from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import pandas as pd


class EvidenceClass(StrEnum):
    SYNTHETIC = "synthetic_method_fixture"
    MIXED = "public_plus_synthetic_scenario"
    EMPIRICAL = "empirical_descriptive"


@dataclass(frozen=True)
class CatalogFile:
    id: str
    source_path: str
    format: str
    sha256: str
    bytes: int
    required_columns: tuple[str, ...] = ()
    numeric_columns: tuple[str, ...] = ()
    units: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SnapshotDefinition:
    id: str
    label: str
    version: str
    evidence_class: EvidenceClass
    evidence_label: str
    supports_intervention_claims: bool
    claim_boundary: str
    files: tuple[CatalogFile, ...]


@dataclass(frozen=True)
class ArtifactCatalog:
    schema_version: int
    description: str
    snapshots: tuple[SnapshotDefinition, ...]


@dataclass
class LoadedArtifact:
    definition: CatalogFile
    raw: bytes
    rows: pd.DataFrame | None = None
    json: dict[str, Any] | list[Any] | None = None


@dataclass
class LoadedSnapshot:
    definition: SnapshotDefinition
    artifacts: dict[str, LoadedArtifact]


@dataclass(frozen=True)
class Metric:
    label: str
    value: str
    detail: str
    tone: str = "default"


@dataclass(frozen=True)
class EvidenceNote:
    title: str
    body: str
    status: str


@dataclass
class OverviewSnapshot:
    id: str
    label: str
    version: str
    evidence_class: EvidenceClass
    evidence_label: str
    claim_boundary: str
    strategies: list[str]
    default_strategy: str | None
    allocations: pd.DataFrame
    kpis: pd.DataFrame
    resources: pd.DataFrame
    constraints: pd.DataFrame
    base_metrics: list[Metric]
    evidence_notes: list[EvidenceNote]
    source_files: tuple[CatalogFile, ...]
