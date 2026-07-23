import { useCallback, useEffect, useMemo, useState } from 'react';

import { MetricCard } from '../components/MetricCard';
import { Pill } from '../components/Pill';
import { apiRequest } from '../lib/api';
import { floors, normalizeFloor, statusClass } from '../lib/constants';

const LIVE_REFRESH_MS = 5000;
const REALTIME_WINDOW_MS = 5 * 60 * 1000;
const CHART_HISTORY_LIMIT = 500;
const MAX_POINTS_PER_SENSOR = 720;

function buildHourlyRows(points) {
  const flowPoints = points
    .filter((point) => point.field === 'flow_lpm')
    .slice()
    .sort((a, b) => new Date(a.time) - new Date(b.time));

  return flowPoints.slice(-12).map((point, index, list) => {
    const previous = list[index - 1]?.value ?? point.value;
    const status = point.value >= 115 ? 'Elevado' : 'Normal';
    return {
      hour: point.time ? new Date(point.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '--:--',
      consumption: Number(point.value || 0).toFixed(1),
      trend: point.value >= previous ? 'up' : 'down',
      status,
    };
  });
}

function buildSensorSeries(points) {
  const colors = ['#55b6c4', '#5aa45d', '#3f8fdd', '#d08a4b', '#8a78c9'];
  const validPoints = points
    .filter((point) => point.field === 'flow_lpm')
    .map((point) => ({ ...point, timestamp: new Date(point.time).getTime(), value: Number(point.value || 0) }))
    .filter((point) => Number.isFinite(point.timestamp) && Number.isFinite(point.value));
  const newestTime = validPoints.length ? Math.max(...validPoints.map((point) => point.timestamp)) : Date.now();
  const liveEnd = newestTime + LIVE_REFRESH_MS;
  const windowStart = liveEnd - REALTIME_WINDOW_MS;
  const grouped = validPoints
    .filter((point) => point.timestamp >= windowStart && point.timestamp <= liveEnd)
    .reduce((acc, point) => {
      const key = point.device_id || 'sensor';
      acc[key] = acc[key] || [];
      acc[key].push(point);
      return acc;
    }, {});

  return Object.entries(grouped).map(([deviceId, values], index) => ({
    deviceId,
    color: colors[index % colors.length],
    points: values
      .slice()
      .sort((a, b) => a.timestamp - b.timestamp)
      .slice(-MAX_POINTS_PER_SENSOR)
      .map((point) => ({
        time: point.time,
        timestamp: point.timestamp,
        value: point.value,
        floor: point.floor,
        site: point.site,
        tenant: point.tenant,
      })),
  }));
}

function niceStep(rawStep) {
  const power = 10 ** Math.floor(Math.log10(rawStep || 1));
  const fraction = rawStep / power;
  if (fraction <= 1) return power;
  if (fraction <= 2) return 2 * power;
  if (fraction <= 5) return 5 * power;
  return 10 * power;
}

function LineChart({ series }) {
  const width = 1000;
  const height = 300;
  const padding = { top: 22, right: 28, bottom: 44, left: 54 };
  const values = series.flatMap((item) => item.points.map((point) => point.value));
  const times = series.flatMap((item) => item.points.map((point) => point.timestamp).filter(Number.isFinite));
  const dataMin = values.length ? Math.min(...values) : 0;
  const dataMax = values.length ? Math.max(...values) : 12;
  const step = niceStep((dataMax - dataMin || 1) / 4);
  const minValue = Math.max(0, Math.floor((dataMin - step) / step) * step);
  const maxValue = Math.max(minValue + step * 4, Math.ceil((dataMax + step) / step) * step);
  const newestTime = times.length ? Math.max(...times) : Date.now();
  const maxTime = newestTime + LIVE_REFRESH_MS;
  const minTime = maxTime - REALTIME_WINDOW_MS;
  const yTicks = Array.from({ length: 5 }, (_, index) => {
    const value = minValue + ((maxValue - minValue) * index) / 4;
    return Math.round(value * 10) / 10;
  }).reverse();
  const xTicks = Array.from({ length: 5 }, (_, index) => minTime + (index * (maxTime - minTime)) / 4);

  function pointFor(point, index, length) {
    const plotWidth = width - padding.left - padding.right;
    const plotHeight = height - padding.top - padding.bottom;
    const pointTime = point.timestamp;
    const x = Number.isFinite(pointTime) && maxTime > minTime
      ? padding.left + ((pointTime - minTime) / (maxTime - minTime)) * plotWidth
      : padding.left + (index * plotWidth) / Math.max(1, length - 1);
    const y = padding.top + plotHeight - ((point.value - minValue) / (maxValue - minValue || 1)) * plotHeight;
    return { x, y };
  }

  function toPolyline(points) {
    if (!points.length) return '';
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
    if (!Number.isFinite(timestamp)) return '';
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  return (
    <div className="influx-chart-wrap">
      <svg
        className="line-chart"
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        role="img"
        aria-label="Grafica de lineas de sensores"
      >
        <rect className="chart-bg" x="0" y="0" width={width} height={height} />
        {yTicks.map((tick) => {
          const y = padding.top + ((maxValue - tick) / (maxValue - minValue || 1)) * (height - padding.top - padding.bottom);
          return (
            <g key={tick}>
              <text className="axis-label y-label" x={padding.left - 14} y={y + 4}>{tick}</text>
              <line className="grid-line" x1={padding.left} y1={y} x2={width - padding.right} y2={y} />
            </g>
          );
        })}

        {xTicks.map((tick, index) => {
          const x = padding.left + (index * (width - padding.left - padding.right)) / Math.max(1, xTicks.length - 1);
          return (
            <g key={tick}>
              <line className="vertical-grid-line" x1={x} y1={padding.top} x2={x} y2={height - padding.bottom} />
              <text className="axis-label x-label" x={x} y={height - 10}>{formatTick(tick)}</text>
            </g>
          );
        })}

        <line className="axis-line" x1={padding.left} y1={padding.top} x2={padding.left} y2={height - padding.bottom} />
        <line className="axis-line" x1={padding.left} y1={height - padding.bottom} x2={width - padding.right} y2={height - padding.bottom} />
        <line className="now-line" x1={width - padding.right} y1={padding.top} x2={width - padding.right} y2={height - padding.bottom} />

        {series.map((item) => (
          <g key={item.deviceId}>
            <path
              className="series-fill"
              d={toAreaPath(item.points)}
              fill={item.color}
            />
            <polyline
              fill="none"
              className="sensor-line"
              stroke={item.color}
              strokeWidth="2.4"
              strokeLinecap="round"
              strokeLinejoin="round"
              points={toPolyline(item.points)}
            />
            {item.points.map((value, index) => {
              const { x, y } = pointFor(value, index, item.points.length);
              return index % 8 === 0 || index === item.points.length - 1
                ? <circle className="line-dot" cx={x} cy={y} r="1.8" fill={item.color} key={`${item.deviceId}-${index}`} />
                : null;
            })}
          </g>
        ))}
      </svg>
    </div>
  );
}

export function ControlPanel({ token }) {
  const [floor, setFloor] = useState('PB');
  const [telemetry, setTelemetry] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [liveNow, setLiveNow] = useState(Date.now());

  const loadTelemetry = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const floorParam = floor === 'Todos' ? '' : `&floor=${encodeURIComponent(floor)}`;
      const data = await apiRequest(`/api/v1/telemetry/latest?field=flow_lpm&limit=${CHART_HISTORY_LIMIT}${floorParam}`, { token });
      setTelemetry(data);
    } catch (err) {
      setError(err.message);
      setTelemetry([]);
    } finally {
      setLoading(false);
    }
  }, [token, floor]);

  useEffect(() => {
    loadTelemetry();
    const timer = setInterval(loadTelemetry, LIVE_REFRESH_MS);
    return () => clearInterval(timer);
  }, [loadTelemetry]);

  useEffect(() => {
    const timer = setInterval(() => setLiveNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const floorPoints = useMemo(() => telemetry.filter((point) => {
    if (floor === 'Todos') return true;
    return normalizeFloor(point.floor) === floor;
  }), [telemetry, floor]);

  const flowValues = floorPoints.filter((point) => point.field === 'flow_lpm').map((point) => Number(point.value || 0));
  const latestValue = flowValues[0] ?? 0;
  const average = flowValues.length ? flowValues.reduce((sum, value) => sum + value, 0) / flowValues.length : 0;
  const monthly = average * 60 * 24 * 30 / 1000;
  const amount = monthly * 40;
  const systemState = latestValue >= 115 ? 'Fuga posible' : 'Sistema Normal';
  const hourlyRows = buildHourlyRows(floorPoints);
  const sensorSeries = useMemo(() => buildSensorSeries(floorPoints), [floorPoints]);
  const newestPointTime = sensorSeries
    .flatMap((item) => item.points.map((point) => point.timestamp))
    .filter(Number.isFinite)
    .reduce((latest, timestamp) => Math.max(latest, timestamp), 0);
  const secondsSinceLastPoint = newestPointTime ? Math.max(0, Math.round((liveNow - newestPointTime) / 1000)) : null;

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Resumen</h1>
          <p>Lecturas actuales del edificio</p>
        </div>
        <button className="primary-action" onClick={loadTelemetry} disabled={loading}>
          {loading ? 'Actualizando...' : 'Actualizar ahora'}
        </button>
      </header>

      <section className="toolbar compact">
        <label>
          Filtrar por piso
          <select value={floor} onChange={(event) => setFloor(event.target.value)}>
            {floors.map((item) => <option key={item}>{item}</option>)}
          </select>
        </label>
      </section>

      {error && <div className="form-error page-error">InfluxDB: {error}</div>}

      <section className="metrics-grid">
        <MetricCard label="Lectura actual" value={latestValue.toFixed(1)} unit="L/min" />
        <MetricCard label="Consumo mensual" value={monthly.toFixed(1)} unit="m3" />
        <MetricCard label="Importe estimado" value={amount.toFixed(2)} unit="Bs" tone="money" />
        <MetricCard label="Estado" value={systemState} tone={systemState === 'Sistema Normal' ? 'ok' : 'critical'} />
      </section>

      <section className="panel chart-panel">
        <div className="panel-heading">
          <div>
            <h2>Consumo por sensor</h2>
            <p>
              Ventana movil de 5 minutos
              {secondsSinceLastPoint !== null && ` - ultima lectura hace ${secondsSinceLastPoint}s`}
            </p>
          </div>
          <div className="live-indicator"><i /> En vivo</div>
        </div>
        {sensorSeries.length ? (
          <>
            <LineChart series={sensorSeries} />
            <div className="chart-legend-bottom">
              <span className="axis-legend-title">Sensores</span>
              {sensorSeries.map((item) => (
                <span key={item.deviceId}><i style={{ background: item.color }} /> {item.deviceId}</span>
              ))}
            </div>
          </>
        ) : (
          <div className="empty-chart">Sin lecturas para graficar.</div>
        )}
      </section>

      <section className="panel table-panel">
        <h2>Registro por Hora - {floor}</h2>
        <table>
          <thead>
            <tr>
              <th>Hora</th>
              <th>Consumo (L)</th>
              <th>Tendencia</th>
              <th>Estado</th>
            </tr>
          </thead>
          <tbody>
            {hourlyRows.map((row, index) => (
              <tr key={`${row.hour}-${index}`}>
                <td>{row.hour}</td>
                <td>{row.consumption}</td>
                <td><span className={`trend ${row.trend}`}>{row.trend === 'up' ? 'up' : 'down'}</span></td>
                <td><Pill tone={statusClass(row.status)}>{row.status}</Pill></td>
              </tr>
            ))}
            {!hourlyRows.length && (
              <tr>
                <td colSpan="4">Sin datos de InfluxDB para este filtro.</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </>
  );
}
