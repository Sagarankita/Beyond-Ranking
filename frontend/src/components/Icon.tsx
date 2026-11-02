import type { ReactNode, SVGProps } from "react";

export type IconName =
  | "overview"
  | "scenario"
  | "algorithm"
  | "pareto"
  | "robustness"
  | "target"
  | "evidence"
  | "menu"
  | "external"
  | "info"
  | "check"
  | "warning";

const paths: Record<IconName, ReactNode> = {
  overview: <><rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/></>,
  scenario: <><path d="M4 18V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v12"/><path d="M8 9h8M8 13h5M3 20h18"/></>,
  algorithm: <><circle cx="6" cy="6" r="3"/><circle cx="18" cy="6" r="3"/><circle cx="12" cy="18" r="3"/><path d="m8.5 7.5 2 7M15.5 7.5l-2 7M9 6h6"/></>,
  pareto: <><path d="M4 19V5M4 19h16"/><circle cx="8" cy="15" r="1.5"/><circle cx="11" cy="11" r="1.5"/><circle cx="15" cy="9" r="1.5"/><circle cx="19" cy="5" r="1.5"/></>,
  robustness: <><path d="M12 3 4.5 6v5c0 4.8 3.2 8.1 7.5 10 4.3-1.9 7.5-5.2 7.5-10V6L12 3Z"/><path d="m8.5 12 2.2 2.2 4.8-5"/></>,
  target: <><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><path d="M12 2v3M22 12h-3M12 22v-3M2 12h3"/></>,
  evidence: <><path d="M6 3h9l3 3v15H6z"/><path d="M14 3v4h4M9 12h6M9 16h6M9 8h2"/></>,
  menu: <><path d="M4 7h16M4 12h16M4 17h16"/></>,
  external: <><path d="M14 4h6v6M20 4l-9 9"/><path d="M18 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h6"/></>,
  info: <><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></>,
  check: <path d="m5 12 4 4L19 6"/>,
  warning: <><path d="M12 3 2.7 20h18.6L12 3Z"/><path d="M12 9v5M12 17h.01"/></>,
};

export function Icon({ name, ...props }: { name: IconName } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {paths[name]}
    </svg>
  );
}
