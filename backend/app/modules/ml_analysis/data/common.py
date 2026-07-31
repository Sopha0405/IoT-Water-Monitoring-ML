from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

LOCAL_TIMEZONE = "America/La_Paz"
SAMPLE_SECONDS = 5
INTERVAL_TOLERANCE_SECONDS = 1
CANONICAL_COLUMNS = {
    "timestamp": ["timestamp", "ts", "time", "fecha_hora"],
    "sensor_id": ["sensor_id", "device_id", "sensor"],
    "flow_lpm": ["flow_lpm", "caudal_lpm", "flow"],
    "status": ["status", "estado"],
    "event_id": ["event_id", "scenario_event_id", "evento_id"],
    "actual_label": ["actual_label", "label", "is_anomaly", "is_anomaly_active"],
    "actual_type": ["actual_type", "anomaly_type", "event_type", "scenario", "tipo_anomalia", "tipo_evento"],
    "anomaly_severity": ["anomaly_severity", "severity", "severidad"],
    "label_status": ["label_status", "label_source", "estado_etiqueta"],
    "is_sensor_error": ["is_sensor_error", "sensor_error"],
    "is_normal_difficult": ["is_normal_difficult", "es_normal_dificil", "normal_dificil"],
    "is_maintenance": ["is_maintenance", "es_mantenimiento", "maintenance"],
    "is_injected_anomaly": ["is_injected_anomaly", "es_anomalia_inyectada"],
    "is_post_event": ["is_post_event", "is_post_event_window"],
    "baseline_train_eligible": ["baseline_train_eligible", "apto_entrenamiento_baseline"],
}
TECHNICAL_STATUSES = {"sensor_error", "desconectado", "error_lectura", "maintenance", "mantenimiento", "offline"}
SUSPICIOUS_UNKNOWN_STATUSES = {"unknown", "desconocido"}
NORMAL_STATUSES = {"ok", "activo", "normal"}
ANOMALY_TYPES = {"microleak", "sustained_leak", "peak", "growing_consumption", "fuga", "fuga_sostenida", "pico"}


@dataclass(frozen=True)
class SplitPaths:
    train: Path
    validation: Path
    test: Path
    report: Path


def normalize_reading_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    rename: dict[str, str] = {}
    lower_to_original = {column.lower(): column for column in result.columns}
    for canonical, candidates in CANONICAL_COLUMNS.items():
        for candidate in candidates:
            if candidate.lower() in lower_to_original:
                rename[lower_to_original[candidate.lower()]] = canonical
                break
    result.rename(columns=rename, inplace=True)
    if "timestamp" in result:
        result["timestamp"] = pd.to_datetime(result["timestamp"], errors="coerce", utc=True)
    if "sensor_id" in result:
        result["sensor_id"] = result["sensor_id"].astype("string").fillna("").str.strip()
    if "flow_lpm" in result:
        result["flow_lpm"] = pd.to_numeric(result["flow_lpm"], errors="coerce")
    if "status" not in result:
        result["status"] = "ok"
    result["status"] = result["status"].astype("string").fillna("unknown").str.strip().str.lower()
    for column in ["event_id", "actual_type", "anomaly_severity", "label_status"]:
        if column not in result:
            result[column] = None
    for column in [
        "is_sensor_error",
        "is_normal_difficult",
        "is_maintenance",
        "is_injected_anomaly",
        "is_post_event",
        "baseline_train_eligible",
    ]:
        if column not in result:
            result[column] = False
        result[column] = result[column].fillna(False).astype(bool)
    if "actual_label" not in result:
        result["actual_label"] = result["actual_type"].astype("string").str.lower().isin(ANOMALY_TYPES).astype(int)
    else:
        result["actual_label"] = pd.to_numeric(result["actual_label"], errors="coerce").fillna(0).astype(int)
    return result


def add_interval_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.sort_values(["sensor_id", "timestamp"]).copy()
    result["interval_seconds"] = result.groupby("sensor_id")["timestamp"].diff().dt.total_seconds()
    result["is_duplicate"] = result.duplicated(["sensor_id", "timestamp"], keep=False)
    result["is_out_of_order"] = False
    irregular = result["interval_seconds"].notna() & (
        (result["interval_seconds"] - SAMPLE_SECONDS).abs() > INTERVAL_TOLERANCE_SECONDS
    )
    result["is_irregular_interval"] = irregular
    result["local_date"] = result["timestamp"].dt.tz_convert(LOCAL_TIMEZONE).dt.date.astype("string")
    return result


def stable_frame_hash(frame: pd.DataFrame, columns: list[str] | None = None) -> str:
    selected = frame[columns] if columns else frame
    hashed = pd.util.hash_pandas_object(selected.reset_index(drop=True), index=True)
    return hashlib_bytes(hashed.to_numpy(dtype=np.uint64).tobytes())


def hashlib_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def ensure_columns(frame: pd.DataFrame, required: list[str]) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError("Faltan columnas requeridas: " + ", ".join(missing))


def json_default(value: Any) -> Any:
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    return str(value)




