export function PageHeader({ title, description, actions }) {
  return (
    <header className="page-header dashboard-hero">
      <div className="page-header-copy">
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="header-actions">{actions}</div>}
    </header>
  );
}

export function DashboardGrid({ children, variant = 'default' }) {
  return (
    <section className={`metrics-grid ${variant === 'secondary' ? 'secondary-metrics' : ''}`}>
      {children}
    </section>
  );
}

export function InfoCard({ label, value, tone = 'neutral' }) {
  return (
    <article className={`info-card ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

export function StatusBadge({ children, tone = 'neutral' }) {
  return (
    <span className={`status-badge ${tone}`}>
      {children}
    </span>
  );
}

export function SectionCard({ title, description, meta, children, className = '' }) {
  return (
    <section className={`panel section-card ${className}`}>
      <div className="panel-heading">
        <div>
          <h2>{title}</h2>
          {description && <p>{description}</p>}
        </div>
        {meta}
      </div>
      {children}
    </section>
  );
}

export function EmptyState({ children }) {
  return <div className="empty-chart empty-state">{children}</div>;
}
