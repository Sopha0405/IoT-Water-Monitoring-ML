import { useCallback, useEffect, useMemo, useState } from 'react';

import { ActionPopcard } from '../components/ActionPopcard';
import { MetricCard } from '../components/MetricCard';
import { Pill } from '../components/Pill';
import { apiRequest } from '../lib/api';
import { floors, normalizeFloor, statusClass } from '../lib/constants';

const statusLabels = {
  active: 'En Linea',
  offline: 'Desconectado',
  maintenance: 'Mantenimiento',
};

function displayStatus(value) {
  return statusLabels[value] || value || 'Sin estado';
}

export function SensorManagement({ token }) {
  const [sensors, setSensors] = useState([]);
  const [hiddenTelemetryIds, setHiddenTelemetryIds] = useState([]);
  const [query, setQuery] = useState('');
  const [floor, setFloor] = useState('Todos');
  const [status, setStatus] = useState('Todos');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [popcard, setPopcard] = useState(null);
  const [form, setForm] = useState({
    device_id: '',
    floor: 'PB',
    location: '',
    sensor_type: 'FS300A',
    status: 'active',
  });

  const loadSensors = useCallback(async () => {
    setLoading(true);
    setMessage('');
    try {
      const [devices, telemetry] = await Promise.all([
        apiRequest('/api/v1/devices/', { token }),
        apiRequest('/api/v1/telemetry/latest?field=flow_lpm&limit=300', { token }),
      ]);
      const deviceMeta = Object.fromEntries(devices.map((device) => [device.device_id, device]));
      const latestByDevice = telemetry
        .filter((point) => point.device_id)
        .slice()
        .sort((a, b) => new Date(b.time) - new Date(a.time))
        .reduce((acc, point) => {
          if (!acc[point.device_id]) acc[point.device_id] = point;
          return acc;
        }, {});

      const liveSensors = Object.entries(latestByDevice).map(([deviceId, point]) => {
        const meta = deviceMeta[deviceId] || {};
        const ageMs = Date.now() - new Date(point.time).getTime();
        const isFresh = Number.isFinite(ageMs) && ageMs < 2 * 60 * 1000;
        return {
          id: meta.id || deviceId,
          dbId: meta.id || null,
          device_id: deviceId,
          floor: point.floor || meta.floor,
          location: meta.location || (deviceId === 'pb-wokwi' ? 'Medidor Wokwi - Planta Baja' : 'Telemetria MQTT'),
          status: isFresh ? 'active' : 'offline',
          reading: Number(point.value || 0),
          last_seen: point.time,
          last_calibration: meta.last_calibration || null,
          source: point.tenant || point.site || 'MQTT',
        };
      });
      setSensors(liveSensors);
    } catch (err) {
      setMessage(err.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadSensors();
  }, [loadSensors]);

  const filtered = useMemo(() => sensors.filter((sensor) => {
    if (hiddenTelemetryIds.includes(sensor.device_id)) return false;
    const label = displayStatus(sensor.status);
    const matchesText = `${sensor.device_id} ${sensor.location || ''}`.toLowerCase().includes(query.toLowerCase());
    const matchesFloor = floor === 'Todos' || normalizeFloor(sensor.floor) === floor;
    const matchesStatus = status === 'Todos' || label === status;
    return matchesText && matchesFloor && matchesStatus;
  }), [sensors, hiddenTelemetryIds, query, floor, status]);

  function openCreateSensor() {
    setForm({ device_id: '', floor: 'PB', location: '', sensor_type: 'FS300A', status: 'active' });
    setPopcard({ type: 'create' });
  }

  function openEditSensor(sensor) {
    setForm({
      device_id: sensor.device_id,
      floor: normalizeFloor(sensor.floor) || 'PB',
      location: sensor.location || '',
      sensor_type: sensor.sensor_type || 'FS300A',
      status: sensor.status || 'active',
    });
    setPopcard({ type: 'edit', sensor });
  }

  function openDeleteSensor(sensor) {
    setPopcard({ type: 'delete', sensor });
  }

  async function saveSensor() {
    setLoading(true);
    setMessage('');
    try {
      const body = {
        ...form,
        floor: form.floor === 'Todos' ? null : form.floor,
      };
      if (popcard?.type === 'edit' && popcard.sensor.dbId) {
        await apiRequest(`/api/v1/devices/${popcard.sensor.dbId}`, { token, method: 'PUT', body });
        setMessage('Sensor actualizado correctamente.');
      } else {
        await apiRequest('/api/v1/devices/', { token, method: 'POST', body });
        setHiddenTelemetryIds((items) => items.filter((item) => item !== form.device_id));
        setMessage(popcard?.type === 'edit' ? 'Sensor registrado en inventario.' : 'Sensor agregado correctamente.');
      }
      setPopcard(null);
      await loadSensors();
    } catch (err) {
      setMessage(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function deleteSensor() {
    const sensor = popcard?.sensor;
    if (!sensor) return;
    setLoading(true);
    setMessage('');
    try {
      if (sensor.dbId) {
        await apiRequest(`/api/v1/devices/${sensor.dbId}`, { token, method: 'DELETE' });
        setMessage('Sensor eliminado del inventario.');
      } else {
        setHiddenTelemetryIds((items) => [...new Set([...items, sensor.device_id])]);
        setMessage('Sensor ocultado de la vista local. Si sigue publicando MQTT, volvera al recargar desde el backend.');
      }
      setPopcard(null);
      await loadSensors();
    } catch (err) {
      setMessage(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Sensores</h1>
          <p>Lecturas y estado operativo</p>
        </div>
        <div className="header-actions">
          <button className="secondary-action" onClick={loadSensors} disabled={loading}>
            {loading ? 'Actualizando...' : 'Actualizar'}
          </button>
          <button className="primary-action" onClick={openCreateSensor}>Anadir nuevo sensor</button>
        </div>
      </header>

      <section className="toolbar">
        <label>
          Buscar sensor
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="ID o ubicacion..." />
        </label>
        <label>
          Filtrar por piso
          <select value={floor} onChange={(event) => setFloor(event.target.value)}>
            {floors.map((item) => <option key={item}>{item}</option>)}
          </select>
        </label>
        <label>
          Filtrar por estado
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option>Todos</option>
            <option>En Linea</option>
            <option>Desconectado</option>
            <option>Mantenimiento</option>
          </select>
        </label>
      </section>

      {message && <div className="form-error page-error">{message}</div>}

      <section className="metrics-grid">
        <MetricCard label="Total de sensores" value={sensors.length} />
        <MetricCard label="En linea" value={sensors.filter((sensor) => sensor.status === 'active').length} tone="ok" />
        <MetricCard label="Desconectados" value={sensors.filter((sensor) => sensor.status === 'offline').length} tone="critical" />
        <MetricCard label="En mantenimiento" value={sensors.filter((sensor) => sensor.status === 'maintenance').length} tone="warning" />
      </section>

      <section className="panel table-panel sensor-table">
        <h2>Listado de Sensores ({filtered.length})</h2>
        <table>
          <thead>
            <tr>
              <th>ID Sensor</th>
              <th>Ubicacion (Piso)</th>
              <th>Estado</th>
              <th>Lectura actual</th>
              <th>Ultimo dato</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((sensor) => (
              <tr key={sensor.id}>
                <td><strong>{sensor.device_id}</strong></td>
                <td><strong>{sensor.location || '-'}</strong><span>{normalizeFloor(sensor.floor)} - {sensor.source}</span></td>
                <td><Pill tone={statusClass(displayStatus(sensor.status))}>{displayStatus(sensor.status)}</Pill></td>
                <td><strong>{Number(sensor.reading || 0).toFixed(2)}</strong> <span>L/min</span></td>
                <td>{sensor.last_seen ? sensor.last_seen.replace('T', ' ').slice(0, 19) : '-'}</td>
                <td className="actions">
                  <button onClick={() => openEditSensor(sensor)}>Editar</button>
                  <button className="delete" onClick={() => openDeleteSensor(sensor)}>Eliminar</button>
                </td>
              </tr>
            ))}
            {!filtered.length && (
              <tr>
                <td colSpan="6">No hay sensores para mostrar.</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      {(popcard?.type === 'create' || popcard?.type === 'edit') && (
        <ActionPopcard
          title={popcard.type === 'edit' ? 'Editar sensor' : 'Anadir sensor'}
          description={popcard.type === 'edit' && !popcard.sensor.dbId ? 'Este sensor viene de telemetria MQTT. Al guardar, se registrara en el inventario.' : 'Actualiza los metadatos del sensor.'}
          confirmLabel={popcard.type === 'edit' ? 'Guardar cambios' : 'Crear sensor'}
          loading={loading}
          onConfirm={saveSensor}
          onClose={() => setPopcard(null)}
        >
          <div className="popcard-grid">
            <label>ID Sensor<input value={form.device_id} onChange={(event) => setForm({ ...form, device_id: event.target.value })} disabled={popcard.type === 'edit'} /></label>
            <label>Ubicacion<input value={form.location} onChange={(event) => setForm({ ...form, location: event.target.value })} /></label>
            <label>Piso<select value={form.floor} onChange={(event) => setForm({ ...form, floor: event.target.value })}>{floors.filter((item) => item !== 'Todos').map((item) => <option key={item}>{item}</option>)}</select></label>
            <label>Estado<select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}><option value="active">En Linea</option><option value="offline">Desconectado</option><option value="maintenance">Mantenimiento</option></select></label>
          </div>
        </ActionPopcard>
      )}

      {popcard?.type === 'delete' && (
        <ActionPopcard
          title="Eliminar sensor"
          description={`Vas a eliminar u ocultar ${popcard.sensor.device_id}.`}
          confirmLabel="Eliminar"
          danger
          loading={loading}
          onConfirm={deleteSensor}
          onClose={() => setPopcard(null)}
        >
          <p className="popcard-note">Si el sensor solo existe por telemetria MQTT, se ocultara en esta vista local.</p>
        </ActionPopcard>
      )}
    </>
  );
}
