import { Pill } from './Pill';
import { statusClass } from '../lib/constants';

export function buildHourlyRows(points) {
  const flowPoints = points
    .filter((point) => point.field === 'flow_lpm')
    .slice()
    .sort((a, b) => a.timestamp - b.timestamp);

  return flowPoints.slice(-12).map((point, index, list) => {
    const previous = list[index - 1]?.value ?? point.value;
    const status = point.value >= 20 ? 'Elevado' : 'Normal';
    return {
      hour: point.time ? new Date(point.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '--:--',
      consumption: Number(point.value || 0).toFixed(2),
      trend: point.value >= previous ? 'up' : 'down',
      status,
      sensor: point.device_id || '-',
    };
  }).reverse();
}

export function FlowHistoryTable({ floor, rows }) {
  return (
    <section className="panel table-panel">
      <h2>Registro reciente - {floor}</h2>
      <table>
        <thead>
          <tr>
            <th>Hora</th>
            <th>Sensor</th>
            <th>Caudal (L/min)</th>
            <th>Tendencia</th>
            <th>Estado</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row.hour}-${row.sensor}-${index}`}>
              <td>{row.hour}</td>
              <td>{row.sensor}</td>
              <td>{row.consumption}</td>
              <td><span className={`trend ${row.trend}`}>{row.trend === 'up' ? 'sube' : 'baja'}</span></td>
              <td><Pill tone={statusClass(row.status)}>{row.status}</Pill></td>
            </tr>
          ))}
          {!rows.length && (
            <tr>
              <td colSpan="5">No se encontraron registros para el periodo seleccionado.</td>
            </tr>
          )}
        </tbody>
      </table>
    </section>
  );
}
