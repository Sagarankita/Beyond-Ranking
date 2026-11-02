import { describe, expect, it } from "vitest";
import { adaptOverviewSnapshot } from "./adapters";
import type { CatalogFile, LoadedArtifact, LoadedSnapshot, SnapshotDefinition } from "./types";

function csvArtifact(id: string, rows: Array<Record<string, string>>): LoadedArtifact {
  const definition: CatalogFile = {
    id,
    source: `${id}.csv`,
    sourcePath: `${id}.csv`,
    output: `${id}.csv`,
    url: `data/${id}.csv`,
    format: "csv",
    sha256: "0".repeat(64),
    bytes: 1,
  };
  return { definition, raw: "", rows };
}

describe("overview evidence adapters", () => {
  it("keeps the empirical lane descriptive and optimizer-free", () => {
    const definition: SnapshotDefinition = {
      id: "empirical",
      label: "Empirical evidence",
      version: "v1",
      evidenceClass: "empirical_descriptive",
      evidenceLabel: "Descriptive only",
      supportsInterventionClaims: false,
      claimBoundary: "No intervention-response claims.",
      files: [],
    };
    const snapshot: LoadedSnapshot = {
      definition,
      artifacts: {
        coverage: csvArtifact("coverage", [
          { provenance: "observed_public", count: "2" },
          { provenance: "derived_public", count: "3" },
        ]),
        sources: csvArtifact("sources", [{ source_id: "one" }, { source_id: "two" }]),
        publicOnly: csvArtifact("publicOnly", [{ analysis_track: "descriptive" }]),
        evidence: csvArtifact("evidence", [{
          kpi: "graduation rate",
          status: "public_descriptive",
          claim_boundary: "Association only.",
        }]),
      },
    };

    const overview = adaptOverviewSnapshot(snapshot);

    expect(overview.strategies).toEqual([]);
    expect(overview.allocations).toEqual([]);
    expect(overview.kpis).toEqual([]);
    expect(overview.baseMetrics).toContainEqual(expect.objectContaining({
      label: "Empirical optimizer runs",
      value: "0",
    }));
    expect(overview.evidenceNotes).toContainEqual(expect.objectContaining({
      status: "descriptive",
    }));
  });
});
