from __future__ import annotations

import asyncio
import json
import logging
import os
import smtplib
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import ks_2samp
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.alerts.model import Alert
from app.modules.ml_analysis.alerts.policy import microleak_rule
from app.modules.ml_analysis.features.constants import (
    DEFAULT_TIMEZONE,
    FEATURE_NAMES,
    SAMPLE_SECONDS,
    WINDOW_SIZE,
)
from app.modules.ml_analysis.features.extractor import normalize_timestamp
from app.modules.ml_analysis.inference.isolation_forest import IsolationForestModel
from app.modules.ml_analysis.inference.model import ACTIVE_MODEL_PATH, MLAnalysis, ModelManager
from app.modules.ml_analysis.api.schemas import DriftReport, InferenceResponse
from app.modules.telemetry.service import get_latest_telemetry

logger = logging.getLogger(__name__)

_model_cache: IsolationForestModel | None = None
_model_cache_mtime_ns: int | None = None
_last_drift_report: DriftReport | None = None


def get_last_drift_report() -> DriftReport | None:
    return _last_drift_report


def clear_model_cache() -> None:
    global _model_cache, _model_cache_mtime_ns
    _model_cache = None
    _model_cache_mtime_ns = None


async def run_inference(
    sensor_id: str,
    db_influx: Any = None,
    db_postgres: Session | None = None,
) -> InferenceResponse:
    """Analiza exactamente las Ãºltimas 60 lecturas vÃ¡lidas del sensor."""
    del db_influx, db_postgres
    started = time.perf_counter()
    model = _load_active_model()

    flow_field = os.getenv("INFLUX_FLOW_FIELD", "flow_lpm")
    raw_points = await asyncio.to_thread(
        get_latest_telemetry,
        device_id=sensor_id,
        field=flow_field,
        limit=WINDOW_SIZE,
    )
    points = _prepare_points(raw_points)
    readings = np.asarray([float(point.value) for point in points], dtype=float)

    daily_volume = await _read_current_daily_volume(sensor_id)
    window_end = normalize_timestamp(points[-1].time, DEFAULT_TIMEZONE)
    expected_daily_volume = _expected_daily_volume(
        model=model,
        sensor_id=sensor_id,
        timestamp=window_end,
    )
    delta_v_dia = daily_volume - expected_daily_volume

    features = model.extract_features(
        readings,
        sensor_id,
        {
            "timestamp": window_end,
            "sample_seconds": SAMPLE_SECONDS,
            "delta_v_dia": delta_v_dia,
            "r_hora": window_end.hour,
            "timezone": DEFAULT_TIMEZONE,
        },
    )
    prediction = model.predict(features)
    forced_anomaly_type = _rule_based_anomaly_type(features[0])
    if forced_anomaly_type is not None and prediction["prediction"] == "normal":
        prediction = {
            **prediction,
            "prediction": "anomaly",
            "severity": "medium",
            "confidence": max(float(prediction["confidence"]), 0.72),
        }
    anomaly_type = _classify_anomaly_type(
        features[0], prediction["prediction"], forced_anomaly_type=forced_anomaly_type
    )

    status = ModelManager().get_status()
    processed_at = datetime.now(timezone.utc)
    latency_ms = (time.perf_counter() - started) * 1000.0
    if latency_ms > 500:
        logger.warning("Inferencia lenta para %s: %.2f ms", sensor_id, latency_ms)

    return InferenceResponse(
        sensor_id=sensor_id,
        model_version=status.active_version,
        score=prediction["score"],
        severity=prediction["severity"],
        confidence=prediction["confidence"],
        anomaly_type=anomaly_type,
        prediction=prediction["prediction"],
        observed_value=float(features[0][FEATURE_NAMES.index("mu_q")]),
        window_start=normalize_timestamp(points[0].time, DEFAULT_TIMEZONE),
        window_end=window_end,
        samples_used=WINDOW_SIZE,
        processed_at=processed_at,
        latency_ms=round(latency_ms, 2),
    )


async def persist_inference_result(
    result: InferenceResponse,
    db_postgres: Session,
    mqtt_client: Any = None,
) -> Alert | None:
    """Registra toda predicciÃ³n y crea alerta solo para anomalÃ­as no duplicadas."""
    model_label = "IsolationForest"
    if result.model_version:
        model_label = f"IsolationForest:{result.model_version[:16]}"

    analysis = MLAnalysis(
        alert_id=None,
        device_id=result.sensor_id,
        floor=None,
        observed_value=result.observed_value,
        model_name=model_label,
        anomaly_score=result.score,
        prediction=result.prediction,
        confidence=result.confidence,
        processed_at=_naive_utc(result.processed_at),
    )
    db_postgres.add(analysis)

    alert: Alert | None = None
    try:
        db_postgres.flush()
        if result.prediction == "anomaly" and _is_operational_alert_confirmed(result, db_postgres):
            alert = _find_recent_open_alert(result, db_postgres)
            if alert is None:
                alert = Alert(
                    device_id=result.sensor_id,
                    floor=None,
                    anomaly_type=result.anomaly_type,
                    severity=result.severity,
                    risk_percentage=result.confidence,
                    status="pendiente",
                    description=(
                        f"{result.anomaly_type} detectada por Isolation Forest "
                        f"con {result.samples_used} lecturas."
                    ),
                    detected_at=_naive_utc(result.processed_at),
                )
                db_postgres.add(alert)
                db_postgres.flush()
            analysis.alert_id = alert.id
        db_postgres.commit()
        if alert is not None:
            db_postgres.refresh(alert)
    except Exception:
        db_postgres.rollback()
        raise

    if alert is not None:
        payload = json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
        if mqtt_client is not None:
            await asyncio.to_thread(
                mqtt_client.publish,
                "sofia/agua/alertas",
                payload,
                qos=1,
            )
        if result.severity in {"anomalo_moderado", "anomalo_critico"}:
            await _send_supervisor_email(result)
    return alert


async def create_alert(
    inference_result: InferenceResponse,
    db_postgres: Session,
    mqtt_client: Any = None,
) -> Alert | None:
    """Alias compatible: persiste el anÃ¡lisis y crea alerta cuando corresponde."""
    return await persist_inference_result(
        inference_result, db_postgres, mqtt_client=mqtt_client
    )


def _prepare_points(points: list[Any]) -> list[Any]:
    valid = [
        point
        for point in points
        if getattr(point, "value", None) is not None
        and getattr(point, "time", None) is not None
    ]
    valid.sort(key=lambda point: normalize_timestamp(point.time, DEFAULT_TIMEZONE))

    if len(valid) != WINDOW_SIZE:
        raise ValueError(
            f"Se requieren exactamente {WINDOW_SIZE} lecturas; llegaron {len(valid)}"
        )

    values = np.asarray([float(point.value) for point in valid], dtype=float)
    if not np.all(np.isfinite(values)) or np.any(values < 0):
        raise ValueError("La ventana contiene caudales invÃ¡lidos")

    timestamps = [normalize_timestamp(point.time, DEFAULT_TIMEZONE) for point in valid]
    deltas = np.asarray(
        [
            (timestamps[index] - timestamps[index - 1]).total_seconds()
            for index in range(1, len(timestamps))
        ],
        dtype=float,
    )
    tolerance = float(os.getenv("ML_SAMPLE_TOLERANCE_SECONDS", "0.75"))
    if not np.all(np.isclose(deltas, SAMPLE_SECONDS, atol=tolerance)):
        raise ValueError("Las Ãºltimas 60 lecturas no mantienen intervalos de 5 segundos")
    if timestamps[0].date() != timestamps[-1].date():
        raise ValueError("La ventana cruza el cambio de dÃ­a")
    return valid


async def _read_current_daily_volume(sensor_id: str) -> float:
    field = os.getenv(
        "INFLUX_DAILY_VOLUME_FIELD", "volume_accumulated_day_m3"
    )
    points = await asyncio.to_thread(
        get_latest_telemetry,
        device_id=sensor_id,
        field=field,
        limit=1,
    )
    values = [float(point.value) for point in points if point.value is not None]
    if not values or not np.isfinite(values[0]) or values[0] < 0:
        raise RuntimeError(
            f"No existe un valor vÃ¡lido de {field} para calcular delta_v_dia"
        )
    return values[0]


def _expected_daily_volume(
    model: IsolationForestModel,
    sensor_id: str,
    timestamp: datetime,
) -> float:
    references = model.feature_context.get("daily_volume_reference_m3")
    if not isinstance(references, dict):
        raise RuntimeError(
            "El active.joblib no contiene la referencia diaria; reentrene el modelo"
        )
    values = references.get(sensor_id)
    if not isinstance(values, list) or len(values) != 1440:
        raise RuntimeError(
            f"El modelo activo no contiene referencia diaria para {sensor_id}"
        )
    minute = timestamp.hour * 60 + timestamp.minute
    value = float(values[minute])
    if not np.isfinite(value):
        raise RuntimeError("La referencia diaria contiene un valor invÃ¡lido")
    return value


def _classify_anomaly_type(
    features: np.ndarray,
    prediction: str,
    *,
    forced_anomaly_type: str | None = None,
) -> str:
    if prediction != "anomaly":
        return "normal"
    if forced_anomaly_type is not None:
        return forced_anomaly_type

    data = dict(zip(FEATURE_NAMES, features))
    if data["horario_laboral"] == 0 and data["mu_q"] > 1.5 and data["min_q"] > 0.5:
        return "fuga_sostenida_nocturna"
    if data["max_q"] > 12.0 and int(data["r_hora"]) not in {7, 8, 12, 13, 18}:
        return "pico_caudal_anomalo"

    window_volume_m3 = max(float(data["v_ventana"]) / 1000.0, 0.001)
    if data["delta_v_dia"] > max(0.05, 2.5 * window_volume_m3):
        return "consumo_excesivo_diario"
    if data["min_q"] > 0.2 and data["sigma_q"] < 0.15:
        return "flujo_sostenido"
    if data["slope_q"] > 0.2:
        return "consumo_creciente"
    return "anomalia_no_clasificada"


def _rule_based_anomaly_type(features: np.ndarray) -> str | None:
    import pandas as pd

    data = dict(zip(FEATURE_NAMES, features))
    if bool(microleak_rule(pd.DataFrame([data])).iloc[0]):
        return "microfuga"
    return None


def _is_operational_alert_confirmed(result: InferenceResponse, db_postgres: Session) -> bool:
    if result.anomaly_type in {"microfuga", "fuga_sostenida_nocturna", "flujo_sostenido", "consumo_creciente"}:
        return True
    if result.anomaly_type == "anomalia_no_clasificada":
        logger.info(
            "Prediccion general registrada sin alerta operacional sensor=%s",
            result.sensor_id,
        )
        return False
    cutoff = _naive_utc(result.processed_at) - timedelta(minutes=15)
    recent_anomalies = (
        db_postgres.query(MLAnalysis)
        .filter(
            MLAnalysis.device_id == result.sensor_id,
            MLAnalysis.prediction == "anomaly",
            MLAnalysis.processed_at >= cutoff,
        )
        .count()
    )
    if recent_anomalies >= 1:
        return True
    logger.info(
        "Prediccion anomala pendiente de confirmacion sensor=%s type=%s",
        result.sensor_id,
        result.anomaly_type,
    )
    return False


def _find_recent_open_alert(
    result: InferenceResponse,
    db_postgres: Session,
) -> Alert | None:
    cooldown_minutes = int(os.getenv("ML_ALERT_COOLDOWN_MINUTES", "15"))
    cutoff = _naive_utc(result.processed_at) - timedelta(minutes=cooldown_minutes)
    return (
        db_postgres.query(Alert)
        .filter(
            Alert.device_id == result.sensor_id,
            Alert.anomaly_type == result.anomaly_type,
            Alert.status == "pendiente",
            Alert.detected_at >= cutoff,
        )
        .order_by(Alert.detected_at.desc())
        .first()
    )


async def compute_drift(
    X_train: np.ndarray,
    X_prod: np.ndarray,
    db_postgres: Session | None = None,
    validated_false_positive_rate: float | None = None,
) -> DriftReport:
    """Compara features reales de entrenamiento y producciÃ³n mediante KS."""
    global _last_drift_report
    train = np.asarray(X_train, dtype=float)
    prod = np.asarray(X_prod, dtype=float)
    if train.ndim != 2 or prod.ndim != 2:
        raise ValueError("X_train y X_prod deben ser matrices")
    if train.shape[1] != len(FEATURE_NAMES) or prod.shape[1] != len(FEATURE_NAMES):
        raise ValueError("Las matrices no contienen las 24 features oficiales")
    if len(prod) < 30:
        raise ValueError("Se requieren al menos 30 ventanas productivas para drift")

    tests = [
        ks_2samp(train[:, index], prod[:, index])
        for index in range(len(FEATURE_NAMES))
    ]
    ks_scores = [float(test.statistic) for test in tests]
    ks_pvalues = [float(test.pvalue) for test in tests]
    trigger_a = sum(
        score > 0.10 and pvalue < 0.05
        for score, pvalue in zip(ks_scores, ks_pvalues)
    ) >= 3

    trigger_b = False
    if db_postgres is not None:
        now = datetime.utcnow()
        last_day = (
            db_postgres.query(func.count(Alert.id))
            .filter(Alert.detected_at >= now - timedelta(days=1))
            .scalar()
            or 0
        )
        previous_week = (
            db_postgres.query(func.count(Alert.id))
            .filter(
                Alert.detected_at >= now - timedelta(days=8),
                Alert.detected_at < now - timedelta(days=1),
            )
            .scalar()
            or 0
        )
        baseline_per_day = previous_week / 7.0
        if baseline_per_day > 0:
            trigger_b = abs(last_day - baseline_per_day) / baseline_per_day > 0.30

    trigger_c = (
        validated_false_positive_rate is not None
        and validated_false_positive_rate > 0.20
    )
    _last_drift_report = DriftReport(
        generated_at=datetime.now(timezone.utc),
        feature_names=FEATURE_NAMES,
        ks_scores=ks_scores,
        ks_pvalues=ks_pvalues,
        trigger_a=trigger_a,
        trigger_b=trigger_b,
        trigger_c=trigger_c,
        drift_detected=trigger_a or trigger_b or trigger_c,
    )
    return _last_drift_report


def _load_active_model() -> IsolationForestModel:
    global _model_cache, _model_cache_mtime_ns
    path = Path(ACTIVE_MODEL_PATH)
    if not path.exists():
        raise RuntimeError("No existe active.joblib")
    mtime_ns = path.stat().st_mtime_ns
    if _model_cache is None or _model_cache_mtime_ns != mtime_ns:
        _model_cache = IsolationForestModel.load(path)
        _model_cache_mtime_ns = mtime_ns
    return _model_cache


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


async def _send_supervisor_email(result: InferenceResponse) -> None:
    host = os.getenv("SMTP_HOST")
    to_email = os.getenv("SMTP_SUPERVISOR_EMAIL")
    if not host or not to_email:
        logger.info("SMTP no configurado; se omite correo de alerta ML")
        return

    message = EmailMessage()
    message["Subject"] = f"Alerta ML {result.severity}"
    message["From"] = os.getenv("SMTP_FROM", "noreply@sofia.local")
    message["To"] = to_email
    message.set_content(
        f"Sensor {result.sensor_id}: {result.anomaly_type}. "
        f"Ventana {result.window_start.isoformat()} a {result.window_end.isoformat()}."
    )

    def send() -> None:
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "25"))) as smtp:
            smtp.send_message(message)

    await asyncio.to_thread(send)




