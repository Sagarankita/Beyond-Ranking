import { useEffect, useState } from "react";
import { AppShell, type PageId } from "./components/AppShell";
import { OverviewPage } from "./pages/OverviewPage";
import { PlaceholderPage } from "./pages/PlaceholderPage";

const pageIds: PageId[] = [
  "overview",
  "scenario-studio",
  "algorithm-lab",
  "pareto-explorer",
  "robustness-lab",
  "target-cost",
  "evidence-audit",
];

const pageCopy: Record<Exclude<PageId, "overview">, {
  eyebrow: string;
  title: string;
  icon: Parameters<typeof PlaceholderPage>[0]["icon"];
  phase: string;
  description: string;
  planned: string[];
}> = {
  "scenario-studio": {
    eyebrow: "Configure and execute",
    title: "Scenario Studio",
    icon: "scenario",
    phase: "Prompt 2",
    description: "A guided, backend-generated scenario editor and genuine optimizer submission flow will live here.",
    planned: ["Allowlisted datasets and configurations", "Backend-defined decision variables and constraints", "Durable episodes and run history"],
  },
  "algorithm-lab": {
    eyebrow: "Compare methods",
    title: "Algorithm Lab",
    icon: "algorithm",
    phase: "Prompt 3",
    description: "Authentic per-seed benchmark distributions and compatible run comparisons will be added without inventing convergence history.",
    planned: ["Median and IQR leaderboard", "Per-seed metric distributions", "Valid Wilcoxon/Holm results where available"],
  },
  "pareto-explorer": {
    eyebrow: "Inspect trade-offs",
    title: "Pareto Explorer",
    icon: "pareto",
    phase: "Prompt 3",
    description: "Saved and newly generated candidates will be linked to exact archived rows, allocations, intervals and constraints.",
    planned: ["Selectable supported axes", "Exact candidate provenance", "Pin up to three candidates"],
  },
  "robustness-lab": {
    eyebrow: "Stress assumptions",
    title: "Robustness Lab",
    icon: "robustness",
    phase: "Prompt 4",
    description: "Saved assessment, fixed-allocation stress tests and reoptimization will be kept as three distinct backend-backed operations.",
    planned: ["Feasibility probabilities", "Saved percentile summaries", "Comparable assumption sensitivity"],
  },
  "target-cost": {
    eyebrow: "Reverse optimization",
    title: "Target-Cost Explorer",
    icon: "target",
    phase: "Prompt 4",
    description: "The existing target-cost workflow will be exposed with genuine solver status, supported targets and verified recommendations.",
    planned: ["Backend-supported target definitions", "Minimum modeled cost", "Honest infeasible and unsupported states"],
  },
  "evidence-audit": {
    eyebrow: "Trace and verify",
    title: "Evidence & Audit",
    icon: "evidence",
    phase: "Prompt 5",
    description: "A presentation-friendly audit surface will expose configs, hashes, seeds, accounting and original artifacts.",
    planned: ["Evidence-lane provenance", "Evaluation accounting", "Downloadable verified artifacts"],
  },
};

function pageFromHash(): PageId {
  const candidate = window.location.hash.replace(/^#/, "") as PageId;
  return pageIds.includes(candidate) ? candidate : "overview";
}

export default function App() {
  const [page, setPage] = useState<PageId>(pageFromHash);

  useEffect(() => {
    const onHashChange = () => setPage(pageFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const navigate = (nextPage: PageId) => {
    window.location.hash = nextPage;
    setPage(nextPage);
  };

  if (page === "overview") {
    return (
      <AppShell page={page} onNavigate={navigate} eyebrow="Read-only artifact foundation" title="Overview">
        <OverviewPage />
      </AppShell>
    );
  }

  const copy = pageCopy[page];
  return (
    <AppShell page={page} onNavigate={navigate} eyebrow={copy.eyebrow} title={copy.title}>
      <PlaceholderPage {...copy} />
    </AppShell>
  );
}
