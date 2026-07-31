import { apiRequest } from '../lib/api';

export const TELEMETRY_REFRESH_MS = 5000;
export const TELEMETRY_HISTORY_LIMIT = 500;

export async function getLatestTelemetry(token, { floor = 'PB', field = 'flow_lpm', limit = TELEMETRY_HISTORY_LIMIT } = {}) {
  const params = new URLSearchParams({
    field,
    limit: String(limit),
  });
  if (floor && floor !== 'Todos') {
    params.set('floor', floor);
  }
  return apiRequest(`/api/v1/telemetry/latest?${params.toString()}`, { token });
}

export function normalizeTelemetryPoint(point) {
  const timestamp = new Date(point?.time).getTime();
  const value = Number(point?.value);
  return {
    ...point,
    timestamp,
    value: Number.isFinite(value) ? value : 0,
  };
}

export function sortTelemetryAsc(points) {
  return points
    .map(normalizeTelemetryPoint)
    .filter((point) => Number.isFinite(point.timestamp))
    .sort((a, b) => a.timestamp - b.timestamp);
}
