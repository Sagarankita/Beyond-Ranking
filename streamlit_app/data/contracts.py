from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd

from .types import ArtifactCatalog, CatalogFile, EvidenceClass


class ArtifactContractError(ValueError):
    """Raised when a saved artifact violates the read-only UI contract."""


def validate_catalog(catalog: ArtifactCatalog) -> None:
    if catalog.schema_version != 1:
        raise ArtifactContractError(
            f"Unsupported catalog schema: {catalog.schema_version}."
        )
    if not catalog.snapshots:
        raise ArtifactContractError("Artifact catalog contains no snapshots.")
    ids: set[str] = set()
    for snapshot in catalog.snapshots:
        if snapshot.id in ids:
            raise ArtifactContractError(f"Duplicate snapshot id: {snapshot.id}.")
        ids.add(snapshot.id)
        if not isinstance(snapshot.evidence_class, EvidenceClass):
            raise ArtifactContractError(
                f"Snapshot {snapshot.id} has an unknown evidence class."
            )
        if not snapshot.version or not snapshot.claim_boundary:
            raise ArtifactContractError(
                f"Snapshot {snapshot.id} is missing version or claim-boundary metadata."
            )


def resolve_allowlisted_path(repository_root: Path, source_path: str) -> Path:
    if Path(source_path).is_absolute():
        raise ArtifactContractError("Artifact paths must be repository-relative.")
    root = repository_root.resolve()
    target = (root / source_path).resolve()
    if target != root and root not in target.parents:
        raise ArtifactContractError(f"Artifact path escapes the repository: {source_path}.")
    if not target.is_file():
        raise ArtifactContractError(f"Artifact file is missing: {source_path}.")
    return target


def validate_dataframe(file: CatalogFile, frame: pd.DataFrame) -> None:
    if frame.empty:
        raise ArtifactContractError(f"{file.source_path} contains no data rows.")
    missing = [column for column in file.required_columns if column not in frame.columns]
    if missing:
        raise ArtifactContractError(
            f"{file.source_path} is missing required column “{missing[0]}”."
        )
    for column in file.required_columns:
        values = frame[column]
        empty = values.isna() | values.astype(str).str.strip().eq("")
        if empty.any():
            row = int(empty[empty].index[0]) + 1
            raise ArtifactContractError(
                f"{file.source_path} has a missing {column} value at data row {row}."
            )
    for column in file.numeric_columns:
        converted = pd.to_numeric(frame[column], errors="coerce")
        invalid = converted.isna() | ~converted.map(math.isfinite)
        if invalid.any():
            row = int(invalid[invalid].index[0]) + 1
            raise ArtifactContractError(
                f"{file.source_path} has a non-finite {column} value at data row {row}."
            )


def parse_boolean(value: Any) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ArtifactContractError(f"Expected a boolean value; received “{value}”.")


def finite_number(value: Any, label: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ArtifactContractError(f"{label} must be numeric; received “{value}”.") from exc
    if not math.isfinite(parsed):
        raise ArtifactContractError(f"{label} must be finite; received “{value}”.")
    return parsed
