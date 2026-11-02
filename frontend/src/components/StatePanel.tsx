import { Icon } from "./Icon";

export function LoadingState({ label = "Validating saved artifacts…" }: { label?: string }) {
  return (
    <div className="state-panel" role="status">
      <span className="loader" aria-hidden="true" />
      <strong>{label}</strong>
      <p>Checking columns, values, hashes and evidence metadata.</p>
    </div>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="state-panel state-panel--empty">
      <span className="state-panel__icon"><Icon name="info" /></span>
      <strong>{title}</strong>
      <p>{body}</p>
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <div className="state-panel state-panel--error" role="alert">
      <span className="state-panel__icon"><Icon name="warning" /></span>
      <strong>Artifact validation failed</strong>
      <p>{error.message}</p>
      {onRetry ? <button className="button button--secondary" onClick={onRetry}>Retry</button> : null}
    </div>
  );
}
