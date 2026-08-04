const REALTIME_WINDOW_MS = 5 * 60 * 1000;
const LIVE_REFRESH_MS = 5000;
const MAX_POINTS_PER_SENSOR = 720;

const SENSOR_COLORS = ['#0b5d86', '#f5a623', '#2e9d72', '#76b4d2', '#98a2b3', '#d64545'];

function niceStep(rawStep) {
  const power = 10 ** Math.floor(Math.log10(rawStep || 1));
  const fraction = rawStep / power;
  if (fraction <= 1) return power;
  if (fraction <= 2) return 2 * power;
  if (fraction <= 5) return 5 * power;
  return 10 * power;
}

export function buildSensorSeries(points, now = Date.now()) {
  const newestTime = points.length ? Math.max(...points.map((point) => point.timestamp)) : now;
  const liveEnd = Math.max(now, newestTime) + LIVE_REFRESH_MS;
  const windowStart = liveEnd - REALTIME_WINDOW_MS;
  const grouped = points
    .filter((point) => point.field === 'flow_lpm')
    .filter((point) => point.timestamp >= windowStart && point.timestamp <= liveEnd)
    .reduce((acc, point) => {
      const key = point.device_id || 'sensor';
      acc[key] = acc[key] || [];
      acc[key].push(point);
      return acc;
    }, {});

  return Object.entries(grouped).map(([deviceId, values], index) => ({
    deviceId,
    color: SENSOR_COLORS[index % SENSOR_COLORS.length],
    points: values
      .slice()
      .sort((a, b) => a.timestamp - b.timestamp)
      .slice(-MAX_POINTS_PER_SENSOR),
  }));
}

export function FlowLineChart({ series, now = Date.now() }) {
  const width = 1000;
  const height = 320;
  const padding = { top: 22, right: 34, bottom: 46, left: 58 };
  const values = series.flatMap((item) => item.points.map((point) => point.value));
  const times = series.flatMap((item) => item.points.map((point) => point.timestamp));
  const dataMin = values.length ? Math.min(...values) : 0;
  const dataMax = values.length ? Math.max(...values) : 12;
  const step = niceStep((dataMax - dataMin || 1) / 4);
  const minValue = Math.max(0, Math.floor((dataMin - step) / step) * step);
  const maxValue = Math.max(minValue + step * 4, Math.ceil((dataMax + step) / step) * step);
  const newestTime = times.length ? Math.max(...times) : now;
  const maxTime = Math.max(now, newestTime) + LIVE_REFRESH_MS;
  const minTime = maxTime - REALTIME_WINDOW_MS;
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const yTicks = Array.from({ length: 5 }, (_, index) => {
    const value = minValue + ((maxValue - minValue) * index) / 4;
    return Math.round(value * 10) / 10;
  }).reverse();
  const xTicks = Array.from({ length: 5 }, (_, index) => minTime + (index * (maxTime - minTime)) / 4);

  function pointFor(point, index, length) {
    const x = Number.isFinite(point.timestamp) && maxTime > minTime
      ? padding.left + ((point.timestamp - minTime) / (maxTime - minTime)) * plotWidth
      : padding.left + (index * plotWidth) / Math.max(1, length - 1);
    const y = padding.top + plotHeight - ((point.value - minValue) / (maxValue - minValue || 1)) * plotHeight;
    return { x, y };
  }

  function toPolyline(points) {
    return points.map((point, index) => {
      const { x, y } = pointFor(point, index, points.length);
      return `${x},${y}`;
    }).join(' ');
  }

  function toAreaPath(points) {
    if (!points.length) return '';
    const line = points.map((point, index) => {
      const { x, y } = pointFor(point, index, points.length);
      return `${index === 0 ? 'M' : 'L'} ${x},${y}`;
    }).join(' ');
    const first = pointFor(points[0], 0, points.length);
    const last = pointFor(points[points.length - 1], points.length - 1, points.length);
    return `${line} L ${last.x},${height - padding.bottom} L ${first.x},${height - padding.bottom} Z`;
  }

  function formatTick(timestamp) {
    return new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  return (
    <div className="influx-chart-wrap flow-chart-wrap">
      <svg
        className="line-chart flow-line-chart"
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        role="img"
        aria-label="Caudal en tiempo real por sensor"
      >
        <rect className="chart-bg" x="0" y="0" width={width} height={height} />
        {yTicks.map((tick) => {
          const y = padding.top + ((maxValue - tick) / (maxValue - minValue || 1)) * plotHeight;
          return (
            <g key={tick}>
              <text className="axis-label y-label" x={padding.left - 14} y={y + 4}>{tick}</text>
              <line className="grid-line" x1={padding.left} y1={y} x2={width - padding.right} y2={y} />
            </g>
          );
        })}
        {xTicks.map((tick, index) => {
          const x = padding.left + (index * plotWidth) / Math.max(1, xTicks.length - 1);
          return (
            <g key={tick}>
              <line className="vertical-grid-line" x1={x} y1={padding.top} x2={x} y2={height - padding.bottom} />
              <text className="axis-label x-label" x={x} y={height - 12}>{formatTick(tick)}</text>
            </g>
          );
        })}
        <line className="axis-line" x1={padding.left} y1={padding.top} x2={padding.left} y2={height - padding.bottom} />
        <line className="axis-line" x1={padding.left} y1={height - padding.bottom} x2={width - padding.right} y2={height - padding.bottom} />
        <line className="now-line" x1={width - padding.right} y1={padding.top} x2={width - padding.right} y2={height - padding.bottom} />
        {series.map((item) => (
          <g key={item.deviceId}>
            <path className="series-fill" d={toAreaPath(item.points)} fill={item.color} />
            <polyline
              fill="none"
              className="sensor-line"
              stroke={item.color}
              strokeWidth="2.6"
              strokeLinecap="round"
              strokeLinejoin="round"
              points={toPolyline(item.points)}
            />
            {item.points.map((point, index) => {
              if (index % 10 !== 0 && index !== item.points.length - 1) return null;
              const { x, y } = pointFor(point, index, item.points.length);
              const isLast = index === item.points.length - 1;
              return (
                <g key={`${item.deviceId}-${index}`}>
                  {isLast && <circle className="live-pulse" cx={x} cy={y} r="3.5" fill={item.color} />}
                  <circle className="line-dot" cx={x} cy={y} r={isLast ? 3.4 : 1.8} fill={item.color} />
                </g>
              );
            })}
          </g>
        ))}
      </svg>
    </div>
  );
}
