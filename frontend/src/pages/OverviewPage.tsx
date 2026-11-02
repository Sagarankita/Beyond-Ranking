import { useEffect, useMemo, useState } from "react";
import { adaptOverviewSnapshot } from "../data/adapters";
import { titleCase } from "../data/format";
import { loadCatalog, loadSnapshot } from "../data/loaders";
import type { ArtifactCatalog, OverviewSnapshot } from "../data/types";
import { AllocationChart } from "../components/AllocationChart";
import { ChartPanel } from "../components/ChartPanel";
import { EvidenceBadge } from "../components/EvidenceBadge";
import { ConstraintIndicators, ResourceIndicators } from "../components/Indicators";
import { KpiIntervalChart } from "../components/KpiIntervalChart";
import { MetricCard } from "../components/MetricCard";
import { EmptyState, ErrorState, LoadingState } from "../components/StatePanel";

export function OverviewPage() {
  const [catalog, setCatalog] = useState<ArtifactCatalog | null>(null);
  const [snapshotId, setSnapshotId] = useState<string>("");
  const [overview, setOverview] = useState<OverviewSnapshot | null>(null);
  const [strategy, setStrategy] = useState<string>("");
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    loadCatalog(controller.signal)
      .then((loadedCatalog) => {
        setCatalog(loadedCatalog);
        setSnapshotId((current) => current || loadedCatalog.snapshots[0]?.id || "");
        setError(null);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason : new Error(String(reason)));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [reloadToken]);

  const definition = useMemo(
    () => catalog?.snapshots.find((snapshot) => snapshot.id === snapshotId) ?? null,
    [catalog, snapshotId],
  );

  useEffect(() => {
    if (!definition) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setOverview(null);
    loadSnapshot(definition, controller.signal)
      .then((loaded) => {
        const adapted = adaptOverviewSnapshot(loaded);
        setOverview(adapted);
        setStrategy(adapted.defaultStrategy ?? "");
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason : new Error(String(reason)));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [definition]);

  if (error) return <div className="page"><ErrorState error={error} onRetry={() => setReloadToken((value) => value + 1)} /></div>;
  if (loading || !catalog || !overview) return <div className="page"><LoadingState /></div>;

  const allocations = overview.allocations.filter((row) => row.strategy === strategy);
  const kpis = overview.kpis.filter((row) => row.strategy === strategy);
  const resources = overview.resources.filter((row) => row.strategy === strategy);
  const constraints = overview.constraints.filter((row) => row.strategy === strategy);

  return (
    <div className="page overview-page">
      <section className="overview-hero">
        <div>
          <span className="overline">Versioned saved outputs</span>
          <h2>Evidence-aware allocation overview</h2>
          <p>Compare a persisted reference allocation with saved recommendations. This foundation validates and renders artifacts; it cannot execute an optimizer.</p>
        </div>
        <div className="overview-controls">
          <label>
            Snapshot
            <select value={snapshotId} onChange={(event) => setSnapshotId(event.target.value)}>
              {catalog.snapshots.map((snapshot) => (
                <option key={snapshot.id} value={snapshot.id}>{snapshot.label}</option>
              ))}
            </select>
          </label>
          {overview.strategies.length ? (
            <label>
              Saved strategy
              <select value={strategy} onChange={(event) => setStrategy(event.target.value)}>
                {overview.strategies.map((value) => (
                  <option key={value} value={value}>{titleCase(value)}</option>
                ))}
              </select>
            </label>
          ) : null}
        </div>
      </section>

      <section className={`claim-banner claim-banner--${overview.evidenceClass}`}>
        <EvidenceBadge evidenceClass={overview.evidenceClass} label={overview.evidenceLabel} />
        <p>{overview.claimBoundary}</p>
        <span>{overview.version}</span>
      </section>

      <section className="metric-grid" aria-label="Snapshot summary">
        {overview.baseMetrics.map((metric) => <MetricCard key={metric.label} metric={metric} />)}
      </section>

      <div className="overview-grid overview-grid--primary">
        <ChartPanel
          eyebrow="Decision comparison"
          title="Current vs recommended allocation"
          description="Exact values come from the persisted reporting artifact; bars are normalized only for readable mixed-unit comparison."
          help="No allocation is recomputed in the browser. Select a saved strategy to change the artifact rows shown."
          action={overview.strategies.length ? <span className="source-chip">{allocations.length} saved decisions</span> : null}
        >
          {allocations.length ? (
            <AllocationChart rows={allocations} strategyLabel={titleCase(strategy)} />
          ) : (
            <EmptyState title="No empirical allocation recommendation" body="The empirical evidence snapshot contains descriptive public evidence, not an intervention-response optimizer run." />
          )}
        </ChartPanel>

        <ChartPanel
          eyebrow="Resource envelope"
          title="Utilization"
          description="Budget and faculty indicators use limits recorded in the same saved resource artifact."
          help="An absolute indicator is shown without a utilization bar when the artifact does not record a compatible capacity limit."
        >
          {resources.length ? (
            <ResourceIndicators rows={resources} />
          ) : (
            <EmptyState title="No modeled utilization" body="Resource utilization is unavailable without a saved optimizer allocation." />
          )}
        </ChartPanel>
      </div>

      <div className="overview-grid overview-grid--secondary">
        <ChartPanel
          eyebrow="Model output"
          title="KPI prediction intervals"
          description="Current and recommended predictions are shown with their persisted uncertainty intervals and evidence labels."
          help="These intervals describe model prediction uncertainty. They are not empirical confidence intervals for a causal intervention effect."
        >
          {kpis.length ? (
            <KpiIntervalChart rows={kpis} />
          ) : (
            <EmptyState title="No empirical response intervals" body="Observed public outcomes remain descriptive; synthetic model intervals are not imported into this evidence lane." />
          )}
        </ChartPanel>

        <ChartPanel
          eyebrow="Feasibility"
          title="Constraint status"
          description="Named residuals come directly from the saved evaluator output."
          help="The browser applies the reporting pass threshold to saved residuals. It never evaluates or repairs a candidate."
        >
          {constraints.length ? (
            <ConstraintIndicators rows={constraints} />
          ) : (
            <EmptyState title="No allocation constraints" body="There is no empirical candidate to test in this snapshot." />
          )}
        </ChartPanel>
      </div>

      <section className="evidence-section">
        <header>
          <div><span className="overline">Claim support</span><h2>What this snapshot can—and cannot—say</h2></div>
          <span className="source-chip">{overview.sourceFiles.length} validated files</span>
        </header>
        <div className="evidence-note-grid">
          {overview.evidenceNotes.slice(0, 8).map((note) => (
            <article key={`${note.title}-${note.status}`} className={`evidence-note evidence-note--${note.status}`}>
              <span>{titleCase(note.status)}</span>
              <h3>{note.title}</h3>
              <p>{note.body}</p>
            </article>
          ))}
        </div>
        <details className="provenance-details">
          <summary>Artifact provenance and validation contract</summary>
          <div>
            {overview.sourceFiles.map((file) => (
              <a key={file.id} href={file.url} download>
                <span><strong>{titleCase(file.id)}</strong><small>{file.sourcePath}</small></span>
                <code>{file.sha256.slice(0, 12)}…</code>
              </a>
            ))}
          </div>
        </details>
      </section>
    </div>
  );
}
