import { parseCsv } from "./csv";
import { ArtifactContractError, validateCatalog, validateCsvRows } from "./contracts";
import type {
  ArtifactCatalog,
  CatalogFile,
  JsonValue,
  LoadedArtifact,
  LoadedSnapshot,
  SnapshotDefinition,
} from "./types";

export async function sha256Hex(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)]
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
}

async function fetchText(url: string, signal?: AbortSignal): Promise<string> {
  const response = await fetch(url, { signal });
  if (!response.ok) {
    throw new ArtifactContractError(`Could not load ${url}: HTTP ${response.status}.`);
  }
  return response.text();
}

function resolveAssetUrl(path: string): string {
  return new URL(path, document.baseURI).toString();
}

export async function loadCatalog(signal?: AbortSignal): Promise<ArtifactCatalog> {
  const text = await fetchText(resolveAssetUrl("data/catalog.json"), signal);
  const catalog = JSON.parse(text) as ArtifactCatalog;
  validateCatalog(catalog);
  return catalog;
}

async function loadArtifact(
  definition: CatalogFile,
  signal?: AbortSignal,
): Promise<LoadedArtifact> {
  const raw = await fetchText(resolveAssetUrl(definition.url), signal);
  const digest = await sha256Hex(raw);
  if (digest !== definition.sha256) {
    throw new ArtifactContractError(
      `${definition.sourcePath} failed SHA-256 validation. Expected ${definition.sha256}, received ${digest}.`,
    );
  }

  if (definition.format === "csv") {
    const rows = parseCsv(raw);
    validateCsvRows(definition, rows);
    return { definition, raw, rows };
  }

  let json: JsonValue;
  try {
    json = JSON.parse(raw) as JsonValue;
  } catch {
    throw new ArtifactContractError(`${definition.sourcePath} is not valid JSON.`);
  }
  return { definition, raw, json };
}

export async function loadSnapshot(
  definition: SnapshotDefinition,
  signal?: AbortSignal,
): Promise<LoadedSnapshot> {
  const artifacts = await Promise.all(
    definition.files.map((file) => loadArtifact(file, signal)),
  );

  return {
    definition,
    artifacts: Object.fromEntries(artifacts.map((artifact) => [artifact.definition.id, artifact])),
  };
}
