import type { ArtifactCatalog, CatalogFile, CsvRow, EvidenceClass } from "./types";

export const EVIDENCE_CLASSES: EvidenceClass[] = [
  "synthetic_method_fixture",
  "public_plus_synthetic_scenario",
  "empirical_descriptive",
];

export class ArtifactContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ArtifactContractError";
  }
}

export function validateCatalog(catalog: ArtifactCatalog): void {
  if (catalog.schemaVersion !== 1) {
    throw new ArtifactContractError(`Unsupported catalog schema: ${catalog.schemaVersion}`);
  }
  if (!Array.isArray(catalog.snapshots) || catalog.snapshots.length === 0) {
    throw new ArtifactContractError("Artifact catalog contains no snapshots.");
  }

  const ids = new Set<string>();
  for (const snapshot of catalog.snapshots) {
    if (ids.has(snapshot.id)) {
      throw new ArtifactContractError(`Duplicate snapshot id: ${snapshot.id}`);
    }
    ids.add(snapshot.id);
    if (!EVIDENCE_CLASSES.includes(snapshot.evidenceClass)) {
      throw new ArtifactContractError(
        `Snapshot ${snapshot.id} has an unknown evidence class: ${snapshot.evidenceClass}`,
      );
    }
    if (!snapshot.version || !snapshot.claimBoundary) {
      throw new ArtifactContractError(
        `Snapshot ${snapshot.id} is missing version or claim-boundary metadata.`,
      );
    }
  }
}

export function validateCsvRows(file: CatalogFile, rows: CsvRow[]): void {
  if (rows.length === 0) {
    throw new ArtifactContractError(`${file.sourcePath} contains no data rows.`);
  }

  const headers = new Set(Object.keys(rows[0] ?? {}));
  for (const column of file.requiredColumns ?? []) {
    if (!headers.has(column)) {
      throw new ArtifactContractError(
        `${file.sourcePath} is missing required column “${column}”.`,
      );
    }
  }

  rows.forEach((row, rowIndex) => {
    for (const column of file.requiredColumns ?? []) {
      if (!(column in row) || row[column]?.trim() === "") {
        throw new ArtifactContractError(
          `${file.sourcePath} has a missing ${column} value at data row ${rowIndex + 1}.`,
        );
      }
    }
    for (const column of file.numericColumns ?? []) {
      const value = row[column];
      if (value === undefined || value.trim() === "" || !Number.isFinite(Number(value))) {
        throw new ArtifactContractError(
          `${file.sourcePath} has a non-finite ${column} value at data row ${rowIndex + 1}.`,
        );
      }
    }
  });
}

export function parseBoolean(value: string): boolean {
  const normalized = value.trim().toLowerCase();
  if (["true", "1", "yes"].includes(normalized)) return true;
  if (["false", "0", "no"].includes(normalized)) return false;
  throw new ArtifactContractError(`Expected a boolean value; received “${value}”.`);
}

export function finiteNumber(value: string, label: string): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    throw new ArtifactContractError(`${label} must be finite; received “${value}”.`);
  }
  return parsed;
}
