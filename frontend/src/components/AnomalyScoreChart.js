export function AnomalyScoreChart({ analyses }) {
  const width = 1100;
  const height = 240;
  const pad = { top: 18, right: 24, bottom: 34, left: 48 };
  const values = analyses.slice(0, 60).reverse();
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const toX = (index) => pad.left + (index * plotWidth) / Math.max(1, values.length - 1);
  const toY = (score) => pad.top + plotHeight - (Number(score || 0) / 100) * plotHeight;
  const line = values.map((item, index) => `${toX(index)},${toY(item.anomaly_score)}`).join(' ');
  function pointClass(score) {
    if (score >= 85) return '#ff2d4e';
    if (score >= 50) return '#ffb020';
    return '#55b6c4';
  }

  return (
    <div className="influx-chart-wrap risk-chart">
      <svg className="line-chart" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label="Nivel de riesgo">
        <rect className="chart-bg" width={width} height={height} />
        {[0, 50, 85, 100].map((tick) => {
          const y = toY(tick);
          return (
            <g key={tick}>
              <line className="grid-line" x1={pad.left} y1={y} x2={width - pad.right} y2={y} />
              <text className="axis-label y-label" x={pad.left - 12} y={y + 4}>{tick}</text>
            </g>
          );
        })}
        <line className="threshold-line critical" x1={pad.left} y1={toY(85)} x2={width - pad.right} y2={toY(85)} />
        {values.length > 1 && <polyline className="series-line" fill="none" points={line} />}
        {values.map((item, index) => (
          <circle
            key={`${item.id}-${index}`}
            cx={toX(index)}
            cy={toY(item.anomaly_score)}
            r={Number(item.anomaly_score || 0) >= 85 ? 4.2 : 3}
            fill={pointClass(Number(item.anomaly_score || 0))}
          />
        ))}
        <line className="axis-line" x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} />
        <line className="axis-line" x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} />
      </svg>
    </div>
  );
}
