import { useEffect, useState, type ReactNode } from "react";
import { Icon, type IconName } from "./Icon";

export type PageId =
  | "overview"
  | "scenario-studio"
  | "algorithm-lab"
  | "pareto-explorer"
  | "robustness-lab"
  | "target-cost"
  | "evidence-audit";

const navigation: Array<{ id: PageId; label: string; icon: IconName; phase: string }> = [
  { id: "overview", label: "Overview", icon: "overview", phase: "Ready" },
  { id: "scenario-studio", label: "Scenario Studio", icon: "scenario", phase: "Phase 2" },
  { id: "algorithm-lab", label: "Algorithm Lab", icon: "algorithm", phase: "Phase 3" },
  { id: "pareto-explorer", label: "Pareto Explorer", icon: "pareto", phase: "Phase 3" },
  { id: "robustness-lab", label: "Robustness Lab", icon: "robustness", phase: "Phase 4" },
  { id: "target-cost", label: "Target-Cost Explorer", icon: "target", phase: "Phase 4" },
  { id: "evidence-audit", label: "Evidence & Audit", icon: "evidence", phase: "Phase 5" },
];

export function AppShell({
  page,
  onNavigate,
  title,
  eyebrow,
  children,
}: {
  page: PageId;
  onNavigate: (page: PageId) => void;
  title: string;
  eyebrow: string;
  children: ReactNode;
}) {
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    setMenuOpen(false);
  }, [page]);

  return (
    <div className="app-layout">
      <aside className={`sidebar ${menuOpen ? "sidebar--open" : ""}`} aria-label="Primary">
        <a className="brand" href="#overview" onClick={() => onNavigate("overview")}>
          <span className="brand__mark" aria-hidden="true"><i /><i /><i /></span>
          <span><strong>Beyond Ranking</strong><small>Decision Studio</small></span>
        </a>

        <nav className="navigation">
          <span className="navigation__label">Workspace</span>
          {navigation.map((item) => (
            <a
              key={item.id}
              href={`#${item.id}`}
              className={page === item.id ? "active" : ""}
              aria-current={page === item.id ? "page" : undefined}
              onClick={(event) => {
                event.preventDefault();
                onNavigate(item.id);
              }}
            >
              <Icon name={item.icon} />
              <span>{item.label}</span>
              <small className={item.phase === "Ready" ? "ready" : ""}>{item.phase}</small>
            </a>
          ))}
        </nav>

        <div className="sidebar__footer">
          <a href="./legacy/index.html" target="_blank" rel="noreferrer">
            <span><strong>Legacy artifact viewer</strong><small>Original static dashboard</small></span>
            <Icon name="external" />
          </a>
          <div className="read-only-note"><i />Read-only foundation</div>
        </div>
      </aside>

      {menuOpen ? <button className="sidebar-backdrop" aria-label="Close navigation" onClick={() => setMenuOpen(false)} /> : null}

      <main className="main-content">
        <header className="topbar">
          <button className="icon-button mobile-menu" onClick={() => setMenuOpen(true)} aria-label="Open navigation">
            <Icon name="menu" />
          </button>
          <div>
            <span className="overline">{eyebrow}</span>
            <h1>{title}</h1>
          </div>
          <div className="phase-chip"><i />Foundation · read-only</div>
        </header>
        {children}
      </main>
    </div>
  );
}
