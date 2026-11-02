import type { EvidenceClass } from "../data/types";

export function EvidenceBadge({
  evidenceClass,
  label,
}: {
  evidenceClass: EvidenceClass;
  label: string;
}) {
  return (
    <span className={`evidence-badge evidence-badge--${evidenceClass}`}>
      <i aria-hidden="true" />
      {label}
    </span>
  );
}
