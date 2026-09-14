import Link from "next/link";

import { titleCase } from "@/lib/format";

export function PageHeader({ eyebrow, title, description, actions }: Readonly<{ eyebrow?: string; title: string; description: string; actions?: React.ReactNode }>) {
  return (
    <header className="page-header">
      <div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}<h1>{title}</h1><p>{description}</p></div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}

export function Panel({ title, eyebrow, action, children, className = "" }: Readonly<{ title?: string; eyebrow?: string; action?: React.ReactNode; children: React.ReactNode; className?: string }>) {
  return (
    <section className={`panel ${className}`.trim()}>
      {(title || action) && <header className="panel-header"><div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}{title && <h2>{title}</h2>}</div>{action}</header>}
      {children}
    </section>
  );
}

export function MetricCard({ label, value, note, tone = "default" }: Readonly<{ label: string; value: string | number; note?: string; tone?: string }>) {
  return <article className={`metric-card ${tone}`}><span>{label}</span><strong>{value}</strong>{note && <small>{note}</small>}</article>;
}

export function StatusBadge({ value }: Readonly<{ value: string | null | undefined }>) {
  const safeValue = value ?? "not_available";
  const tone = ["completed", "approved", "auto_complete", "low", "full"].includes(safeValue)
    ? "positive"
    : ["failed", "rejected", "block_and_escalate", "critical", "blocked"].includes(safeValue)
      ? "critical"
      : ["pending_review", "pending", "require_human_review", "high"].includes(safeValue)
        ? "review"
        : ["complete_with_warning", "medium", "degraded", "revision_requested"].includes(safeValue)
          ? "warning"
          : "neutral";
  return <span className={`status-badge ${tone}`}>{titleCase(safeValue)}</span>;
}

export function LoadingState({ label = "Loading workspace" }: Readonly<{ label?: string }>) {
  return <div className="state-card" role="status"><span className="spinner" /><strong>{label}</strong><p>Reading the current backend state.</p></div>;
}

export function ErrorState({ title = "Unable to load this view", message, requestId, retry }: Readonly<{ title?: string; message: string; requestId?: string | null; retry?: () => void }>) {
  return <div className="state-card error" role="alert"><strong>{title}</strong><p>{message}</p>{requestId && <code>Request ID: {requestId}</code>}{retry && <button className="button secondary" onClick={retry}>Try again</button>}</div>;
}

export function EmptyState({ title, description, actionHref, actionLabel }: Readonly<{ title: string; description: string; actionHref?: string; actionLabel?: string }>) {
  return <div className="state-card"><span className="empty-mark" aria-hidden="true">◇</span><strong>{title}</strong><p>{description}</p>{actionHref && actionLabel && <Link className="button secondary" href={actionHref}>{actionLabel}</Link>}</div>;
}

export function DefinitionList({ items }: Readonly<{ items: Array<{ label: string; value: React.ReactNode }> }>) {
  return <dl className="definition-list">{items.map((item) => <div key={item.label}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}</dl>;
}

export function BarList({ items }: Readonly<{ items: Array<{ label: string; value: number; tone?: string }> }>) {
  const max = Math.max(...items.map((item) => item.value), 1);
  return <div className="bar-list">{items.map((item) => <div className="bar-row" key={item.label}><div className="bar-label"><span>{titleCase(item.label)}</span><strong>{item.value}</strong></div><div className="bar-track" aria-label={`${titleCase(item.label)}: ${item.value}`}><span className={item.tone ?? ""} style={{ width: `${Math.max((item.value / max) * 100, item.value ? 4 : 0)}%` }} /></div></div>)}</div>;
}
