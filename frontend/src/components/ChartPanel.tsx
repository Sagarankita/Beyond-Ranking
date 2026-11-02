import type { ReactNode } from "react";
import { Icon } from "./Icon";

export function ChartPanel({
  eyebrow,
  title,
  description,
  help,
  action,
  children,
  className = "",
}: {
  eyebrow: string;
  title: string;
  description: string;
  help?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`chart-panel ${className}`}>
      <header className="chart-panel__header">
        <div>
          <span className="overline">{eyebrow}</span>
          <div className="title-with-help">
            <h2>{title}</h2>
            {help ? (
              <span className="help-tip" tabIndex={0} aria-label={help} data-tooltip={help}>
                <Icon name="info" />
              </span>
            ) : null}
          </div>
          <p>{description}</p>
        </div>
        {action ? <div className="chart-panel__action">{action}</div> : null}
      </header>
      <div className="chart-panel__body">{children}</div>
    </section>
  );
}
