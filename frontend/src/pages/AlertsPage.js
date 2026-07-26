import { useCallback, useEffect, useMemo, useState } from 'react';

import { ActionPopcard } from '../components/ActionPopcard';
import { MetricCard } from '../components/MetricCard';
import { Pill } from '../components/Pill';
import {
  getAlerts,
  submitAlertFeedback,
  updateAlertStatus,
} from '../services/mlAdminService';
import { floors, normalizeFloor } from '../lib/constants';

const statusLabels = {
  open: 'Activa',
  acknowledged: 'Reconocida',
  reviewing: 'En revision',
  confirmed_leak: 'Fuga confirmada',
  false_positive: 'Falsa alerta',
  resolved: 'Resuelta',
  closed: 'Cerrada',
  attended: 'Atendida',
  investigating: 'Investigando',
  possible: 'Posible',
};

const statusOptions = [
  ['acknowledged', 'Reconocer alerta'],
  ['reviewing', 'Poner en revision'],
  ['confirmed_leak', 'Confirmar fuga'],
  ['false_positive', 'Marcar falsa alerta'],
  ['resolved', 'Resolver'],
  ['closed', 'Cerrar'],
];

function formatDate(value) {
  if (!value) return '-';
  return String(value).replace('T', ' ').slice(0, 16);
}

function numberValue(...values) {
  const found = values.find((value) => value !== undefined && value !== null && value !== '');
  const parsed = Number(found);
  return Number.isFinite(parsed) ? parsed : null;
}

function scoreValue(alert) {
  return numberValue(alert.max_score, alert.score_max, alert.risk_percentage);
}

function severityTone(value) {
  const severity = String(value || '').toLowerCase();
  if (['critical', 'critica', 'alta', 'high'].includes(severity)) return 'danger';
  if (['medium', 'media', 'warning'].includes(severity)) return 'warning';
  return 'success';
}

function statusTone(status) {
  if (['open', 'confirmed_leak'].includes(status)) return 'danger';
  if (['acknowledged', 'reviewing', 'investigating', 'possible'].includes(status)) return 'warning';
  return 'success';
}

function feedbackPayload(alert, status, notes) {
  const score = scoreValue(alert) || 0;
  const threshold = numberValue(alert.threshold, alert.decision_threshold) || 85;
  return {
    sensor_id: alert.sensor_id || alert.device_id || '',
    model_version: alert.model_version || null,
    prediction_score: score,
    decision_threshold: threshold,
    predicted_anomaly: status !== 'false_positive',
    operator_label: status === 'false_positive' ? 'false_positive' : 'true_positive',
    operator_event_type: status,
    feedback_status: 'reviewed',
    notes,
    window_start: alert.window_start || alert.detected_at || new Date().toISOString(),
    window_end: alert.window_end || alert.last_detected_at || alert.detected_at || new Date().toISOString(),
    source_data_hash: alert.source_data_hash || `alert-${alert.id}`,
  };
}

export function AlertsPage({ token }) {
  const [alerts, setAlerts] = useState([]);
  const [status, setStatus] = useState('Todas');
  const [floor, setFloor] = useState('Todos');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [target, setTarget] = useState(null);
  const [statusDraft, setStatusDraft] = useState('acknowledged');
  const [notes, setNotes] = useState('');

  const loadData = useCallback(async () => {
    setLoading(true);
    setMessage('');
    try {
      setAlerts(await getAlerts(token));
    } catch (err) {
      setMessage(err.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  function openStatusEditor(alert, nextStatus = alert.status || 'acknowledged') {
    setTarget(alert);
    setStatusDraft(nextStatus);
    setNotes(alert.observations || alert.description || '');
  }

  async function saveStatus() {
    if (!target) return;
    setLoading(true);
    setMessage('');
    const previousAlerts = alerts;
    setAlerts((items) => items.map((alert) => (
      alert.id === target.id
        ? { ...alert, status: statusDraft, observations: notes, description: notes || alert.description }
        : alert
    )));
    try {
      const updated = await updateAlertStatus(token, target.id, statusDraft, { observations: notes });
      if (['confirmed_leak', 'false_positive'].includes(statusDraft)) {
        await submitAlertFeedback(token, target.id, feedbackPayload(target, statusDraft, notes));
      }
      setAlerts((items) => items.map((alert) => (alert.id === target.id ? { ...alert, ...updated } : alert)));
      setTarget(null);
      setMessage('Estado y comentarios guardados.');
    } catch (err) {
      setAlerts(previousAlerts);
      setMessage(`No se pudo guardar la alerta: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }

  const filtered = useMemo(() => alerts.filter((alert) => {
    const matchesStatus = status === 'Todas' || alert.status === status;
    const matchesFloor = floor === 'Todos' || normalizeFloor(alert.floor) === floor;
    return matchesStatus && matchesFloor;
  }), [alerts, status, floor]);

  const activeCount = alerts.filter((alert) => ['open', 'acknowledged', 'reviewing', 'confirmed_leak'].includes(alert.status)).length;
  const leakCount = alerts.filter((alert) => alert.status === 'confirmed_leak').length;
  const falseCount = alerts.filter((alert) => alert.status === 'false_positive').length;
  const maxScore = alerts.reduce((max, alert) => Math.max(max, scoreValue(alert) || 0), 0);

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Alertas</h1>
          <p>Eventos generados por FastAPI a partir del modelo activo y almacenados como DTOs operativos.</p>
        </div>
        <div className="header-actions">
          <button className="secondary-action" onClick={loadData} disabled={loading}>
            {loading ? 'Actualizando...' : 'Actualizar'}
          </button>
        </div>
      </header>

      {message && <div className="form-error page-error">{message}</div>}

      <section className="metrics-grid">
        <MetricCard label="Alertas activas" value={activeCount} tone="critical" />
        <MetricCard label="Fugas confirmadas" value={leakCount} tone="critical" />
        <MetricCard label="Falsas alertas" value={falseCount} tone="warning" />
        <MetricCard label="Score maximo" value={maxScore.toFixed(0)} tone={maxScore >= 85 ? 'critical' : 'warning'} />
      </section>

      <section className="toolbar compact two-cols">
        <label>
          Filtrar por estado
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="Todas">Todas las alertas</option>
            {Object.entries(statusLabels).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
        <label>
          Filtrar por piso
          <select value={floor} onChange={(event) => setFloor(event.target.value)}>
            {floors.map((item) => <option key={item}>{item}</option>)}
          </select>
        </label>
      </section>

      <section className="panel table-panel alert-table">
        <h2>Registro de alertas ({filtered.length})</h2>
        <table>
          <thead>
            <tr>
              <th>Sensor</th>
              <th>Piso</th>
              <th>Tipo</th>
              <th>Severidad</th>
              <th>Inicio</th>
              <th>Ultima deteccion</th>
              <th>Estado</th>
              <th>Score max.</th>
              <th>Caudal prom.</th>
              <th>Ventanas</th>
              <th>Modelo</th>
              <th>Responsable</th>
              <th>Observaciones</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((alert) => {
              const score = scoreValue(alert);
              return (
                <tr key={alert.id}>
                  <td><strong>{alert.sensor_id || alert.device_id}</strong></td>
                  <td>{normalizeFloor(alert.floor)}</td>
                  <td>{alert.alert_type || alert.anomaly_type || '-'}</td>
                  <td><Pill tone={severityTone(alert.severity)}>{alert.severity || '-'}</Pill></td>
                  <td>{formatDate(alert.started_at || alert.detected_at)}</td>
                  <td>{formatDate(alert.last_detected_at || alert.detected_at)}</td>
                  <td><Pill tone={statusTone(alert.status)}>{statusLabels[alert.status] || alert.status || '-'}</Pill></td>
                  <td>{score === null ? '-' : score.toFixed(1)}</td>
                  <td>{numberValue(alert.avg_flow, alert.average_flow, alert.observed_value)?.toFixed(2) || '-'}</td>
                  <td>{alert.window_count || alert.windows_count || alert.samples_used || '-'}</td>
                  <td>{alert.model_version || alert.model_name || '-'}</td>
                  <td>{alert.assignee || alert.responsible || alert.attended_by || '-'}</td>
                  <td>{alert.observations || alert.description || '-'}</td>
                  <td className="actions">
                    <button onClick={() => openStatusEditor(alert)} disabled={loading}>Gestionar</button>
                  </td>
                </tr>
              );
            })}
            {!filtered.length && (
              <tr>
                <td colSpan="14">No hay alertas para mostrar.</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      {target && (
        <ActionPopcard
          title="Gestionar alerta"
          description={`Actualizar alerta de ${target.sensor_id || target.device_id}.`}
          confirmLabel="Guardar"
          loading={loading}
          onConfirm={saveStatus}
          onClose={() => setTarget(null)}
        >
          <div className="popcard-grid single">
            <label>
              Estado
              <select value={statusDraft} onChange={(event) => setStatusDraft(event.target.value)}>
                {statusOptions.map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </label>
            <label>
              Comentarios
              <textarea value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Observaciones del operador" />
            </label>
          </div>
        </ActionPopcard>
      )}
    </>
  );
}
