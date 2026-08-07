import { useCallback, useEffect, useMemo, useState } from 'react';

import { ActionPopcard } from './ActionPopcard';
import { FloorForm } from './FloorForm';
import { FloorTable } from './FloorTable';
import { MetricCard } from './MetricCard';
import {
  createFloor,
  deleteFloor,
  getFloors,
  updateFloor,
} from '../services/floorService';

const emptyForm = {
  code: '',
  name: '',
  description: '',
  is_active: true,
};

export function FloorManagement({ token }) {
  const [floors, setFloors] = useState([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [popcard, setPopcard] = useState(null);
  const [form, setForm] = useState(emptyForm);

  const loadFloors = useCallback(async () => {
    setLoading(true);
    setMessage('');
    try {
      const data = await getFloors(token, { includeInactive: true });
      setFloors(Array.isArray(data) ? data : []);
    } catch (err) {
      setMessage(`No fue posible completar la operacion: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadFloors();
  }, [loadFloors]);

  const filtered = useMemo(() => floors.filter((floor) => (
    `${floor.code} ${floor.name}`.toLowerCase().includes(query.toLowerCase())
  )), [floors, query]);

  function openCreate() {
    setForm(emptyForm);
    setPopcard({ type: 'create' });
  }

  function openEdit(floor) {
    setForm({
      code: floor.code || '',
      name: floor.name || '',
      description: floor.description || '',
      is_active: floor.is_active ?? true,
    });
    setPopcard({ type: 'edit', floor });
  }

  async function saveFloor() {
    setLoading(true);
    setMessage('');
    try {
      const payload = {
        code: form.code.trim(),
        name: form.name.trim(),
        description: form.description.trim() || null,
        is_active: form.is_active,
      };
      if (popcard?.type === 'edit') {
        await updateFloor(token, popcard.floor.id, payload);
        setMessage('Piso actualizado correctamente.');
      } else {
        await createFloor(token, payload);
        setMessage('Piso creado correctamente.');
      }
      setPopcard(null);
      await loadFloors();
    } catch (err) {
      setMessage(`No fue posible completar la operacion: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }

  async function removeFloor() {
    const floor = popcard?.floor;
    if (!floor) return;
    setLoading(true);
    setMessage('');
    try {
      await deleteFloor(token, floor.id);
      setMessage('Piso eliminado.');
      setPopcard(null);
      await loadFloors();
    } catch (err) {
      setMessage(`No fue posible completar la operacion: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Gestion de pisos</h1>
          <p>Administra los niveles operativos donde se asignan dispositivos.</p>
        </div>
        <div className="header-actions">
          <button className="secondary-action" onClick={loadFloors} disabled={loading}>Actualizar</button>
          <button className="primary-action" onClick={openCreate}>Anadir piso</button>
        </div>
      </header>

      <section className="toolbar compact two-cols">
        <label>
          Buscar piso
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Codigo o nombre..." />
        </label>
      </section>

      {message && <div className="form-error page-error">{message}</div>}

      <section className="metrics-grid">
        <MetricCard label="Pisos registrados" value={floors.length} />
        <MetricCard label="Pisos activos" value={floors.filter((floor) => floor.is_active).length} tone="ok" />
        <MetricCard label="Dispositivos asignados" value={floors.reduce((total, floor) => total + Number(floor.device_count || 0), 0)} tone="blue" />
        <MetricCard label="Resultados filtrados" value={filtered.length} />
      </section>

      <FloorTable floors={filtered} loading={loading} onEdit={openEdit} onDelete={(floor) => setPopcard({ type: 'delete', floor })} />

      {(popcard?.type === 'create' || popcard?.type === 'edit') && (
        <ActionPopcard
          title={popcard.type === 'edit' ? 'Editar piso' : 'Anadir piso'}
          description="Define codigo, nombre y estado operativo del piso."
          confirmLabel={popcard.type === 'edit' ? 'Guardar cambios' : 'Crear piso'}
          loading={loading}
          onConfirm={saveFloor}
          onClose={() => setPopcard(null)}
        >
          <FloorForm form={form} setForm={setForm} />
        </ActionPopcard>
      )}

      {popcard?.type === 'delete' && (
        <ActionPopcard
          title="Eliminar piso"
          description={`Vas a eliminar el piso ${popcard.floor.code}.`}
          confirmLabel="Eliminar"
          danger
          loading={loading}
          onConfirm={removeFloor}
          onClose={() => setPopcard(null)}
        >
          <p className="popcard-note">No se puede eliminar un piso con dispositivos asociados.</p>
        </ActionPopcard>
      )}
    </>
  );
}
