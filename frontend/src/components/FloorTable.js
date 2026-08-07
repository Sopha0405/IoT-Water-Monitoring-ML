import { Pill } from './Pill';

export function FloorTable({ floors, loading, onEdit, onDelete }) {
  return (
    <section className="panel table-panel">
      <h2>Gestion de pisos ({floors.length})</h2>
      <table>
        <thead>
          <tr>
            <th>Codigo</th>
            <th>Nombre</th>
            <th>Descripcion</th>
            <th>Dispositivos</th>
            <th>Estado</th>
            <th>Acciones</th>
          </tr>
        </thead>
        <tbody>
          {floors.map((floor) => (
            <tr key={floor.id}>
              <td><strong>{floor.code}</strong></td>
              <td>{floor.name}</td>
              <td>{floor.description || '-'}</td>
              <td>{floor.device_count ?? 0}</td>
              <td><Pill tone={floor.is_active ? 'success' : 'warning'}>{floor.is_active ? 'Activo' : 'Inactivo'}</Pill></td>
              <td className="actions">
                <button onClick={() => onEdit(floor)} disabled={loading}>Editar</button>
                <button className="delete" onClick={() => onDelete(floor)} disabled={loading || Number(floor.device_count || 0) > 0}>Eliminar</button>
              </td>
            </tr>
          ))}
          {!floors.length && (
            <tr>
              <td colSpan="6">No se encontraron pisos registrados.</td>
            </tr>
          )}
        </tbody>
      </table>
    </section>
  );
}
