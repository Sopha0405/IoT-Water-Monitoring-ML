from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
from scipy.stats import linregress

from app.modules.ml_analysis.features.constants import (
    DEFAULT_TIMEZONE,
    FEATURE_NAMES,
    FEATURE_SCHEMA_VERSION,
    FLOW_ACTIVE_MIN_LPM,
    HISTORY_SIZE,
    MICROFLOW_MAX_LPM,
    PIPELINE_VERSION,
    SAMPLE_SECONDS,
    WINDOW_SIZE,
)
from app.modules.ml_analysis.features.references import expected_hourly_flow, validate_reference
from app.modules.ml_analysis.features.temporal import deviation_vs_expected, hour_cycle, is_working_hours, month_cycle
from app.modules.ml_analysis.streaming.types import FlowReading


def normalize_timestamp(value: datetime | str, timezone_name: str = DEFAULT_TIMEZONE) -> datetime:
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        parsed = value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
    return parsed.astimezone(ZoneInfo(timezone_name))


def extract_features(
    current_window: list[FlowReading],
    history_30m: list[FlowReading],
    reference: dict[str, Any] | None,
    temporal_context: dict[str, Any] | None,
) -> dict[str, float]:
    reference = validate_reference(reference)
    temporal_context = temporal_context or {}
    if len(current_window) != WINDOW_SIZE:
        raise ValueError("current_window debe tener exactamente 60 lecturas")
    if not history_30m or history_30m[-1] != current_window[-1]:
        raise ValueError("history_30m debe terminar en la misma lectura que current_window")
    if any(item.timestamp > current_window[-1].timestamp for item in history_30m):
        raise ValueError("history_30m contiene datos futuros")

    values = np.asarray([item.flow_lpm for item in current_window], dtype=float)
    history_values = np.asarray([item.flow_lpm for item in history_30m[-HISTORY_SIZE:]], dtype=float)
    if not np.all(np.isfinite(values)) or not np.all(np.isfinite(history_values)):
        raise ValueError("Las lecturas deben ser finitas")

    sample_seconds = float(current_window[-1].sample_seconds)
    elapsed_minutes = np.arange(values.size, dtype=float) * sample_seconds / 60.0
    active = values >= FLOW_ACTIVE_MIN_LPM
    micro = (values >= FLOW_ACTIVE_MIN_LPM) & (values <= MICROFLOW_MAX_LPM)
    local_ts = current_window[-1].timestamp.astimezone(ZoneInfo(str(temporal_context.get("timezone", DEFAULT_TIMEZONE))))
    hour_decimal = local_ts.hour + local_ts.minute / 60.0 + local_ts.second / 3600.0
    expected_hour = expected_hourly_flow(reference, local_ts.hour)
    hora_sin, hora_cos = hour_cycle(hour_decimal)
    mes_sin, mes_cos = month_cycle(local_ts.month)

    features = {
        "mu_q": float(np.mean(values)),
        "sigma_q": float(np.std(values, ddof=0)),
        "min_q": float(np.min(values)),
        "max_q": float(np.max(values)),
        "iqr_q": float(np.percentile(values, 75) - np.percentile(values, 25)),
        "slope_q": float(linregress(elapsed_minutes, values).slope),
        "v_ventana": float(np.sum(values) * sample_seconds / 60.0),
        "pct_tiempo_con_flujo_5min": float(np.mean(active)),
        "pct_microflujo_5min": float(np.mean(micro)),
        "mediana_caudal_5min": float(np.median(values)),
        "duracion_microflujo_continuo_seg": float(_longest_run_seconds(micro, sample_seconds)),
        "num_arranques_5min": float(_count_starts(active)),
        "caudal_promedio_30min": float(np.mean(history_values)),
        "num_ventanas_consecutivas_microflujo": float(temporal_context.get("microflow_windows", 0.0)),
        "delta_v_dia": float(temporal_context.get("delta_v_dia", 0.0)),
        "desviacion_vs_patron_hora": deviation_vs_expected(float(np.mean(values)), expected_hour),
        "r_hora": expected_hour,
        "hora_sin": hora_sin,
        "hora_cos": hora_cos,
        "dia_semana": float(local_ts.weekday()),
        "horario_laboral": is_working_hours(local_ts.weekday(), local_ts.hour),
        "mes_sin": mes_sin,
        "mes_cos": mes_cos,
        "sensor_id_enc": _encode_sensor_id(current_window[-1].sensor_id),
    }
    ordered = {name: float(features[name]) for name in FEATURE_NAMES}
    if len(ordered) != 24 or list(ordered) != FEATURE_NAMES:
        raise RuntimeError("Orden o cantidad invalida de features")
    if not np.all(np.isfinite(list(ordered.values()))):
        raise RuntimeError("features no finitas")
    return ordered


def _longest_run_seconds(mask: np.ndarray, sample_seconds: float) -> float:
    longest = current = 0
    for value in mask:
        current = current + 1 if bool(value) else 0
        longest = max(longest, current)
    return longest * sample_seconds


def _count_starts(mask: np.ndarray) -> int:
    previous = False
    starts = 0
    for value in mask:
        current = bool(value)
        if current and not previous:
            starts += 1
        previous = current
    return starts


def _encode_sensor_id(sensor_id: str) -> float:
    digest = hashlib.sha256(sensor_id.strip().encode("utf-8")).hexdigest()
    return float(int(digest[:12], 16) % 10_000)




