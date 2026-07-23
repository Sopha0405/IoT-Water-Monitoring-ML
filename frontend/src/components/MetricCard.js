export function MetricCard({ label, value, unit, tone = 'neutral', icon }) {
  return (
    <article className={`metric-card ${tone}`}>
      <div className="metric-label">
        <span className="metric-icon">{icon}</span>
        {label}
      </div>
      <strong>{value}</strong>
      {unit && <span className="metric-unit">{unit}</span>}
    </article>
  );
}
