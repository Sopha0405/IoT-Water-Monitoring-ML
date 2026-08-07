import { apiRequest } from '../lib/api';

export function getModelAdminStatus(token) {
  return apiRequest('/api/v1/ml-analysis/admin/status', { token });
}

export function getActiveModel(token) {
  return getModelAdminStatus(token);
}

export function getCandidateModel(token) {
  return getModelAdminStatus(token);
}

export function getModelComparison(token) {
  return getModelAdminStatus(token);
}

export function getRetrainingJobs(token) {
  return apiRequest('/api/v1/admin/ml/retraining/jobs', { token }).catch(() => []);
}

export function getRetrainingJob(token, id) {
  return apiRequest(`/api/v1/admin/ml/retraining/${id}/export-summary`, { token });
}

export function prepareDatasetFromInflux(token, payload = {}) {
  return apiRequest('/api/v1/admin/ml/retraining/from-influx', {
    token,
    method: 'POST',
    body: payload,
  });
}

export function startTraining(token, jobId) {
  return apiRequest(`/api/v1/admin/ml/retraining/${jobId}/train`, {
    token,
    method: 'POST',
  });
}

export function promoteCandidate(token, jobId, reason) {
  return apiRequest('/api/v1/ml-analysis/promote', {
    token,
    method: 'POST',
    body: { job_id: jobId, reason, acknowledgedWarnings: true },
  });
}

export function rejectCandidate(token, jobId, reason) {
  return apiRequest('/api/v1/ml-analysis/reject', {
    token,
    method: 'POST',
    body: { job_id: jobId, reason: reason || 'Rechazo administrativo del candidato' },
  });
}

export function rollbackModel(token, version) {
  return apiRequest('/api/v1/ml-analysis/rollback', {
    token,
    method: 'POST',
    body: { version },
  });
}

export function getAlerts(token, params = {}) {
  const query = new URLSearchParams();
  if (params.status) query.set('status', params.status);
  if (params.floor) query.set('floor', params.floor);
  const suffix = query.toString() ? `?${query.toString()}` : '';
  return apiRequest(`/api/v1/alerts${suffix}`, { token });
}

export async function getAlert(token, id) {
  try {
    return await apiRequest(`/api/v1/alerts/${id}`, { token });
  } catch (err) {
    const alerts = await getAlerts(token);
    const alert = alerts.find((item) => String(item.id) === String(id));
    if (!alert) throw err;
    return alert;
  }
}

export async function updateAlertStatus(token, id, status, payload = {}) {
  try {
    return await apiRequest(`/api/v1/alerts/${id}/status`, {
      token,
      method: 'PATCH',
      body: { status, ...payload },
    });
  } catch (err) {
    return apiRequest(`/api/v1/alerts/${id}`, {
      token,
      method: 'PUT',
      body: { status, description: payload.observations },
    });
  }
}

export function submitAlertFeedback(token, id, payload) {
  return apiRequest(`/api/v1/ml/feedback/${id}`, {
    token,
    method: 'POST',
    body: payload,
  });
}
