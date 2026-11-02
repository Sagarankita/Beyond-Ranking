import { finiteNumber, parseBoolean } from "./contracts";
import type {
  AllocationDatum,
  ConstraintDatum,
  CsvRow,
  EvidenceNote,
  JsonValue,
  KpiDatum,
  LoadedSnapshot,
  MetricDatum,
  OverviewSnapshot,
  ResourceDatum,
} from "./types";

function rows(snapshot: LoadedSnapshot, id: string): CsvRow[] {
  return snapshot.artifacts[id]?.rows ?? [];
}

function jsonObject(snapshot: LoadedSnapshot, id: string): Record<string, unknown> {
  const value = snapshot.artifacts[id]?.json as JsonValue | undefined;
  return value && !Array.isArray(value) ? value : {};
}

function unique(values: string[]): string[] {
  return [...new Set(values)];
}

function titleCase(value: string): string {
  return value
    .replace(/^policy_/, "")
    .replaceAll("__", " · ")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function syntheticOverview(snapshot: LoadedSnapshot): OverviewSnapshot {
  const allocationRows = rows(snapshot, "allocations");
  const kpiRows = rows(snapshot, "kpis");
  const resourceRows = rows(snapshot, "resources");
  const constraintRows = rows(snapshot, "constraints");
  const portfolioRows = rows(snapshot, "portfolio");
  const manifest = jsonObject(snapshot, "manifest");
  const strategies = unique(allocationRows.map((row) => row.strategy ?? "").filter(Boolean));

  const allocations: AllocationDatum[] = allocationRows.map((row) => ({
    strategy: row.strategy ?? "",
    variable: row.variable ?? "",
    unit: row.unit ?? "",
    current: finiteNumber(row.current ?? "", "allocation current"),
    recommended: finiteNumber(row.recommended ?? "", "allocation recommended"),
    difference: finiteNumber(row.difference ?? "", "allocation difference"),
  }));

  const kpis: KpiDatum[] = kpiRows.map((row) => ({
    strategy: row.strategy ?? "",
    kpi: row.kpi ?? "",
    current: finiteNumber(row.current_prediction ?? "", "current KPI prediction"),
    currentLower: finiteNumber(row.current_lower ?? "", "current KPI lower interval"),
    currentUpper: finiteNumber(row.current_upper ?? "", "current KPI upper interval"),
    recommended: finiteNumber(
      row.recommended_prediction ?? "",
      "recommended KPI prediction",
    ),
    recommendedLower: finiteNumber(
      row.recommended_lower ?? "",
      "recommended KPI lower interval",
    ),
    recommendedUpper: finiteNumber(
      row.recommended_upper ?? "",
      "recommended KPI upper interval",
    ),
    evidence: "synthetic_method_fixture",
  }));

  const resources: ResourceDatum[] = resourceRows.flatMap((row) => [
    {
      strategy: row.strategy ?? "",
      label: "Budget",
      value: finiteNumber(row.cost ?? "", "resource cost"),
      limit: finiteNumber(row.budget_limit ?? "", "budget limit"),
      unit: "INR",
    },
    {
      strategy: row.strategy ?? "",
      label: "Research faculty effort",
      value: finiteNumber(row.research_fte ?? "", "research FTE"),
      limit: finiteNumber(row.research_fte_capacity ?? "", "research FTE capacity"),
      unit: "FTE",
    },
  ]);

  const constraints: ConstraintDatum[] = constraintRows.map((row) => ({
    strategy: row.strategy ?? "",
    constraint: row.constraint ?? "",
    residual: finiteNumber(row.residual ?? "", "constraint residual"),
    passed: parseBoolean(row.passed ?? ""),
  }));

  const selectedPortfolio = portfolioRows.filter(
    (row) => row.selection_status === "selected",
  );
  const uniqueAllocations = new Set(
    selectedPortfolio.map((row) => row.allocation_group).filter(Boolean),
  ).size;
  const reportId = String(manifest.report_id ?? snapshot.definition.version);

  const baseMetrics: MetricDatum[] = [
    {
      label: "Saved strategies",
      value: String(strategies.length),
      detail: "Post-optimization portfolio views",
    },
    {
      label: "Unique allocations",
      value: String(uniqueAllocations),
      detail: "Several strategy labels may share one allocation",
      tone: uniqueAllocations <= 1 ? "warning" : "default",
    },
    {
      label: "Supported objectives",
      value: "1 / 4",
      detail: "Research only in this fixture",
      tone: "warning",
    },
    {
      label: "Artifact version",
      value: "v1",
      detail: reportId,
    },
  ];

  const evidenceNotes: EvidenceNote[] = [
    {
      title: "Research objective",
      body: "Supported within this synthetic method fixture by the saved response model and reporting definitions.",
      status: "synthetic",
    },
    {
      title: "Innovation, student and societal objectives",
      body: "Unsupported zero-score dimensions in this fixture; the Overview does not chart them as meaningful outcomes.",
      status: "unsupported",
    },
    {
      title: "Institutional interpretation",
      body: "The reference allocation is illustrative and the predicted changes are not observed or causal effects.",
      status: "unsupported",
    },
  ];

  return {
    id: snapshot.definition.id,
    label: snapshot.definition.label,
    version: snapshot.definition.version,
    evidenceClass: snapshot.definition.evidenceClass,
    evidenceLabel: snapshot.definition.evidenceLabel,
    claimBoundary: snapshot.definition.claimBoundary,
    strategies,
    defaultStrategy: strategies.includes("balanced") ? "balanced" : (strategies[0] ?? null),
    allocations,
    kpis,
    resources,
    constraints,
    baseMetrics,
    evidenceNotes,
    sourceFiles: snapshot.definition.files,
  };
}

function mixedOverview(snapshot: LoadedSnapshot): OverviewSnapshot {
  const allocationRows = rows(snapshot, "allocations");
  const kpiRows = rows(snapshot, "kpis");
  const resourceRows = rows(snapshot, "resources");
  const constraintRows = rows(snapshot, "constraints");
  const evidenceRows = rows(snapshot, "evidence");
  const manifest = jsonObject(snapshot, "manifest");
  const policyRows = allocationRows.filter((row) => row.strategy_type === "policy_selection");
  const strategies = unique(policyRows.map((row) => row.strategy_id ?? "").filter(Boolean));
  const currentValues = new Map(
    allocationRows
      .filter((row) => row.strategy_id === "current")
      .map((row) => [row.decision, finiteNumber(row.value ?? "", "current decision")]),
  );
  const currentKpis = new Map(
    kpiRows
      .filter((row) => row.strategy_id === "current")
      .map((row) => [row.kpi, row]),
  );
  const evidenceByKpi = new Map(evidenceRows.map((row) => [row.kpi, row.status]));

  const allocations: AllocationDatum[] = policyRows.map((row) => {
    const current = currentValues.get(row.decision ?? "") ?? 0;
    const recommended = finiteNumber(row.value ?? "", "recommended decision");
    return {
      strategy: row.strategy_id ?? "",
      variable: row.decision ?? "",
      unit: /funding|support/.test(row.decision ?? "") ? "INR" : "configured decision unit",
      current,
      recommended,
      difference: recommended - current,
    };
  });

  const kpis: KpiDatum[] = kpiRows
    .filter((row) => row.strategy_type === "policy_selection")
    .map((row) => {
      const current = currentKpis.get(row.kpi ?? "");
      return {
        strategy: row.strategy_id ?? "",
        kpi: row.kpi ?? "",
        current: finiteNumber(current?.prediction ?? "", "current KPI prediction"),
        currentLower: finiteNumber(current?.lower ?? "", "current KPI lower interval"),
        currentUpper: finiteNumber(current?.upper ?? "", "current KPI upper interval"),
        recommended: finiteNumber(row.prediction ?? "", "recommended KPI prediction"),
        recommendedLower: finiteNumber(row.lower ?? "", "recommended KPI lower interval"),
        recommendedUpper: finiteNumber(row.upper ?? "", "recommended KPI upper interval"),
        evidence: evidenceByKpi.get(row.kpi ?? "") ?? "unknown",
      };
    });

  const resources: ResourceDatum[] = resourceRows
    .filter((row) => row.strategy_type === "policy_selection" || row.strategy_id === "current")
    .flatMap((row) => {
      const budget =
        finiteNumber(row.total_cost ?? "", "total cost") +
        finiteNumber(row.budget_remaining ?? "", "budget remaining");
      return [
        {
          strategy: row.strategy_id ?? "",
          label: "Budget",
          value: finiteNumber(row.total_cost ?? "", "total cost"),
          limit: budget,
          unit: "INR",
        },
        {
          strategy: row.strategy_id ?? "",
          label: "Allocated faculty effort",
          value: finiteNumber(row.allocated_faculty_fte ?? "", "allocated faculty FTE"),
          limit: 0,
          unit: "FTE",
        },
      ];
    });

  const constraints: ConstraintDatum[] = constraintRows
    .filter((row) => strategies.includes(row.strategy_id ?? ""))
    .map((row) => {
      const residual = finiteNumber(row.residual ?? "", "constraint residual");
      return {
        strategy: row.strategy_id ?? "",
        constraint: row.constraint ?? "",
        residual,
        passed: residual <= 1e-9,
      };
    });

  const scenarioCount = new Set(resourceRows.map((row) => row.scenario)).size;
  const comparisonRuns = Number(manifest.completed_comparison_runs ?? 0);
  const evaluations = Number(manifest.matched_candidate_evaluations ?? 0);
  const baseMetrics: MetricDatum[] = [
    {
      label: "Policy views",
      value: String(strategies.length),
      detail: "Saved base-scenario selections",
    },
    {
      label: "Scenario contexts",
      value: String(scenarioCount),
      detail: "Base and stress contexts in the saved package",
    },
    {
      label: "Comparison runs",
      value: String(comparisonRuns),
      detail: `${evaluations} matched candidate evaluations per run`,
    },
    {
      label: "Intervention evidence",
      value: "Synthetic",
      detail: "Public-calibrated but not empirically fitted",
      tone: "warning",
    },
  ];

  const evidenceNotes: EvidenceNote[] = evidenceRows.map((row) => ({
    title: titleCase(row.kpi ?? "Unknown KPI"),
    body: row.claim_boundary ?? "No claim boundary recorded.",
    status:
      row.status === "public_descriptive"
        ? "descriptive"
        : row.status === "unsupported"
          ? "unsupported"
          : "synthetic",
  }));

  return {
    id: snapshot.definition.id,
    label: snapshot.definition.label,
    version: snapshot.definition.version,
    evidenceClass: snapshot.definition.evidenceClass,
    evidenceLabel: snapshot.definition.evidenceLabel,
    claimBoundary: snapshot.definition.claimBoundary,
    strategies,
    defaultStrategy: strategies.includes("policy_balanced")
      ? "policy_balanced"
      : (strategies[0] ?? null),
    allocations,
    kpis,
    resources,
    constraints,
    baseMetrics,
    evidenceNotes,
    sourceFiles: snapshot.definition.files,
  };
}

function empiricalOverview(snapshot: LoadedSnapshot): OverviewSnapshot {
  const coverageRows = rows(snapshot, "coverage");
  const sourceRows = rows(snapshot, "sources");
  const publicOnlyRows = rows(snapshot, "publicOnly");
  const evidenceRows = rows(snapshot, "evidence");

  const countFor = (provenance: string) =>
    coverageRows
      .filter((row) => row.provenance === provenance)
      .reduce((total, row) => total + finiteNumber(row.count ?? "", "coverage count"), 0);

  const publicDescriptive = evidenceRows.filter(
    (row) => row.status === "public_descriptive",
  );
  const baseMetrics: MetricDatum[] = [
    {
      label: "Registered sources",
      value: String(sourceRows.length),
      detail: "Authoritative public snapshots",
    },
    {
      label: "Observed coverage",
      value: String(countFor("observed_public")),
      detail: "Coverage records marked observed_public",
    },
    {
      label: "Derived coverage",
      value: String(countFor("derived_public")),
      detail: "Coverage records marked derived_public",
    },
    {
      label: "Empirical optimizer runs",
      value: "0",
      detail: "No intervention-response optimization exists",
      tone: "warning",
    },
  ];

  const evidenceNotes: EvidenceNote[] = [
    ...publicDescriptive.map((row) => ({
      title: titleCase(row.kpi ?? "Public outcome"),
      body: row.claim_boundary ?? "Descriptive public evidence only.",
      status: "descriptive" as const,
    })),
    {
      title: "Public-only denominator sensitivity",
      body: `${publicOnlyRows.length} saved descriptive checks are available; none is a causal intervention estimate.`,
      status: "descriptive",
    },
    {
      title: "Modeled intervention response",
      body: "Unavailable in the empirical lane. Synthetic scenario models remain segregated in the public + synthetic snapshot.",
      status: "unsupported",
    },
  ];

  return {
    id: snapshot.definition.id,
    label: snapshot.definition.label,
    version: snapshot.definition.version,
    evidenceClass: snapshot.definition.evidenceClass,
    evidenceLabel: snapshot.definition.evidenceLabel,
    claimBoundary: snapshot.definition.claimBoundary,
    strategies: [],
    defaultStrategy: null,
    allocations: [],
    kpis: [],
    resources: [],
    constraints: [],
    baseMetrics,
    evidenceNotes,
    sourceFiles: snapshot.definition.files,
  };
}

export function adaptOverviewSnapshot(snapshot: LoadedSnapshot): OverviewSnapshot {
  switch (snapshot.definition.evidenceClass) {
    case "synthetic_method_fixture":
      return syntheticOverview(snapshot);
    case "public_plus_synthetic_scenario":
      return mixedOverview(snapshot);
    case "empirical_descriptive":
      return empiricalOverview(snapshot);
  }
}
