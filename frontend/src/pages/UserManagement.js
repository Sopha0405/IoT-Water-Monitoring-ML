import { useCallback, useEffect, useMemo, useState } from 'react';

import { ActionPopcard } from '../components/ActionPopcard';
import { MetricCard } from '../components/MetricCard';
import { Pill } from '../components/Pill';
import { apiRequest } from '../lib/api';
import { floors, normalizeFloor, roleNames } from '../lib/constants';

export function UserManagement({ token, currentUser }) {
  const [users, setUsers] = useState([]);
  const [query, setQuery] = useState('');
  const [floor, setFloor] = useState('Todos');
  const [role, setRole] = useState('Todos');
  const [showForm, setShowForm] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    name: '',
    email: '',
    password: '',
    phone: '',
    floor: 'PB',
    role_id: 1,
    is_active: true,
  });

  function resetForm() {
    setForm({ name: '', email: '', password: '', phone: '', floor: 'PB', role_id: 1, is_active: true });
    setEditingUser(null);
  }

  const loadUsers = useCallback(async () => {
    setLoading(true);
    setMessage('');
    try {
      const data = await apiRequest('/api/v1/users/', { token });
      setUsers(data);
    } catch (err) {
      setMessage(err.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  function startCreateUser() {
    resetForm();
    setShowForm((value) => !value);
  }

  function startEditUser(user) {
    setEditingUser(user);
    setForm({
      name: user.name || '',
      email: user.email || '',
      password: '',
      phone: user.phone || '',
      floor: normalizeFloor(user.floor) || 'PB',
      role_id: user.role_id || 1,
      is_active: user.is_active ?? true,
    });
    setShowForm(true);
  }

  async function saveUser(event) {
    event?.preventDefault();
    setLoading(true);
    setMessage('');
    try {
      const payload = {
        name: form.name,
        email: form.email,
        phone: form.phone || null,
        floor: form.floor === 'Todos' ? null : form.floor,
        role_id: Number(form.role_id),
        is_active: form.is_active,
      };

      if (editingUser) {
        await apiRequest(`/api/v1/users/${editingUser.id}`, {
          token,
          method: 'PUT',
          body: payload,
        });
        if (form.password) {
          await apiRequest(`/api/v1/users/${editingUser.id}/password`, {
            token,
            method: 'PATCH',
            body: { password: form.password },
          });
        }
        setMessage('Usuario actualizado correctamente.');
      } else {
        await apiRequest('/api/v1/users/', {
          token,
          method: 'POST',
          body: {
            ...payload,
            password: form.password,
          },
        });
        setMessage('Usuario creado correctamente.');
      }

      resetForm();
      setShowForm(false);
      await loadUsers();
    } catch (err) {
      setMessage(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function deleteUser() {
    if (!deleteTarget) return;
    if (deleteTarget.id === currentUser?.id) {
      setMessage('No puedes eliminar tu propia sesion.');
      return;
    }
    setLoading(true);
    setMessage('');
    try {
      await apiRequest(`/api/v1/users/${deleteTarget.id}`, { token, method: 'DELETE' });
      await loadUsers();
      setDeleteTarget(null);
      setMessage('Usuario eliminado.');
    } catch (err) {
      setMessage(err.message);
    } finally {
      setLoading(false);
    }
  }

  const filtered = useMemo(() => users.filter((user) => {
    const roleLabel = roleNames[user.role_id] || `Rol ${user.role_id}`;
    const matchesText = `${user.name} ${user.email} ${user.phone || ''}`.toLowerCase().includes(query.toLowerCase());
    const matchesFloor = floor === 'Todos' || normalizeFloor(user.floor) === floor;
    const matchesRole = role === 'Todos' || roleLabel === role;
    return matchesText && matchesFloor && matchesRole;
  }), [users, query, floor, role]);

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Usuarios</h1>
          <p>Accesos y permisos</p>
        </div>
        <div className="header-actions">
          <button className="secondary-action" onClick={loadUsers} disabled={loading}>Actualizar</button>
          <button className="primary-action" onClick={startCreateUser}>
            Anadir nuevo usuario
          </button>
        </div>
      </header>

      <section className="toolbar">
        <label>
          Buscar usuario
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Nombre, telefono o email..." />
        </label>
        <label>
          Filtrar por piso
          <select value={floor} onChange={(event) => setFloor(event.target.value)}>
            {floors.map((item) => <option key={item}>{item}</option>)}
          </select>
        </label>
        <label>
          Filtrar por rol
          <select value={role} onChange={(event) => setRole(event.target.value)}>
            <option>Todos</option>
            <option>Supervisor</option>
            <option>Tecnico</option>
            <option>Administrador</option>
          </select>
        </label>
      </section>

      {showForm && (
        <ActionPopcard
          title={editingUser ? 'Editar usuario' : 'Anadir usuario'}
          description={editingUser ? 'Modifica los datos del usuario seleccionado.' : 'Crea un nuevo acceso al sistema.'}
          confirmLabel={editingUser ? 'Guardar cambios' : 'Crear usuario'}
          loading={loading}
          onConfirm={saveUser}
          onClose={() => { resetForm(); setShowForm(false); }}
        >
        <div className="popcard-grid">
          <label>Nombre<input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required /></label>
          <label>Email<input type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required /></label>
          <label>Password<input type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} required={!editingUser} minLength="8" placeholder={editingUser ? 'Dejar igual' : ''} /></label>
          <label>Telefono<input value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} /></label>
          <label>Piso<select value={form.floor} onChange={(event) => setForm({ ...form, floor: event.target.value })}>{floors.filter((item) => item !== 'Todos').map((item) => <option key={item}>{item}</option>)}</select></label>
          <label>Rol<select value={form.role_id} onChange={(event) => setForm({ ...form, role_id: event.target.value })}><option value="1">Supervisor</option><option value="2">Tecnico</option><option value="3">Administrador</option></select></label>
          <label>Estado<select value={form.is_active ? 'true' : 'false'} onChange={(event) => setForm({ ...form, is_active: event.target.value === 'true' })}><option value="true">Activo</option><option value="false">Inactivo</option></select></label>
        </div>
        </ActionPopcard>
      )}

      {message && <div className="form-error page-error">{message}</div>}

      <section className="metrics-grid">
        <MetricCard icon="group" label="Total de usuarios" value={users.length} />
        <MetricCard icon="admin_panel_settings" label="Administradores" value={users.filter((user) => user.role_id === 3).length} tone="blue" />
        <MetricCard icon="verified_user" label="Activos" value={users.filter((user) => user.is_active).length} tone="ok" />
        <MetricCard icon="filter_alt" label="Resultados filtrados" value={filtered.length} />
      </section>

      <section className="panel table-panel">
        <h2>Listado de Usuarios ({filtered.length})</h2>
        <table>
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Piso</th>
              <th>Rol</th>
              <th>Estado</th>
              <th>Contacto</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((user) => (
              <tr key={user.id}>
                <td><strong>{user.name}</strong><span>{user.email}</span></td>
                <td>{user.floor || 'Todos'}</td>
                <td><Pill tone={user.role_id === 3 ? 'info' : 'neutral'}>{roleNames[user.role_id] || `Rol ${user.role_id}`}</Pill></td>
                <td><Pill tone={user.is_active ? 'success' : 'warning'}>{user.is_active ? 'Activo' : 'Inactivo'}</Pill></td>
                <td>{user.phone || '-'}</td>
                <td className="actions">
                  <button onClick={() => startEditUser(user)} disabled={loading}>Editar</button>
                  <button className="delete" onClick={() => setDeleteTarget(user)} disabled={loading}>Eliminar</button>
                </td>
              </tr>
            ))}
            {!filtered.length && (
              <tr>
                <td colSpan="6">No hay usuarios para mostrar.</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      {deleteTarget && (
        <ActionPopcard
          title="Eliminar usuario"
          description={`Vas a eliminar el usuario ${deleteTarget.email}.`}
          confirmLabel="Eliminar"
          danger
          loading={loading}
          onConfirm={deleteUser}
          onClose={() => setDeleteTarget(null)}
        >
          <p className="popcard-note">Esta accion quitara el acceso del usuario al sistema.</p>
        </ActionPopcard>
      )}
    </>
  );
}
