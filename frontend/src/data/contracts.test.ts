import { describe, expect, it } from "vitest";
import { ArtifactContractError, parseBoolean, validateCatalog, validateCsvRows } from "./contracts";
import type { ArtifactCatalog, CatalogFile } from "./types";

const file: CatalogFile = {
  id: "fixture",
  source: "fixture.csv",
  sourcePath: "fixture.csv",
  output: "fixture.csv",
  url: "data/fixture.csv",
  format: "csv",
  sha256: "0".repeat(64),
  bytes: 1,
  requiredColumns: ["name", "value"],
  numericColumns: ["value"],
};

describe("artifact contracts", () => {
  it("rejects missing required columns and values", () => {
    expect(() => validateCsvRows(file, [{ name: "alpha" }])).toThrow(/required column “value”/);
    expect(() => validateCsvRows(file, [{ name: "", value: "1" }])).toThrow(/missing name value/);
  });

  it("rejects non-finite numeric values", () => {
    expect(() => validateCsvRows(file, [{ name: "alpha", value: "NaN" }])).toThrow(/non-finite value/);
    expect(() => validateCsvRows(file, [{ name: "alpha", value: "Infinity" }])).toThrow(ArtifactContractError);
  });

  it("requires a recognized evidence class", () => {
    const catalog = {
      schemaVersion: 1,
      generatedAt: "2026-01-01T00:00:00Z",
      description: "test",
      snapshots: [{
        id: "bad",
        label: "Bad",
        version: "v1",
        evidenceClass: "causal_claim",
        evidenceLabel: "invalid",
        supportsInterventionClaims: true,
        claimBoundary: "none",
        files: [],
      }],
    } as unknown as ArtifactCatalog;

    expect(() => validateCatalog(catalog)).toThrow(/unknown evidence class/);
  });

  it("parses explicit booleans without truthiness coercion", () => {
    expect(parseBoolean("True")).toBe(true);
    expect(parseBoolean("0")).toBe(false);
    expect(() => parseBoolean("maybe")).toThrow(/Expected a boolean/);
  });
});
