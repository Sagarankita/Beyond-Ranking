import type { IconName } from "../components/Icon";
import { Icon } from "../components/Icon";

export function PlaceholderPage({
  icon,
  phase,
  title,
  description,
  planned,
}: {
  icon: IconName;
  phase: string;
  title: string;
  description: string;
  planned: string[];
}) {
  return (
    <div className="page placeholder-page">
      <section className="placeholder-card">
        <span className="placeholder-card__icon"><Icon name={icon} /></span>
        <div className="placeholder-card__content">
          <span className="overline">{phase} · not executable yet</span>
          <h2>{title}</h2>
          <p>{description}</p>
          <div className="planned-list">
            {planned.map((item) => <div key={item}><Icon name="check" /><span>{item}</span></div>)}
          </div>
          <div className="placeholder-warning"><Icon name="warning" /><span>No editable control on this page starts backend work in Prompt 1. Execution will be added only through a validated Python API in the later phase.</span></div>
        </div>
      </section>
    </div>
  );
}
