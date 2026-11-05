from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .catalog import CATALOG_PATH, REPOSITORY_ROOT
from .contracts import (
    ArtifactContractError,
    resolve_allowlisted_path,
    validate_catalog,
    validate_dataframe,
)
from .types import (
    ArtifactCatalog,
    CatalogFile,
    EvidenceClass,
    LoadedArtifact,
    LoadedSnapshot,
    SnapshotDefinition,
)


def _catalog_file(value: dict[str, Any]) -> CatalogFile:
    return CatalogFile(
        id=str(value["id"]),
        source_path=str(value["sourcePath"]),
        format=str(value["format"]),
        sha256=str(value["sha256"]),
        bytes=int(value["bytes"]),
        required_columns=tuple(value.get("requiredColumns", [])),
        numeric_columns=tuple(value.get("numericColumns", [])),
        units={str(key): str(unit) for key, unit in value.get("units", {}).items()},
    )


def load_catalog(path: Path = CATALOG_PATH) -> ArtifactCatalog:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        snapshots = tuple(
            SnapshotDefinition(
                id=str(item["id"]),
                label=str(item["label"]),
                version=str(item["version"]),
                evidence_class=EvidenceClass(str(item["evidenceClass"])),
                evidence_label=str(item["evidenceLabel"]),
                supports_intervention_claims=bool(item["supportsInterventionClaims"]),
                claim_boundary=str(item["claimBoundary"]),
                files=tuple(_catalog_file(file) for file in item["files"]),
            )
            for item in payload["snapshots"]
        )
        catalog = ArtifactCatalog(
            schema_version=int(payload["schemaVersion"]),
            description=str(payload["description"]),
            snapshots=snapshots,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ArtifactContractError(f"Artifact catalog is invalid: {exc}") from exc
    validate_catalog(catalog)
    return catalog


def load_artifact(
    definition: CatalogFile,
    repository_root: Path = REPOSITORY_ROOT,
) -> LoadedArtifact:
    path = resolve_allowlisted_path(repository_root, definition.source_path)
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != definition.sha256:
        raise ArtifactContractError(
            f"{definition.source_path} failed SHA-256 validation. "
            f"Expected {definition.sha256}, received {digest}."
        )
    if len(raw) != definition.bytes:
        raise ArtifactContractError(
            f"{definition.source_path} failed byte-count validation."
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ArtifactContractError(
            f"{definition.source_path} is not valid UTF-8."
        ) from exc
    if definition.format == "csv":
        frame = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
        validate_dataframe(definition, frame)
        return LoadedArtifact(definition=definition, raw=raw, rows=frame)
    if definition.format == "json":
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ArtifactContractError(
                f"{definition.source_path} is not valid JSON."
            ) from exc
        if not isinstance(value, (dict, list)):
            raise ArtifactContractError(
                f"{definition.source_path} must contain a JSON object or array."
            )
        return LoadedArtifact(definition=definition, raw=raw, json=value)
    raise ArtifactContractError(
        f"{definition.source_path} has unsupported format {definition.format}."
    )


def load_snapshot(snapshot_id: str, catalog: ArtifactCatalog | None = None) -> LoadedSnapshot:
    active_catalog = catalog or load_catalog()
    definition = next(
        (snapshot for snapshot in active_catalog.snapshots if snapshot.id == snapshot_id),
        None,
    )
    if definition is None:
        raise ArtifactContractError(f"Unknown snapshot id: {snapshot_id}.")
    artifacts = {
        file.id: load_artifact(file)
        for file in definition.files
    }
    return LoadedSnapshot(definition=definition, artifacts=artifacts)
