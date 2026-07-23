from __future__ import annotations

import asyncio
import json
import logging
import smtplib
import time
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import ks_2samp
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.alerts.model import Alert
from app.modules.ml_analysis.isolation_forest import FEATURE_NAMES, IsolationForestModel
from app.modules.ml_analysis.model import ACTIVE_MODEL_PATH, MLAnalysis
from app.modules.ml_analysis.schemas import DriftReport, InferenceResponse
from app.modules.telemetry.service import get_latest_telemetry

logger = logging.getLogger(__name__)

_model_cache: IsolationForestModel | None = None
_last_drift_report: DriftReport | None = None
_positive_slope_windows: dict[str, int] = {}


def get_last_drift_report() -> DriftReport | None:
    """Retorna el ultimo reporte de drift calculado."""
    return _last_drift_report


async def run_inference(sensor_id: str, db_influx: Any = None, db_postgres: Session | None = None) -> InferenceResponse:
    """Ejecuta inferencia en tiempo real sobre las ultimas 60 lecturas de un sensor."""
    started = time.perf_counter()
    model = _load_active_model()
    points = await asyncio.to_thread(get_latest_telemetry, device_id=sensor_id, field="flow_lpm", limit=60)
    readings = [float(point.value) for point in reversed(points) if point.value is not None]
    if len(readings) < 10:
        raise ValueError("Se requieren al menos 10 lecturas para inferencia")

    context = _build_context(points, db_postgres)
    features = model._extract_features(readings, sensor_id, context)
    prediction = model.predict(features)
    anomaly_type = _classify_anomaly_type(sensor_id, features[0], prediction["score"])
    processed_at = datetime.utcnow()
    latency_ms = (time.perf_counter() - started) * 1000
    if latency_ms > 500:
        logger.warning("Inferencia lenta para %s: %.2f ms", sensor_id, latency_ms)
    return InferenceResponse(
        sensor_id=sensor_id,
        score=prediction["score"],
        severity=prediction["severity"],
        confidence=prediction["confidence"],
        anomaly_type=anomaly_type,
        prediction=prediction["prediction"],
        processed_at=processed_at,
        latency_ms=round(latency_ms, 2),
    )


async def create_alert(inference_result: InferenceResponse, db_postgres: Session, mqtt_client: Any = None) -> Alert | None:
    """Crea alerta, registra analisis ML, publica MQTT y envia SMTP si aplica."""
    if inference_result.severity == "normal":
        return None

    alert = Alert(
        device_id=inference_result.sensor_id,
        floor=None,
        anomaly_type=inference_result.anomaly_type,
        severity=inference_result.severity,
        risk_percentage=round(abs(inference_result.score) * 100, 1),
        status="pendiente",
        description=f"Anomalia {inference_result.severity} detectada por IsolationForest.",
        detected_at=datetime.utcnow(),
    )
    db_postgres.add(alert)
    db_postgres.flush()
    analysis = MLAnalysis(
        alert_id=alert.id,
        device_id=inference_result.sensor_id,
        floor=None,
        observed_value=None,
        model_name="IsolationForest",
        anomaly_score=inference_result.score,
        prediction=inference_result.prediction,
        confidence=inference_result.confidence,
        processed_at=inference_result.processed_at,
    )
    db_postgres.add(analysis)
    db_postgres.commit()
    db_postgres.refresh(alert)

    payload = json.dumps(inference_result.model_dump(mode="json"))
    if mqtt_client is not None:
        await asyncio.to_thread(mqtt_client.publish, "sofia/agua/alertas", payload, qos=1)
    if inference_result.severity in {"anomalo_moderado", "anomalo_critico"}:
        await _send_supervisor_email(inference_result)
    return alert


def _classify_anomaly_type(sensor_id: str, features: np.ndarray, score: float) -> str:
    """Clasifica el tipo de anomalia con reglas de negocio sobre features."""
    data = dict(zip(FEATURE_NAMES, features))
    if data["horario_laboral"] == 0 and data["mu_q"] > 1.5 and data["min_q"] > 0.5:
        return "fuga_sostenida_nocturna"
    if data["max_q"] > 12.0 and int(data["r_hora"]) not in {7, 8, 12, 13, 18, 19}:
        return "pico_caudal_anomalo"
    _positive_slope_windows[sensor_id] = _positive_slope_windows.get(sensor_id, 0) + 1 if data["slope_q"] > 0.2 else 0
    if _positive_slope_windows[sensor_id] >= 3:
        return "consumo_creciente"
    historical_mean = max(float(data.get("v_ventana", 0.0)), 0.001)
    if data["delta_v_dia"] > 2.5 * historical_mean:
        return "consumo_excesivo_diario"
    return "anomalia_no_clasificada" if score < 0 else "normal"


async def compute_drift(
    X_train: np.ndarray,
    X_prod: np.ndarray,
    db_postgres: Session | None = None,
    baseline_alert_rate: float = 1.0,
) -> DriftReport:
    """Calcula drift con KS test y triggers operativos."""
    global _last_drift_report
    train = np.asarray(X_train, dtype=float)
    prod = np.asarray(X_prod, dtype=float)
    ks_scores = [float(ks_2samp(train[:, idx], prod[:, idx]).statistic) for idx in range(train.shape[1])]
    trigger_a = sum(score > 0.10 for score in ks_scores) >= 3
    trigger_b = False
    trigger_c = False
    if db_postgres is not None:
        today = datetime.utcnow() - timedelta(days=1)
        alerts_today = db_postgres.query(func.count(Alert.id)).filter(Alert.detected_at >= today).scalar() or 0
        trigger_b = abs(alerts_today - baseline_alert_rate) / max(baseline_alert_rate, 0.001) > 0.30
        attended = db_postgres.query(func.count(Alert.id)).filter(Alert.attended_by.isnot(None)).scalar() or 0
        trigger_c = attended > 300
    _last_drift_report = DriftReport(
        generated_at=datetime.utcnow(),
        ks_scores=ks_scores,
        trigger_a=trigger_a,
        trigger_b=trigger_b,
        trigger_c=trigger_c,
        drift_detected=trigger_a or trigger_b or trigger_c,
    )
    return _last_drift_report


def _load_active_model() -> IsolationForestModel:
    """Carga el modelo activo desde disco y mantiene cache en memoria."""
    global _model_cache
    if _model_cache is None:
        if not Path(ACTIVE_MODEL_PATH).exists():
            raise RuntimeError("Modelo no cargado")
        _model_cache = IsolationForestModel.load(ACTIVE_MODEL_PATH)
    return _model_cache


def _build_context(points: list[Any], db_postgres: Session | None) -> dict[str, Any]:
    """Construye contexto temporal y volumetrico para extraccion de features."""
    timestamp = points[0].time if points and points[0].time else datetime.utcnow()
    return {
        "timestamp": timestamp.replace(tzinfo=None) if getattr(timestamp, "tzinfo", None) else timestamp,
        "sample_seconds": 5,
        "delta_v_dia": 0.0,
        "r_hora": timestamp.hour,
    }


async def _send_supervisor_email(inference_result: InferenceResponse) -> None:
    """Envia correo SMTP al supervisor si las variables de entorno estan configuradas."""
    import os

    host = os.getenv("SMTP_HOST")
    to_email = os.getenv("SMTP_SUPERVISOR_EMAIL")
    if not host or not to_email:
        logger.info("SMTP no configurado; se omite correo de alerta ML")
        return
    message = EmailMessage()
    message["Subject"] = f"Alerta ML {inference_result.severity}"
    message["From"] = os.getenv("SMTP_FROM", "noreply@sofia.local")
    message["To"] = to_email
    message.set_content(f"Sensor {inference_result.sensor_id}: {inference_result.anomaly_type}")
    def send() -> None:
        """Abre una conexion SMTP temporal y envia el mensaje."""
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "25"))) as smtp:
            smtp.send_message(message)

    await asyncio.to_thread(send)
