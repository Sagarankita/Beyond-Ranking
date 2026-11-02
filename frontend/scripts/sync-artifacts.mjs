import { createHash } from "node:crypto";
import { cp, mkdir, readFile, stat, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(frontendRoot, "..");
const publicRoot = resolve(frontendRoot, "public");

const snapshots = [
  {
    id: "synthetic-phase7-v1",
    label: "Synthetic method fixture",
    version: "phase7-synthetic-v1",
    evidenceClass: "synthetic_method_fixture",
    evidenceLabel: "Synthetic fixture · not empirical",
    supportsInterventionClaims: false,
    claimBoundary:
      "Method-validation fixture only. Predictions are illustrative, noncausal, and not institution-specific.",
    files: [
      {
        id: "manifest",
        source: "results/reporting/phase7-synthetic-v1/manifest.json",
        output: "manifest.json",
        format: "json",
      },
      {
        id: "allocations",
        source: "results/reporting/phase7-synthetic-v1/current_vs_strategy_allocations.csv",
        output: "current_vs_strategy_allocations.csv",
        format: "csv",
        requiredColumns: ["strategy", "variable", "unit", "current", "recommended", "difference"],
        numericColumns: ["current", "recommended", "difference"],
        units: { current: "unit column", recommended: "unit column", difference: "unit column" },
      },
      {
        id: "kpis",
        source: "results/reporting/phase7-synthetic-v1/current_vs_strategy_kpis.csv",
        output: "current_vs_strategy_kpis.csv",
        format: "csv",
        requiredColumns: ["strategy", "kpi", "current_prediction", "current_lower", "current_upper", "recommended_prediction", "recommended_lower", "recommended_upper"],
        numericColumns: ["current_prediction", "current_lower", "current_upper", "recommended_prediction", "recommended_lower", "recommended_upper"],
        units: { current_prediction: "KPI-specific", recommended_prediction: "KPI-specific" },
      },
      {
        id: "resources",
        source: "results/reporting/phase7-synthetic-v1/resource_utilization.csv",
        output: "resource_utilization.csv",
        format: "csv",
        requiredColumns: ["strategy", "cost", "budget_limit", "budget_utilization", "budget_remaining", "research_fte", "research_fte_capacity", "research_fte_utilization"],
        numericColumns: ["cost", "budget_limit", "budget_utilization", "budget_remaining", "research_fte", "research_fte_capacity", "research_fte_utilization"],
        units: { cost: "INR", budget_limit: "INR", research_fte: "FTE" },
      },
      {
        id: "constraints",
        source: "results/reporting/phase7-synthetic-v1/constraint_checks.csv",
        output: "constraint_checks.csv",
        format: "csv",
        requiredColumns: ["strategy", "constraint", "residual", "passed"],
        numericColumns: ["residual"],
      },
      {
        id: "portfolio",
        source: "results/reporting/phase7-synthetic-v1/strategy_portfolio.csv",
        output: "strategy_portfolio.csv",
        format: "csv",
        requiredColumns: ["selection_status", "allocation_group", "cost", "feasible", "objective_benefit__research"],
        numericColumns: ["cost", "objective_benefit__research"],
      },
    ],
  },
  {
    id: "vjti-public-synthetic-v1",
    label: "VJTI public + synthetic scenario",
    version: "vjti_public_plus_synthetic_experiments_v1",
    evidenceClass: "public_plus_synthetic_scenario",
    evidenceLabel: "Public-calibrated · synthetic responses",
    supportsInterventionClaims: false,
    claimBoundary:
      "Public evidence calibrates the baseline, but intervention responses are synthetic, associational, and noncausal.",
    files: [
      {
        id: "manifest",
        source: "artifacts/public_experiments/vjti_v1/experiment_manifest.json",
        output: "experiment_manifest.json",
        format: "json",
      },
      {
        id: "allocations",
        source: "artifacts/public_experiments/vjti_v1/strategy_allocations.csv",
        output: "strategy_allocations.csv",
        format: "csv",
        requiredColumns: ["strategy_id", "strategy_type", "scenario", "source_artifact", "feasible", "total_cost", "budget_remaining", "decision", "value"],
        numericColumns: ["total_cost", "budget_remaining", "value"],
        units: { total_cost: "INR", budget_remaining: "INR", value: "decision-specific" },
      },
      {
        id: "kpis",
        source: "artifacts/public_experiments/vjti_v1/strategy_kpis.csv",
        output: "strategy_kpis.csv",
        format: "csv",
        requiredColumns: ["strategy_id", "strategy_type", "scenario", "kpi", "prediction", "lower", "upper"],
        numericColumns: ["prediction", "lower", "upper"],
        units: { prediction: "KPI-specific", lower: "KPI-specific", upper: "KPI-specific" },
      },
      {
        id: "resources",
        source: "artifacts/public_experiments/vjti_v1/strategy_resource_summary.csv",
        output: "strategy_resource_summary.csv",
        format: "csv",
        requiredColumns: ["strategy_id", "strategy_type", "scenario", "total_cost", "budget_remaining", "allocated_faculty_fte", "resource_feasible"],
        numericColumns: ["total_cost", "budget_remaining", "allocated_faculty_fte"],
        units: { total_cost: "INR", budget_remaining: "INR", allocated_faculty_fte: "FTE" },
      },
      {
        id: "constraints",
        source: "artifacts/public_experiments/vjti_v1/strategy_constraints.csv",
        output: "strategy_constraints.csv",
        format: "csv",
        requiredColumns: ["strategy_id", "constraint", "residual", "normalized_residual"],
        numericColumns: ["residual", "normalized_residual"],
      },
      {
        id: "evidence",
        source: "artifacts/evidence_modeling/vjti_v1/kpi_evidence_registry.csv",
        output: "kpi_evidence_registry.csv",
        format: "csv",
        requiredColumns: ["kpi", "status", "public_model_status", "synthetic_model_status", "claim_boundary"],
      },
    ],
  },
  {
    id: "vjti-empirical-v1",
    label: "VJTI empirical public evidence",
    version: "vjti-ceit-public-plus-synthetic-v1",
    evidenceClass: "empirical_descriptive",
    evidenceLabel: "Observed + derived · descriptive only",
    supportsInterventionClaims: false,
    claimBoundary:
      "Descriptive public evidence only. No empirical intervention-response model or empirical optimization run is available.",
    files: [
      {
        id: "manifest",
        source: "artifacts/public_data/vjti_ceit_v1/manifest.json",
        output: "manifest.json",
        format: "json",
      },
      {
        id: "coverage",
        source: "artifacts/public_data/vjti_ceit_v1/provenance_coverage.csv",
        output: "provenance_coverage.csv",
        format: "csv",
        requiredColumns: ["dimension", "member", "provenance", "count", "coverage_fraction"],
        numericColumns: ["count", "coverage_fraction"],
      },
      {
        id: "sources",
        source: "artifacts/public_data/vjti_ceit_v1/source_register.csv",
        output: "source_register.csv",
        format: "csv",
        requiredColumns: ["source_id", "title", "url", "access_date", "authority", "retrieval_status", "sha256"],
      },
      {
        id: "publicOnly",
        source: "artifacts/public_experiments/vjti_v1/public_only_sensitivity.csv",
        output: "public_only_sensitivity.csv",
        format: "csv",
        requiredColumns: ["analysis_track", "outcome", "denominator", "numerator", "denominator_value", "rate", "source_artifact", "causal_claim"],
        numericColumns: ["numerator", "denominator_value", "rate"],
      },
      {
        id: "evidence",
        source: "artifacts/evidence_modeling/vjti_v1/kpi_evidence_registry.csv",
        output: "kpi_evidence_registry.csv",
        format: "csv",
        requiredColumns: ["kpi", "status", "public_model_status", "synthetic_model_status", "claim_boundary"],
      },
    ],
  },
];

function sha256(buffer) {
  return createHash("sha256").update(buffer).digest("hex");
}

const catalog = {
  schemaVersion: 1,
  generatedAt: new Date().toISOString(),
  description: "Build-time index of immutable, versioned Beyond Ranking artifacts.",
  snapshots: [],
};

for (const snapshot of snapshots) {
  const outputDirectory = resolve(publicRoot, "data", snapshot.id);
  await mkdir(outputDirectory, { recursive: true });
  const catalogFiles = [];

  for (const file of snapshot.files) {
    const source = resolve(repositoryRoot, file.source);
    const destination = resolve(outputDirectory, file.output);
    const contents = await readFile(source);
    await writeFile(destination, contents);
    const metadata = await stat(source);
    catalogFiles.push({
      ...file,
      sourcePath: file.source,
      url: `data/${snapshot.id}/${file.output}`,
      sha256: sha256(contents),
      bytes: metadata.size,
    });
  }

  catalog.snapshots.push({
    ...snapshot,
    files: catalogFiles,
  });
}

await mkdir(resolve(publicRoot, "data"), { recursive: true });
await writeFile(
  resolve(publicRoot, "data", "catalog.json"),
  `${JSON.stringify(catalog, null, 2)}\n`,
);

const legacySource = resolve(repositoryRoot, "sites/beyond-ranking-evidence-dashboard/dist");
const legacyDestination = resolve(publicRoot, "legacy");
await mkdir(legacyDestination, { recursive: true });
await cp(legacySource, legacyDestination, { recursive: true, force: true });

console.log(`Synced ${catalog.snapshots.length} evidence snapshots and the legacy viewer.`);
