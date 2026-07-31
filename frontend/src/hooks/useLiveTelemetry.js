import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  getLatestTelemetry,
  sortTelemetryAsc,
  TELEMETRY_REFRESH_MS,
} from '../services/telemetryService';

export function useLiveTelemetry(token, { floor, refreshMs = TELEMETRY_REFRESH_MS } = {}) {
  const [points, setPoints] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [lastFetchAt, setLastFetchAt] = useState(null);
  const [now, setNow] = useState(Date.now());

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await getLatestTelemetry(token, { floor });
      setPoints(sortTelemetryAsc(Array.isArray(data) ? data : []));
      setLastFetchAt(Date.now());
    } catch (err) {
      setError(err.message);
      setPoints([]);
    } finally {
      setLoading(false);
    }
  }, [token, floor]);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, refreshMs);
    return () => clearInterval(timer);
  }, [refresh, refreshMs]);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const latestPoint = useMemo(() => {
    if (!points.length) return null;
    return points.reduce((latest, point) => (
      !latest || point.timestamp > latest.timestamp ? point : latest
    ), null);
  }, [points]);
  const source = useMemo(() => {
    if (!points.length) return 'empty';
    return points.some((point) => point.source === 'real') ? 'real' : 'demo';
  }, [points]);

  return {
    points,
    latestPoint,
    source,
    loading,
    error,
    now,
    lastFetchAt,
    refresh,
  };
}
