import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

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
  const requestRef = useRef({ id: 0, controller: null });

  const refresh = useCallback(async () => {
    const requestId = requestRef.current.id + 1;
    requestRef.current.controller?.abort();
    const controller = new AbortController();
    requestRef.current = { id: requestId, controller };
    setLoading(true);
    setError('');
    try {
      const data = await getLatestTelemetry(token, { floor, signal: controller.signal });
      if (requestRef.current.id !== requestId) return;
      setPoints(sortTelemetryAsc(Array.isArray(data) ? data : []));
      setLastFetchAt(Date.now());
    } catch (err) {
      if (err.name === 'AbortError' || requestRef.current.id !== requestId) return;
      setError(err.message);
    } finally {
      if (requestRef.current.id === requestId) {
        setLoading(false);
      }
    }
  }, [token, floor]);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, refreshMs);
    return () => {
      clearInterval(timer);
      requestRef.current.controller?.abort();
    };
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
