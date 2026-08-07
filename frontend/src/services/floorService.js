import { apiRequest } from '../lib/api';

export function getFloors(token, params = {}) {
  const query = new URLSearchParams();
  if (params.includeInactive) query.set('include_inactive', 'true');
  const suffix = query.toString() ? `?${query.toString()}` : '';
  return apiRequest(`/api/v1/floors/${suffix}`, { token });
}

export function getFloorById(token, id) {
  return apiRequest(`/api/v1/floors/${id}`, { token });
}

export function createFloor(token, payload) {
  return apiRequest('/api/v1/floors/', { token, method: 'POST', body: payload });
}

export function updateFloor(token, id, payload) {
  return apiRequest(`/api/v1/floors/${id}`, { token, method: 'PUT', body: payload });
}

export function deleteFloor(token, id) {
  return apiRequest(`/api/v1/floors/${id}`, { token, method: 'DELETE' });
}
