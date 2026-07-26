import { apiRequest } from '../lib/api';

export interface ModelMetrics {
  precision: number | null;
  recall: number | null;
  f1: number | null;
  fpr: number | null;
  pr_auc?: number | null;
  roc_auc?: number | null;
}

export interface ModelSummary {
  exists: boolean;
  valid?: boolean;
  version: string | null;
  status: string;
  algorithm?: string | null;
  threshold: number | null;
  metrics: ModelMetrics;
  trained_at: string | null;
  promoted_at?: string | null;
  model_path?: string | null;
  sha256: string | null;
  schema_version: string | null;
  pipeline_version: string | null;
  feature_count: number | null;
  recommendation: string | null;
  warnings: string[];
  errors?: string[];
}

export interface RetrainingJob {
  jobId?: number;
  id?: number;
  status?: string;
  sourcePath?: string | null;
  dataset?: string | null;
  period?: { start: string; end: string };
  progress?: number | string;
  currentStep?: string;
  step?: string;
  error?: string;
  candidateVersion?: string;
}

export interface ModelAdminStatus {
  active: ModelSummary | null;
  candidate: ModelSummary | null;
  retraining_jobs: RetrainingJob[];
  can_promote: boolean;
  can_reject: boolean;
  can_rollback: boolean;
}

export function getModelAdminStatus(token: string): Promise<ModelAdminStatus> {
  return apiRequest('/api/v1/ml-analysis/admin/status', { token });
}

export function getActiveModel(token: string) {
  return getModelAdminStatus(token);
}

export function getCandidateModel(token: string) {
  return getModelAdminStatus(token);
}

export function getModelComparison(token: string) {
  return getModelAdminStatus(token);
}

export function getModelHistory(token: string) {
  return apiRequest('/api/v1/admin/ml/retraining/models/history', { token }).catch(() => []);
}

export function getRetrainingJobs(token: string) {
  return apiRequest('/api/v1/admin/ml/retraining/jobs', { token }).catch(() => []);
}

export function getRetrainingJob(token: string, id: number | string) {
  return apiRequest(`/api/v1/admin/ml/retraining/${id}/export-summary`, { token });
}

export function prepareDatasetFromInflux(token: string, payload = {}) {
  return apiRequest('/api/v1/admin/ml/retraining/from-influx', {
    token,
    method: 'POST',
    body: payload,
  });
}

export function startTraining(token: string, jobId: number | string) {
  return apiRequest(`/api/v1/admin/ml/retraining/${jobId}/train`, {
    token,
    method: 'POST',
  });
}

export function promoteCandidate(token: string, jobId: number | string | null, reason: string) {
  return apiRequest('/api/v1/ml-analysis/promote', {
    token,
    method: 'POST',
    body: { job_id: jobId, reason },
  });
}

export function rejectCandidate(token: string, jobId: number | string | null, reason: string) {
  return apiRequest('/api/v1/ml-analysis/reject', {
    token,
    method: 'POST',
    body: { job_id: jobId, reason: reason || 'Rechazo administrativo del candidato' },
  });
}

export function rollbackModel(token: string, version: string) {
  return apiRequest('/api/v1/ml-analysis/rollback', {
    token,
    method: 'POST',
    body: { version },
  });
}

export function getAlerts(token: string, params: { status?: string; floor?: string } = {}) {
  const query = new URLSearchParams();
  if (params.status) query.set('status', params.status);
  if (params.floor) query.set('floor', params.floor);
  const suffix = query.toString() ? `?${query.toString()}` : '';
  return apiRequest(`/api/v1/alerts${suffix}`, { token });
}

export async function getAlert(token: string, id: number | string) {
  try {
    return await apiRequest(`/api/v1/alerts/${id}`, { token });
  } catch (err) {
    const alerts = await getAlerts(token);
    const alert = alerts.find((item) => String(item.id) === String(id));
    if (!alert) throw err;
    return alert;
  }
}

export async function updateAlertStatus(token: string, id: number | string, status: string, payload: { observations?: string } = {}) {
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

export function submitAlertFeedback(token: string, id: number | string, payload: Record<string, unknown>) {
  return apiRequest(`/api/v1/ml/feedback/${id}`, {
    token,
    method: 'POST',
    body: payload,
  });
}
