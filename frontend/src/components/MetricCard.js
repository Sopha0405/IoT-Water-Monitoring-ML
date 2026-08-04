import { memo } from 'react';

export const MetricCard = memo(function MetricCard({ label, value, unit, tone = 'neutral', icon }) {
  return (
    <article className={`metric-card ${tone}`}>
      <div className="metric-label">
        {icon && <span className="material-symbols-outlined metric-icon" aria-hidden="true">{icon}</span>}
        {label}
      </div>
      <strong>{value}</strong>
      {unit && <span className="metric-unit">{unit}</span>}
    </article>
  );
});
