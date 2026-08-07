export function FloorForm({ form, setForm }) {
  return (
    <div className="popcard-grid">
      <label>
        Codigo
        <input
          value={form.code}
          onChange={(event) => setForm({ ...form, code: event.target.value.toUpperCase() })}
          maxLength="20"
          required
        />
      </label>
      <label>
        Nombre
        <input
          value={form.name}
          onChange={(event) => setForm({ ...form, name: event.target.value })}
          maxLength="100"
          required
        />
      </label>
      <label>
        Descripcion
        <input
          value={form.description}
          onChange={(event) => setForm({ ...form, description: event.target.value })}
          maxLength="255"
        />
      </label>
      <label>
        Estado
        <select
          value={form.is_active ? 'true' : 'false'}
          onChange={(event) => setForm({ ...form, is_active: event.target.value === 'true' })}
        >
          <option value="true">Activo</option>
          <option value="false">Inactivo</option>
        </select>
      </label>
    </div>
  );
}
