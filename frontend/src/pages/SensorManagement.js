import { useCallback, useEffect, useMemo, useState } from 'react';

import { ActionPopcard } from '../components/ActionPopcard';
import { MetricCard } from '../components/MetricCard';
import { Pill } from '../components/Pill';
import { allowedFloorsForUser, hasAdminAccess, normalizeFloor, statusClass } from '../lib/constants';
import {
  createDevice,
  deleteDevice,
  getActiveTelemetryDevices,
  getIotConfig,
  updateDevice,
} from '../services/deviceService';
import { getFloors } from '../services/floorService';

const statusLabels = {
  active: 'En línea',
  offline: 'Desconectado',
  maintenance: 'Mantenimiento',
};

function displayStatus(value) {
  return statusLabels[value] || value || 'Sin estado';
}

function formatDate(value) {
  if (!value) return '-';
  const raw = String(value);
  const date = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(raw) ? raw : `${raw.replace(' ', 'T')}Z`);
  if (Number.isNaN(date.getTime())) return raw.replace('T', ' ').slice(0, 16);
  return date.toLocaleString('es-BO', {
    timeZone: 'America/La_Paz',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

export function SensorManagement({ token, currentUser }) {
  const [sensors, setSensors] = useState([]);
  const [floorOptions, setFloorOptions] = useState([]);
  const [iotConfig, setIotConfig] = useState(null);
  const [hiddenTelemetryIds, setHiddenTelemetryIds] = useState([]);
  const [query, setQuery] = useState('');
  const floorFilterOptions = useMemo(() => allowedFloorsForUser(currentUser, currentUser?.role_id === 3), [currentUser]);
  const [floor, setFloor] = useState('Todos');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [popcard, setPopcard] = useState(null);
  const [form, setForm] = useState({
    device_id: '',
    floor_id: '',
    floor: 'PB',
    location: '',
    sensor_type: 'FS300A',
    status: 'active',
  });
  const canManageDevices = hasAdminAccess(currentUser);

  const loadSensors = useCallback(async () => {
    setLoading(true);
    setMessage('');
    try {
      const [activeSensors, config] = await Promise.all([
        getActiveTelemetryDevices(token, { floor, limit: 300 }),
        getIotConfig(token),
      ]);
      setIotConfig(config);
      setSensors(Array.isArray(activeSensors) ? activeSensors : []);
    } catch (err) {
      setMessage(`No fue posible completar la operación: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }, [token, floor]);

  useEffect(() => {
    loadSensors();
  }, [loadSensors]);

  const loadFloors = useCallback(async () => {
    if (!canManageDevices) {
      setFloorOptions([]);
      return;
    }
    try {
      const data = await getFloors(token);
      setFloorOptions(Array.isArray(data) ? data : []);
    } catch (err) {
      setMessage(`No fue posible cargar pisos: ${err.message}`);
    }
  }, [canManageDevices, token]);

  useEffect(() => {
    loadFloors();
  }, [loadFloors]);

  const filtered = useMemo(() => sensors.filter((sensor) => {
    if (hiddenTelemetryIds.includes(sensor.device_id)) return false;
    const matchesText = `${sensor.device_id} ${sensor.location || ''}`.toLowerCase().includes(query.toLowerCase());
    const matchesFloor = floor === 'Todos' || normalizeFloor(sensor.floor) === floor;
    return matchesText && matchesFloor;
  }), [sensors, hiddenTelemetryIds, query, floor]);

  function openCreateSensor() {
    const firstFloor = floorOptions[0];
    setForm({
      device_id: '',
      floor_id: firstFloor?.id ? String(firstFloor.id) : '',
      floor: firstFloor?.code || 'PB',
      location: '',
      sensor_type: 'FS300A',
      status: 'active',
    });
    setPopcard({ type: 'create' });
  }

  function openEditSensor(sensor) {
    setForm({
      device_id: sensor.device_id,
      floor_id: sensor.floor_id ? String(sensor.floor_id) : '',
      floor: sensor.floor_info?.code || normalizeFloor(sensor.floor) || 'PB',
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
        floor_id: form.floor_id ? Number(form.floor_id) : null,
        floor: form.floor === 'Todos' ? null : form.floor,
      };
      if (popcard?.type === 'edit' && popcard.sensor.id) {
        await updateDevice(token, popcard.sensor.id, body);
        setMessage('Sensor actualizado correctamente.');
      } else {
        await createDevice(token, body);
        setHiddenTelemetryIds((items) => items.filter((item) => item !== form.device_id));
        setMessage(popcard?.type === 'edit' ? 'Sensor registrado. Aparecerá como activo cuando publique telemetría.' : 'Sensor registrado. Aparecerá como activo cuando publique telemetría.');
      }
      setPopcard(null);
      await loadSensors();
    } catch (err) {
      setMessage(`No fue posible completar la operación: ${err.message}`);
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
      if (sensor.id) {
        await deleteDevice(token, sensor.id);
        setMessage('Sensor eliminado del inventario.');
      } else {
        setHiddenTelemetryIds((items) => [...new Set([...items, sensor.device_id])]);
        setMessage('Sensor ocultado de la vista local. Si sigue publicando MQTT, volvera al recargar desde el backend.');
      }
      setPopcard(null);
      await loadSensors();
    } catch (err) {
      setMessage(`No fue posible completar la operación: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Dispositivos</h1>
          <p>Lecturas y estado operativo de los sensores conectados.</p>
        </div>
        <div className="header-actions">
          <button className="secondary-action" onClick={loadSensors} disabled={loading}>
            {loading ? 'Actualizando...' : 'Actualizar'}
          </button>
          {canManageDevices && <button className="primary-action" onClick={openCreateSensor}>Añadir nuevo sensor</button>}
        </div>
      </header>

      <section className="toolbar">
        <label>
          Buscar sensor
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="ID o ubicación..." />
        </label>
        <label>
          Filtrar por piso
          <select
            value={floor}
            onChange={(event) => {
              setFloor(event.target.value);
            }}
          >
            {floorFilterOptions.map((item) => <option key={item}>{item}</option>)}
          </select>
        </label>
      </section>

      {message && <div className="form-error page-error">{message}</div>}

      <section className="metrics-grid">
        <MetricCard icon="sensors" label="Sensores activos" value={sensors.length} />
        <MetricCard icon="inventory_2" label="Registrados" value={sensors.filter((sensor) => sensor.registered).length} tone="blue" />
        <MetricCard icon="schedule" label="Actualizados" value={sensors.filter((sensor) => sensor.last_seen).length} tone="ok" />
      </section>

      <section className="panel table-panel sensor-table">
        <h2>Sensores activos ({filtered.length})</h2>
        <table>
          <thead>
            <tr>
              <th>ID Sensor</th>
              <th>Ubicación (Piso)</th>
              <th>Estado</th>
              <th>Origen</th>
              <th>Lectura actual</th>
              <th>Alertas</th>
              <th>Último dato</th>
              {canManageDevices && <th>Acciones</th>}
            </tr>
          </thead>
          <tbody>
            {filtered.map((sensor) => (
              <tr key={sensor.id || sensor.device_id}>
                <td><strong>{sensor.device_id}</strong></td>
                <td>
                  <strong>{sensor.location || 'Sin ubicación registrada'}</strong>
                  <span>{sensor.floor_info ? `${sensor.floor_info.code} - ${sensor.floor_info.name}` : 'Sin piso asignado'} - {sensor.site || 'telemetría'}</span>
                </td>
                <td><Pill tone={statusClass(displayStatus(sensor.status))}>{displayStatus(sensor.status)}</Pill></td>
                <td><Pill tone={sensor.registered ? 'success' : 'warning'}>{sensor.registered ? 'Registrado' : 'No registrado'}</Pill></td>
                <td>{sensor.reading === null ? '-' : <><strong>{Number(sensor.reading || 0).toFixed(2)}</strong> <span>L/min</span></>}</td>
                <td>
                  <strong>{Number(sensor.active_alert_count || 0)}</strong>
                  <span>activas / {Number(sensor.alert_count || 0)} total</span>
                </td>
                <td>{formatDate(sensor.last_seen)}</td>
                {canManageDevices && (
                  <td className="actions">
                    <button onClick={() => openEditSensor(sensor)}>Editar</button>
                    <button className="delete" onClick={() => openDeleteSensor(sensor)}>Eliminar</button>
                  </td>
                )}
              </tr>
            ))}
            {!filtered.length && (
              <tr>
                <td colSpan={canManageDevices ? 8 : 7}>No se encontraron registros para el periodo seleccionado.</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      {(popcard?.type === 'create' || popcard?.type === 'edit') && (
        <ActionPopcard
          title={popcard.type === 'edit' ? 'Editar sensor' : 'Añadir sensor'}
          description={popcard.type === 'edit' && !popcard.sensor.id ? 'Este sensor viene de telemetría MQTT. Al guardar, se registrará en el inventario.' : 'Registra el device_id que enviará telemetría MQTT.'}
          confirmLabel={popcard.type === 'edit' ? 'Guardar cambios' : 'Crear sensor'}
          loading={loading}
          onConfirm={saveSensor}
          onClose={() => setPopcard(null)}
        >
          <div className="popcard-grid">
            <label>ID Sensor<input value={form.device_id} onChange={(event) => setForm({ ...form, device_id: event.target.value })} disabled={popcard.type === 'edit'} /></label>
            <label>Ubicación<input value={form.location} onChange={(event) => setForm({ ...form, location: event.target.value })} /></label>
            <label>
              Piso
              <select
                value={form.floor_id}
                onChange={(event) => {
                  const selected = floorOptions.find((item) => String(item.id) === event.target.value);
                  setForm({ ...form, floor_id: event.target.value, floor: selected?.code || form.floor });
                }}
              >
                <option value="">Sin piso asignado</option>
                {floorOptions.map((item) => <option key={item.id} value={item.id}>{item.code} - {item.name}</option>)}
              </select>
            </label>
            <label>Estado<select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}><option value="active">En línea</option><option value="offline">Desconectado</option><option value="maintenance">Mantenimiento</option></select></label>
          </div>
          <p className="popcard-note">
            Topic MQTT esperado: {(iotConfig?.topic_template || '').replace('{site}', iotConfig?.site || '').replace('{device_id}', form.device_id || '{device_id}')}
          </p>
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
          <p className="popcard-note">Si el sensor solo existe por telemetría MQTT, se ocultará en esta vista local.</p>
        </ActionPopcard>
      )}
    </>
  );
}
