import type { MetricDatum } from "../data/types";

export function MetricCard({ metric }: { metric: MetricDatum }) {
  return (
    <article className={`metric-card metric-card--${metric.tone ?? "default"}`}>
      <span>{metric.label}</span>
      <strong>{metric.value}</strong>
      <p>{metric.detail}</p>
    </article>
  );
}
