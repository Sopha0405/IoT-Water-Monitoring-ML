export function DonutChart({ data, centerLabel, centerValue }) {
  const total = data.reduce((sum, item) => sum + item.value, 0);

  if (!total) {
    return <div className="empty-chart">Sin datos para graficar.</div>;
  }

  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  const segments = data.map((item) => {
    const fraction = item.value / total;
    const dash = fraction * circumference;
    const segment = {
      ...item,
      fraction,
      dashArray: `${dash} ${circumference - dash}`,
      dashOffset: -offset,
    };
    offset += dash;
    return segment;
  });

  return (
    <div className="donut-chart-wrap">
      <svg className="donut-chart" viewBox="0 0 100 100" role="img" aria-label="Distribucion">
        <circle className="donut-track" cx="50" cy="50" r={radius} />
        {segments.map((segment) => (
          <circle
            key={segment.label}
            cx="50"
            cy="50"
            r={radius}
            fill="none"
            stroke={segment.color}
            strokeWidth="14"
            strokeDasharray={segment.dashArray}
            strokeDashoffset={segment.dashOffset}
            transform="rotate(-90 50 50)"
            strokeLinecap="butt"
          >
            <title>{`${segment.label}: ${segment.value} (${(segment.fraction * 100).toFixed(0)}%)`}</title>
          </circle>
        ))}
        <text x="50" y="47" textAnchor="middle" className="donut-center-value">{centerValue ?? total}</text>
        <text x="50" y="61" textAnchor="middle" className="donut-center-label">{centerLabel || 'Total'}</text>
      </svg>
      <ul className="donut-legend">
        {data.map((item) => (
          <li key={item.label}>
            <i style={{ background: item.color }} />
            <span>{item.label}</span>
            <strong>{total ? `${((item.value / total) * 100).toFixed(0)}%` : '0%'}</strong>
          </li>
        ))}
      </ul>
    </div>
  );
}
