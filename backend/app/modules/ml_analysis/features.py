from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
from scipy.stats import linregress

FEATURE_NAMES = [
    "mu_q",
    "sigma_q",
    "min_q",
    "max_q",
    "iqr_q",
    "slope_q",
    "v_ventana",
    "delta_v_dia",
    "r_hora",
    "hora_sin",
    "hora_cos",
    "dia_semana",
    "horario_laboral",
    "sensor_id_enc",
]


def encode_sensor_id(sensor_id: str) -> float:
    """Genera la misma codificación numérica estable usada por el modelo."""
    if not sensor_id or not sensor_id.strip():
        raise ValueError("sensor_id no puede estar vacío")
    return float(sum(ord(char) for char in sensor_id.strip()) % 10_000)


def extract_features(
    readings: list[float] | np.ndarray,
    sensor_id: str,
    context: dict[str, Any],
) -> np.ndarray:
    """
    Convierte una ventana de caudal en las 14 features del modelo.

    Contexto esperado:
    - timestamp: fecha de inicio o cierre de la ventana.
    - sample_seconds: intervalo de muestreo; por defecto 5 segundos.
    - delta_v_dia: diferencia del volumen acumulado diario respecto al histórico.
    - r_hora: hora numérica de la ventana; si no llega, se usa timestamp.hour.
    """
    values = np.asarray(readings, dtype=float)

    if values.ndim != 1:
        raise ValueError("readings debe ser una secuencia unidimensional")
    if values.size == 0:
        raise ValueError("readings no puede estar vacío")
    if not np.all(np.isfinite(values)):
        raise ValueError("readings contiene valores nulos o no finitos")
    if np.any(values < 0):
        raise ValueError("readings contiene caudales negativos")

    timestamp = context.get("timestamp") or datetime.utcnow()
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if not isinstance(timestamp, datetime):
        raise ValueError("context['timestamp'] debe ser datetime o texto ISO-8601")

    sample_seconds = float(context.get("sample_seconds", 5))
    if sample_seconds <= 0:
        raise ValueError("sample_seconds debe ser mayor que cero")

    slope = (
        float(linregress(np.arange(values.size), values).slope)
        if values.size > 1
        else 0.0
    )

    hour = int(timestamp.hour)
    weekday = int(timestamp.weekday())
    r_hora = float(context.get("r_hora", hour))

    features = np.asarray(
        [[
            float(np.mean(values)),
            float(np.std(values)),
            float(np.min(values)),
            float(np.max(values)),
            float(np.percentile(values, 75) - np.percentile(values, 25)),
            slope,
            float(np.sum(values) * sample_seconds / 60.0),
            float(context.get("delta_v_dia", 0.0)),
            r_hora,
            float(np.sin(2 * np.pi * hour / 24)),
            float(np.cos(2 * np.pi * hour / 24)),
            float(weekday),
            1.0 if weekday < 5 and 7 <= hour < 19 else 0.0,
            encode_sensor_id(sensor_id),
        ]],
        dtype=float,
    )

    if features.shape[1] != len(FEATURE_NAMES):
        raise RuntimeError(
            f"Se generaron {features.shape[1]} features; "
            f"se esperaban {len(FEATURE_NAMES)}"
        )

    return features
