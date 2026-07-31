import { useMemo, useState } from 'react';

import { FloorSelector } from '../components/FloorSelector';
import { FlowHistoryTable, buildHourlyRows } from '../components/FlowHistoryTable';
import { FlowLineChart, buildSensorSeries } from '../components/FlowLineChart';
import { MetricCard } from '../components/MetricCard';
import { useLiveTelemetry } from '../hooks/useLiveTelemetry';
import { floors } from '../lib/constants';

function formatAge(seconds) {
  if (seconds === null) return 'sin lecturas';
  if (seconds < 60) return `hace ${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `hace ${minutes} min`;
}

function sumValues(values) {
  return values.reduce((sum, value) => sum + value, 0);
}

export function ControlPanel({ token }) {
  const [floor, setFloor] = useState('PB');
  const {
    points,
    latestPoint,
    source,
    loading,
    error,
    now,
    refresh,
  } = useLiveTelemetry(token, { floor });

  const flowValues = useMemo(
    () => points.filter((point) => point.field === 'flow_lpm').map((point) => point.value),
    [points],
  );
  const latestValue = latestPoint?.field === 'flow_lpm' ? latestPoint.value : flowValues.at(-1) ?? 0;
  const average = flowValues.length ? sumValues(flowValues) / flowValues.length : 0;
  const peak = flowValues.length ? Math.max(...flowValues) : 0;
  const monthly = average * 60 * 24 * 30 / 1000;
  const amount = monthly * 40;
  const systemState = latestValue >= 20 || peak >= 25 ? 'Revisar consumo' : 'Sistema Normal';
  const sensorSeries = useMemo(() => buildSensorSeries(points, now), [points, now]);
  const hourlyRows = useMemo(() => buildHourlyRows(points), [points]);
  const secondsSinceLastPoint = latestPoint
    ? Math.max(0, Math.round((now - latestPoint.timestamp) / 1000))
    : null;
  const isRealLive = source === 'real' && secondsSinceLastPoint !== null && secondsSinceLastPoint <= 15;
  const liveLabel = source === 'demo'
    ? 'Datos demo'
    : isRealLive
      ? 'En vivo'
      : 'Sin datos reales';
  const connectionTone = isRealLive ? 'good' : source === 'demo' ? 'warn' : 'bad';
  const latestSensor = latestPoint?.device_id || '-';
  const latestSource = source === 'real' ? 'InfluxDB real' : source === 'demo' ? 'Fallback demo' : 'Sin fuente';

  return (
    <>
      <header className="page-header dashboard-hero">
        <div>
          <h1>Resumen</h1>
          <p>Monitoreo de caudal, consumo y alertas ML en streaming</p>
        </div>
        <button className="primary-action" onClick={refresh} disabled={loading}>
          {loading ? 'Actualizando...' : 'Actualizar ahora'}
        </button>
      </header>

      <section className="quick-status-strip">
        <div className={`connection-chip ${connectionTone}`}>
          <i />
          <span>{liveLabel}</span>
        </div>
        <div>
          <span>Sensor</span>
          <strong>{latestSensor}</strong>
        </div>
        <div>
          <span>Ultima lectura</span>
          <strong>{formatAge(secondsSinceLastPoint)}</strong>
        </div>
        <div>
          <span>Fuente</span>
          <strong>{latestSource}</strong>
        </div>
      </section>

      <section className="toolbar compact dashboard-toolbar">
        <div>
          <span className="control-label">Piso</span>
          <FloorSelector floors={floors} value={floor} onChange={setFloor} />
        </div>
      </section>

      {error && <div className="form-error page-error">InfluxDB: {error}</div>}
      {source !== 'real' && (
        <div className={`status-banner ${source === 'demo' ? 'warning' : 'danger'}`}>
          {source === 'demo'
            ? 'Mostrando datos demo porque InfluxDB no devolvio telemetria real para este filtro.'
            : 'No hay lecturas reales disponibles para este filtro.'}
        </div>
      )}

      <section className="metrics-grid">
        <MetricCard icon="water_drop" label="Lectura actual" value={latestValue.toFixed(2)} unit="L/min" tone="blue" />
        <MetricCard icon="timeline" label="Promedio ventana" value={average.toFixed(2)} unit="L/min" />
        <MetricCard icon="speed" label="Pico reciente" value={peak.toFixed(2)} unit="L/min" tone={peak >= 25 ? 'critical' : 'blue'} />
        <MetricCard icon="verified" label="Estado" value={systemState} tone={systemState === 'Sistema Normal' ? 'ok' : 'warning'} />
      </section>

      <section className="panel chart-panel">
        <div className="panel-heading">
          <div>
            <h2>Caudal por sensor</h2>
            <p>Ventana movil de 5 minutos - ultima lectura {formatAge(secondsSinceLastPoint)}</p>
          </div>
          <div className={`live-indicator ${isRealLive ? 'online' : 'stale'}`}>
            <i /> {liveLabel}
          </div>
        </div>
        {sensorSeries.length ? (
          <>
            <FlowLineChart series={sensorSeries} now={now} />
            <div className="chart-legend-bottom">
              <span className="axis-legend-title">Sensores</span>
              {sensorSeries.map((item) => {
                const last = item.points.at(-1);
                return (
                  <span key={item.deviceId}>
                    <i style={{ background: item.color }} /> {item.deviceId}
                    {last ? ` ${last.value.toFixed(2)} L/min` : ''}
                  </span>
                );
              })}
            </div>
          </>
        ) : (
          <div className="empty-chart">Sin lecturas para graficar.</div>
        )}
      </section>

      <section className="metrics-grid secondary-metrics">
        <MetricCard icon="calendar_month" label="Consumo mensual estimado" value={monthly.toFixed(1)} unit="m3" />
        <MetricCard icon="payments" label="Importe estimado" value={amount.toFixed(2)} unit="Bs" tone="money" />
        <MetricCard icon="database" label="Lecturas cargadas" value={flowValues.length} />
        <MetricCard icon="sensors" label="Sensores visibles" value={sensorSeries.length} />
      </section>

      <FlowHistoryTable floor={floor} rows={hourlyRows} />
    </>
  );
}
