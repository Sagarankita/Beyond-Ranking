export type EvidenceClass =
  | "synthetic_method_fixture"
  | "public_plus_synthetic_scenario"
  | "empirical_descriptive";

export type ArtifactFormat = "csv" | "json";

export interface CatalogFile {
  id: string;
  source: string;
  sourcePath: string;
  output: string;
  url: string;
  format: ArtifactFormat;
  sha256: string;
  bytes: number;
  requiredColumns?: string[];
  numericColumns?: string[];
  units?: Record<string, string>;
}

export interface SnapshotDefinition {
  id: string;
  label: string;
  version: string;
  evidenceClass: EvidenceClass;
  evidenceLabel: string;
  supportsInterventionClaims: boolean;
  claimBoundary: string;
  files: CatalogFile[];
}

export interface ArtifactCatalog {
  schemaVersion: number;
  generatedAt: string;
  description: string;
  snapshots: SnapshotDefinition[];
}

export type CsvRow = Record<string, string>;
export type JsonValue = Record<string, unknown> | unknown[];

export interface LoadedArtifact {
  definition: CatalogFile;
  raw: string;
  rows?: CsvRow[];
  json?: JsonValue;
}

export interface LoadedSnapshot {
  definition: SnapshotDefinition;
  artifacts: Record<string, LoadedArtifact>;
}

export interface AllocationDatum {
  strategy: string;
  variable: string;
  unit: string;
  current: number;
  recommended: number;
  difference: number;
}

export interface KpiDatum {
  strategy: string;
  kpi: string;
  current: number;
  currentLower: number;
  currentUpper: number;
  recommended: number;
  recommendedLower: number;
  recommendedUpper: number;
  evidence: string;
}

export interface ResourceDatum {
  strategy: string;
  label: string;
  value: number;
  limit: number;
  unit: string;
}

export interface ConstraintDatum {
  strategy: string;
  constraint: string;
  residual: number;
  passed: boolean;
}

export interface MetricDatum {
  label: string;
  value: string;
  detail: string;
  tone?: "default" | "positive" | "warning";
}

export interface EvidenceNote {
  title: string;
  body: string;
  status: "supported" | "synthetic" | "descriptive" | "unsupported";
}

export interface OverviewSnapshot {
  id: string;
  label: string;
  version: string;
  evidenceClass: EvidenceClass;
  evidenceLabel: string;
  claimBoundary: string;
  strategies: string[];
  defaultStrategy: string | null;
  allocations: AllocationDatum[];
  kpis: KpiDatum[];
  resources: ResourceDatum[];
  constraints: ConstraintDatum[];
  baseMetrics: MetricDatum[];
  evidenceNotes: EvidenceNote[];
  sourceFiles: CatalogFile[];
}
