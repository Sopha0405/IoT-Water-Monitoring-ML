import { useMemo, useState } from 'react';

import { FloorSelector } from '../components/FloorSelector';
import { FlowHistoryTable, buildHourlyRows } from '../components/FlowHistoryTable';
import { FlowLineChart, buildSensorSeries } from '../components/FlowLineChart';
import { MetricCard } from '../components/MetricCard';
import {
  DashboardGrid,
  EmptyState,
  InfoCard,
  PageHeader,
  SectionCard,
  StatusBadge,
} from '../components/dashboard/DashboardPrimitives';
import { useLiveTelemetry } from '../hooks/useLiveTelemetry';
import { floors } from '../lib/constants';

const billingReference = {
  consumptionM3: 318,
  potableWaterAmount: 3766.25,
  sewerAmount: 3014.50,
};

const numberFormatter = new Intl.NumberFormat('es-BO', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function formatDecimal(value, fractionDigits = 2) {
  return new Intl.NumberFormat('es-BO', {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value);
}

function formatCurrency(value) {
  return `Bs ${numberFormatter.format(value)}`;
}

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
  const potableWaterRate = billingReference.potableWaterAmount / billingReference.consumptionM3;
  const sewerRate = billingReference.sewerAmount / billingReference.consumptionM3;
  const totalRate = potableWaterRate + sewerRate;
  const amount = monthly * totalRate;
  const systemState = latestValue >= 20 || peak >= 25 ? 'Revisar consumo' : 'Sistema Normal';
  const sensorSeries = useMemo(() => buildSensorSeries(points, now), [points, now]);
  const hourlyRows = useMemo(() => buildHourlyRows(points), [points]);
  const hasChartData = sensorSeries.some((item) => item.points.length);
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

  const headerActions = (
    <>
      <div>
        <span className="control-label">Piso</span>
        <FloorSelector floors={floors} value={floor} onChange={setFloor} />
      </div>
      <button className="secondary-action" onClick={refresh} disabled={loading}>
        {loading ? 'Actualizando...' : 'Actualizar informacion'}
      </button>
    </>
  );

  return (
    <div className={`dashboard-view ${loading ? 'is-updating' : ''}`}>
      <PageHeader
        title="Panel de monitoreo"
        description="Resumen operativo del consumo de agua y estado del sistema."
        actions={headerActions}
      />

      <section className="quick-status-strip" aria-busy={loading}>
        <InfoCard
          label="Estado"
          value={<StatusBadge tone={connectionTone}>{liveLabel}</StatusBadge>}
          tone={connectionTone}
        />
        <InfoCard label="Sensor" value={latestSensor} />
        <InfoCard label="Ultima lectura" value={formatAge(secondsSinceLastPoint)} />
        <InfoCard label="Fuente" value={latestSource} />
      </section>

      {error && <div className="form-error page-error">No fue posible completar la operacion: {error}</div>}
      {source !== 'real' && (
        <div className={`status-banner ${source === 'demo' ? 'warning' : 'danger'}`}>
          {source === 'demo'
            ? 'Mostrando datos demo porque InfluxDB no devolvio telemetria real para este filtro.'
            : 'No se encontraron registros reales para el periodo seleccionado.'}
        </div>
      )}

      <DashboardGrid>
        <MetricCard label="Consumo actual" value={latestValue.toFixed(2)} unit="L/min" tone="blue" />
        <MetricCard label="Consumo promedio" value={average.toFixed(2)} unit="L/min" />
        <MetricCard label="Pico de consumo" value={peak.toFixed(2)} unit="L/min" tone={peak >= 25 ? 'critical' : 'blue'} />
        <MetricCard label="Estado del sistema" value={systemState} tone={systemState === 'Sistema Normal' ? 'ok' : 'warning'} />
      </DashboardGrid>

      <SectionCard
        title="Caudal por sensor"
        description={`Ventana movil de 5 minutos - ultima lectura ${formatAge(secondsSinceLastPoint)}`}
        className="chart-panel"
        meta={(
          <div className={`live-indicator ${isRealLive ? 'online' : 'stale'}`}>
            <i /> {liveLabel}
          </div>
        )}
      >
        <div className="chart-stage">
          <FlowLineChart series={sensorSeries} now={now} />
          {!hasChartData && (
            <EmptyState>No se encontraron registros para el periodo seleccionado.</EmptyState>
          )}
        </div>
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
          {!sensorSeries.length && <span>Sin sensores visibles</span>}
        </div>
      </SectionCard>

      <DashboardGrid variant="secondary">
        <MetricCard label="Consumo mensual estimado" value={formatDecimal(monthly, 1)} unit="m³" />
        <MetricCard label="Importe estimado" value={formatCurrency(amount)} tone="money" />
        <MetricCard label="Costo referencial" value={formatCurrency(totalRate)} unit="por m³" />
        <MetricCard label="Lecturas cargadas" value={flowValues.length} />
        <MetricCard label="Sensores visibles" value={sensorSeries.length} />
      </DashboardGrid>

      <FlowHistoryTable floor={floor} rows={hourlyRows} />
    </div>
  );
}
