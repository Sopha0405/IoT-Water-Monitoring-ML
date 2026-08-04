export function BarChart({ data, unit = '', color = 'var(--blue)' }) {
  const max = Math.max(1, ...data.map((item) => item.value));

  if (!data.length) {
    return <div className="empty-chart">Sin datos para graficar.</div>;
  }

  return (
    <div className="bar-chart-h">
      {data.map((item) => {
        const width = Math.max(2, (item.value / max) * 100);
        return (
          <div className="bar-chart-h-row" key={item.label}>
            <span className="bar-chart-h-label" title={item.label}>{item.label}</span>
            <div className="bar-chart-h-track">
              <div
                className="bar-chart-h-fill"
                style={{ width: `${width}%`, background: item.color || color }}
                title={`${item.label}: ${item.value}${unit}`}
              />
            </div>
            <span className="bar-chart-h-value">{item.value}{unit}</span>
          </div>
        );
      })}
    </div>
  );
}
