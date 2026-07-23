import { useCallback, useEffect, useMemo, useState } from 'react';

import { ActionPopcard } from '../components/ActionPopcard';
import { AnomalyScoreChart } from '../components/AnomalyScoreChart';
import { MetricCard } from '../components/MetricCard';
import { Pill } from '../components/Pill';
import { apiRequest } from '../lib/api';
import { floors, normalizeFloor } from '../lib/constants';

const statusLabels = {
  open: 'Activa',
  possible: 'Posible',
  resolved: 'Resuelta',
  investigating: 'Investigando',
  attended: 'Atendida',
};

function statusTone(status) {
  if (status === 'open') return 'danger';
  if (status === 'possible') return 'warning';
  if (status === 'investigating') return 'warning';
  return 'success';
}

function riskTone(value) {
  if (value >= 85) return 'danger';
  if (value >= 50) return 'warning';
  return 'success';
}

function displayStatus(alert) {
  const risk = Number(alert.risk_percentage || 0);
  if (risk >= 50 && risk < 85) return 'possible';
  return alert.status;
}

function alertTypeLabel(alert) {
  if (Number(alert.risk_percentage || 0) >= 85) return 'Riesgo alto';
  return 'Posible fuga';
}

export function AlertsPage({ token }) {
  const [alerts, setAlerts] = useState([]);
  const [analyses, setAnalyses] = useState([]);
  const [status, setStatus] = useState('Todas las alertas');
  const [floor, setFloor] = useState('Todos');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [attendTarget, setAttendTarget] = useState(null);
  const [statusTarget, setStatusTarget] = useState(null);
  const [statusDraft, setStatusDraft] = useState('open');

  const loadData = useCallback(async () => {
    setLoading(true);
    setMessage('');
    try {
      const [alertData, analysisData] = await Promise.all([
        apiRequest('/api/v1/alerts/', { token }),
        apiRequest('/api/v1/ml-analysis/', { token }),
      ]);
      setAlerts(alertData);
      setAnalyses(analysisData);
    } catch (err) {
      setMessage(err.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  async function runAnalysis() {
    setLoading(true);
    setMessage('');
    try {
      const result = await apiRequest('/api/v1/ml-analysis/run', { token, method: 'POST' });
      await loadData();
      setMessage(`${result.anomalies} registros nuevos.`);
    } catch (err) {
      setMessage(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function attendAlert() {
    if (!attendTarget) return;
    setLoading(true);
    setMessage('');
    const previousAlerts = alerts;
    setAlerts((items) => items.map((alert) => (
      alert.id === attendTarget.id
        ? { ...alert, status: 'attended', attended_at: new Date().toISOString() }
        : alert
    )));
    try {
      await apiRequest(`/api/v1/alerts/${attendTarget.id}/attend`, { token, method: 'PATCH' });
      await loadData();
      setAttendTarget(null);
      setMessage('Alerta atendida correctamente.');
    } catch (err) {
      setAlerts(previousAlerts);
      setMessage(`No se pudo atender la alerta: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }

  function openStatusEditor(alert) {
    setStatusTarget(alert);
    setStatusDraft(displayStatus(alert) || 'open');
  }

  async function saveAlertStatus() {
    if (!statusTarget) return;
    setLoading(true);
    setMessage('');
    const previousAlerts = alerts;
    setAlerts((items) => items.map((alert) => (
      alert.id === statusTarget.id ? { ...alert, status: statusDraft } : alert
    )));
    try {
      await apiRequest(`/api/v1/alerts/${statusTarget.id}`, {
        token,
        method: 'PUT',
        body: { status: statusDraft },
      });
      await loadData();
      setStatusTarget(null);
      setMessage('Estado actualizado.');
    } catch (err) {
      setAlerts(previousAlerts);
      setMessage(`No se pudo actualizar el estado: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }

  const visibleAlerts = useMemo(() => alerts.filter((alert) => Number(alert.risk_percentage || 0) >= 50), [alerts]);

  const filtered = useMemo(() => visibleAlerts.filter((alert) => {
    const label = statusLabels[displayStatus(alert)] || displayStatus(alert);
    const matchesStatus = status === 'Todas las alertas' || label === status;
    const matchesFloor = floor === 'Todos' || normalizeFloor(alert.floor) === floor;
    return matchesStatus && matchesFloor;
  }), [visibleAlerts, status, floor]);

  const visibleAnalyses = useMemo(() => analyses.filter((item) => (
    item.prediction === 'anomaly' && Number(item.anomaly_score || 0) >= 50
  )), [analyses]);

  const active = visibleAlerts.filter((alert) => alert.status === 'open' && Number(alert.risk_percentage || 0) >= 85).length;
  const critical = visibleAlerts.filter((alert) => Number(alert.risk_percentage || 0) >= 85).length;
  const possible = visibleAlerts.filter((alert) => Number(alert.risk_percentage || 0) >= 50 && Number(alert.risk_percentage || 0) < 85).length;
  const averageRisk = visibleAlerts.length
    ? Math.round(visibleAlerts.reduce((sum, alert) => sum + Number(alert.risk_percentage || 0), 0) / visibleAlerts.length)
    : 0;

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Alertas</h1>
          <p>Eventos recientes que requieren revision</p>
        </div>
        <div className="header-actions">
          <button className="secondary-action" onClick={loadData} disabled={loading}>
            {loading ? 'Actualizando...' : 'Actualizar'}
          </button>
          <button className="primary-action" onClick={runAnalysis} disabled={loading}>
            Analizar
          </button>
        </div>
      </header>

      {message && <div className="form-error page-error">{message}</div>}

      <section className="metrics-grid">
        <MetricCard label="Alertas activas" value={active} tone="critical" />
        <MetricCard label="Por atender" value={critical} tone="critical" />
        <MetricCard label="Posibilidades" value={possible} tone="warning" />
        <MetricCard label="Riesgo promedio" value={`${averageRisk}%`} tone={averageRisk > 75 ? 'critical' : 'warning'} />
      </section>

      <section className="panel chart-panel">
        <div className="panel-heading">
          <div>
            <h2>Nivel de riesgo</h2>
            <p>Desde 50 puntos</p>
          </div>
        </div>
        <AnomalyScoreChart analyses={visibleAnalyses} />
      </section>

      <section className="toolbar compact two-cols">
        <label>
          Filtrar por estado
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option>Todas las alertas</option>
            <option>Activa</option>
            <option>Posible</option>
            <option>Resuelta</option>
            <option>Investigando</option>
            <option>Atendida</option>
          </select>
        </label>
        <label>
          Filtrar por piso
          <select value={floor} onChange={(event) => setFloor(event.target.value)}>
            {floors.map((item) => <option key={item}>{item}</option>)}
          </select>
        </label>
      </section>

      <section className="panel table-panel">
        <h2>Registro de alertas ({filtered.length})</h2>
        <table>
          <thead>
            <tr>
              <th>Hora</th>
              <th>Sensor</th>
              <th>Piso</th>
              <th>Tipo</th>
              <th>Riesgo</th>
              <th>Estado</th>
              <th>Descripcion</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((alert) => (
              <tr key={alert.id}>
                <td>{alert.detected_at ? alert.detected_at.replace('T', ' ').slice(0, 16) : '-'}</td>
                <td><strong>{alert.device_id}</strong></td>
                <td>{normalizeFloor(alert.floor)}</td>
                <td><Pill tone="neutral">{alertTypeLabel(alert)}</Pill></td>
                <td><Pill tone={riskTone(Number(alert.risk_percentage || 0))}>{Number(alert.risk_percentage || 0).toFixed(0)}%</Pill></td>
                <td><Pill tone={statusTone(displayStatus(alert))}>{statusLabels[displayStatus(alert)] || displayStatus(alert)}</Pill></td>
                <td>{alert.description || '-'}</td>
                <td className="actions">
                  {Number(alert.risk_percentage || 0) >= 85 && alert.status !== 'attended' ? (
                    <button onClick={() => setAttendTarget(alert)} disabled={loading}>
                      Atender
                    </button>
                  ) : (
                    <button onClick={() => openStatusEditor(alert)} disabled={loading}>
                      Estado
                    </button>
                  )}
                  {Number(alert.risk_percentage || 0) >= 85 && alert.status !== 'attended' && (
                    <button onClick={() => openStatusEditor(alert)} disabled={loading}>
                      Estado
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {!filtered.length && (
              <tr>
                <td colSpan="8">No hay alertas para mostrar.</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      {attendTarget && (
        <ActionPopcard
          title="Atender alerta"
          description={`Marcar como atendida la alerta de ${attendTarget.device_id}.`}
          confirmLabel="Atender"
          loading={loading}
          onConfirm={attendAlert}
          onClose={() => setAttendTarget(null)}
        >
          <p className="popcard-note">{attendTarget.description || 'Se registrara la atencion en el backend.'}</p>
        </ActionPopcard>
      )}

      {statusTarget && (
        <ActionPopcard
          title="Editar estado"
          description={`Actualizar estado de ${statusTarget.device_id}.`}
          confirmLabel="Guardar"
          loading={loading}
          onConfirm={saveAlertStatus}
          onClose={() => setStatusTarget(null)}
        >
          <div className="popcard-grid single">
            <label>
              Estado
              <select value={statusDraft} onChange={(event) => setStatusDraft(event.target.value)}>
                <option value="open">Activa</option>
                <option value="possible">Posible</option>
                <option value="investigating">Investigando</option>
                <option value="attended">Atendida</option>
                <option value="resolved">Resuelta</option>
              </select>
            </label>
          </div>
        </ActionPopcard>
      )}
    </>
  );
}
