import type { ConstraintDatum, ResourceDatum } from "../data/types";
import { formatValue, titleCase } from "../data/format";
import { Icon } from "./Icon";

export function ResourceIndicators({ rows }: { rows: ResourceDatum[] }) {
  return (
    <div className="indicator-stack">
      {rows.map((row) => {
        const ratio = row.limit > 0 ? row.value / row.limit : null;
        return (
          <div className="resource-indicator" key={`${row.strategy}-${row.label}`}>
            <div>
              <span>{row.label}</span>
              <strong>{formatValue(row.value, row.unit)}</strong>
            </div>
            {ratio === null ? (
              <p>Saved absolute allocation</p>
            ) : (
              <>
                <div className="progress-track" aria-label={`${row.label} ${Math.round(ratio * 100)} percent utilized`}>
                  <i className={ratio > 1 ? "over" : ""} style={{ width: `${Math.min(100, ratio * 100)}%` }} />
                </div>
                <p>{(ratio * 100).toFixed(1)}% of {formatValue(row.limit, row.unit)}</p>
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function ConstraintIndicators({ rows }: { rows: ConstraintDatum[] }) {
  const passed = rows.filter((row) => row.passed).length;
  const failed = rows.length - passed;
  const mostCritical = [...rows].sort((left, right) => right.residual - left.residual).slice(0, 4);
  return (
    <div className="constraint-summary">
      <div className="constraint-tally">
        <span className="constraint-tally__icon"><Icon name={failed ? "warning" : "check"} /></span>
        <div><strong>{passed} / {rows.length}</strong><p>named constraints passed</p></div>
        <span className={failed ? "status-pill status-pill--warning" : "status-pill"}>{failed ? `${failed} failed` : "Feasible"}</span>
      </div>
      <div className="constraint-list">
        {mostCritical.map((row) => (
          <div key={`${row.strategy}-${row.constraint}`}>
            <span>{titleCase(row.constraint)}</span>
            <code>{row.residual.toExponential(2)}</code>
          </div>
        ))}
      </div>
      <p className="chart-footnote">Residual ≤ 1×10⁻⁹ is the persisted reporting pass rule; no candidate is reevaluated in the browser.</p>
    </div>
  );
}
