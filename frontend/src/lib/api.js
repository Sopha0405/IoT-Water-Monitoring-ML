export const API_BASE = process.env.REACT_APP_API_BASE || 'http://localhost:8000';

function formatApiError(data, fallback) {
  const detail = data?.detail;
  if (!detail) return fallback;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => item?.msg || item?.message || JSON.stringify(item))
      .join(' ');
  }
  return detail.message || JSON.stringify(detail);
}

export async function apiRequest(path, { token, method = 'GET', body, signal } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    signal,
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(formatApiError(data, `Error HTTP ${response.status}`));
  }

  if (response.status === 204) return null;
  return response.json();
}
