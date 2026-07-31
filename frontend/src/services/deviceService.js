import { apiRequest } from '../lib/api';

export function getActiveTelemetryDevices(token, params = {}) {
  const query = new URLSearchParams();
  if (params.floor && params.floor !== 'Todos') query.set('floor', params.floor);
  if (params.limit) query.set('limit', String(params.limit));
  const suffix = query.toString() ? `?${query.toString()}` : '';
  return apiRequest(`/api/v1/devices/active-telemetry${suffix}`, { token });
}

export function getIotConfig(token) {
  return apiRequest('/api/v1/devices/iot/config', { token });
}

export function createDevice(token, payload) {
  return apiRequest('/api/v1/devices/', { token, method: 'POST', body: payload });
}

export function updateDevice(token, id, payload) {
  return apiRequest(`/api/v1/devices/${id}`, { token, method: 'PUT', body: payload });
}

export function deleteDevice(token, id) {
  return apiRequest(`/api/v1/devices/${id}`, { token, method: 'DELETE' });
}
