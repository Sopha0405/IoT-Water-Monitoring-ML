from __future__ import annotations

import logging
import os
from datetime import timezone

import numpy as np
import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler

from app.db.postgres import SessionLocal
from app.modules.alerts.model import Alert
from app.modules.ml_analysis.alerts.policy import AlertPolicy
from app.modules.ml_analysis.alerts.policy import microleak_rule
from app.modules.ml_analysis.features.constants import FEATURE_NAMES, FEATURE_SCHEMA_VERSION
from app.modules.ml_analysis.features.extractor import extract_features
from app.modules.ml_analysis.api.router import compute_daily_drift
from app.modules.ml_analysis.inference.isolation_forest import IsolationForestModel
from app.modules.ml_analysis.inference.model import ACTIVE_MODEL_PATH, MLAnalysis, ModelManager
from app.modules.ml_analysis.streaming.buffer import SensorStreamBuffer
from app.modules.ml_analysis.streaming.types import FlowReading, parse_flow_payload
from app.modules.ml_analysis.streaming.validator import StreamValidator
from app.modules.ml_analysis.streaming.temporal_state import TemporalStateStore
from app.modules.telemetry.service import get_latest_telemetry

from .config import load_config, validate_config
from .influx_writer import InfluxWriter
from .mqtt_consumer import MqttConsumer

logger = logging.getLogger(__name__)
_model_cache: IsolationForestModel | None = None
_model_cache_mtime_ns: int | None = None
_confirmation_state: dict[tuple[str, str], int] = {}
CONFIRMATION_SECONDS = int(os.getenv("ML_ALERT_CONFIRMATION_SECONDS", "180"))
SAMPLE_SECONDS = 5


def start_drift_scheduler() -> BackgroundScheduler:
    """Inicia la tarea diaria de drift ML a las 02:00 UTC."""
    scheduler = BackgroundScheduler(timezone="UTC")

    def job() -> None:
        """Ejecuta el calculo de drift en una sesion PostgreSQL aislada."""
        import asyncio

        db = SessionLocal()
        try:
            asyncio.run(compute_daily_drift(db))
        except Exception as exc:
            logger.exception("No se pudo calcular drift diario: %s", exc)
        finally:
            db.close()

    scheduler.add_job(job, "cron", hour=2, minute=0, id="ml_daily_drift", replace_existing=True)
    scheduler.start()
    return scheduler


def main():
    """Arranca el consumidor MQTT, el writer de InfluxDB y la tarea diaria ML."""
    cfg = load_config()
    validate_config(cfg)

    scheduler = start_drift_scheduler()
    writer = InfluxWriter(cfg.influx, cfg.batch)
    writer.start()
    shadow_mode = os.getenv("ML_SHADOW_MODE", "true").lower() == "true"
    stream_buffer = SensorStreamBuffer()
    validator = StreamValidator()
    temporal_state = TemporalStateStore()
    alert_policy = AlertPolicy(
        critical_peak_lpm=float(os.getenv("ML_CRITICAL_PEAK_LPM", "20.0")),
        cooldown_minutes=int(os.getenv("ML_ALERT_COOLDOWN_MINUTES", "15")),
    )

    def handle_payload(topic: str, payload: dict):
        ok = writer.enqueue(topic, payload)
        if ok:
            print(f"[OK] {topic} -> queue")
        else:
            print(f"[DROP] queue full topic={topic}")
        _process_stream(
            payload,
            stream_buffer,
            validator,
            temporal_state,
            alert_policy,
            shadow_mode,
        )

    consumer = MqttConsumer(cfg.mqtt, handle_payload)

    try:
        print(f"[BOOT] Influx {cfg.influx.url} bucket={cfg.influx.bucket} org={cfg.influx.org}")
        print(f"[BOOT] MQTT {cfg.mqtt.host}:{cfg.mqtt.port} filter={cfg.mqtt.topic_filter}")
        consumer.start_forever()
    finally:
        scheduler.shutdown(wait=False)
        writer.stop()

def _process_stream(
    payload: dict,
    stream_buffer: SensorStreamBuffer,
    validator: StreamValidator,
    temporal_state: TemporalStateStore,
    alert_policy: AlertPolicy,
    shadow_mode: bool,
) -> None:
    if int(payload.get("schema_version", 1)) < 2:
        return
    try:
        reading = parse_flow_payload(payload)
    except ValueError as exc:
        logger.warning("Payload streaming invalido: %s", exc)
        return
    if stream_buffer.count(reading.sensor_id) == 0:
        _hydrate_buffer_from_influx(stream_buffer, reading)
    validation = validator.validate(reading, stream_buffer)
    if not validation.ok:
        if validation.error_type in {"missing_sequence", "irregular_interval"} and stream_buffer.count(reading.sensor_id) > 0:
            logger.warning(
                "Buffer reiniciado sensor=%s tipo=%s msg=%s",
                reading.sensor_id,
                validation.error_type,
                validation.message,
            )
            stream_buffer.clear(reading.sensor_id)
            retry_validation = validator.validate(reading, stream_buffer)
            if retry_validation.ok:
                stream_buffer.append(reading)
            return
        logger.warning("Lectura descartada sensor=%s tipo=%s msg=%s", reading.sensor_id, validation.error_type, validation.message)
        if validation.error_type == "sensor_error":
            state = temporal_state.for_sensor(reading.sensor_id)
            alert_policy.evaluate_sensor_error(reading.sensor_id, reading.timestamp, state)
        return
    try:
        stream_buffer.append(reading)
    except ValueError as exc:
        logger.warning("Buffer rechazo sensor=%s err=%s", reading.sensor_id, exc)
        return

    state = temporal_state.for_sensor(reading.sensor_id)
    history = stream_buffer.latest(reading.sensor_id, 360)
    if len(history) < 60:
        return
    current_window = history[-60:]
    features = extract_features(
        current_window,
        history,
        reference={},
        temporal_context={"microflow_windows": state.consecutive_microflow_windows},
    )
    state = temporal_state.update_microleak_context(
        reading.sensor_id,
        features["pct_microflujo_5min"],
        features["desviacion_vs_patron_hora"],
        features["sigma_q"],
    )
    feature_vector = np.asarray([[features[name] for name in FEATURE_NAMES]], dtype=float)
    prediction = _predict_window(feature_vector, features)
    window_id = f"{reading.sensor_id}:{current_window[0].timestamp.isoformat()}:{current_window[-1].timestamp.isoformat()}"
    state = temporal_state.update_prediction(
        reading.sensor_id,
        prediction["prediction"],
        prediction["score"],
        window_id,
    )
    alert_policy.evaluate(
        reading.sensor_id,
        reading.timestamp,
        max_flow_lpm=float(features["max_q"]),
        mean_flow_lpm=float(features["mu_q"]),
        score=float(prediction["score"]),
        prediction=prediction["prediction"],
        state=state,
    )
    operational_type = prediction["anomaly_type"] in {
        "microfuga",
        "fuga_sostenida_nocturna",
        "flujo_sostenido",
        "consumo_creciente",
    }
    confidence_pct = _confidence_percentage(float(prediction["confidence"]))
    prediction = {
        **prediction,
        "confidence": confidence_pct,
        "severity": _severity_from_confidence(confidence_pct),
    }
    confirmed = _confirmed_continuous_alert(
        reading.sensor_id,
        str(prediction["anomaly_type"]),
        operational_type and prediction["prediction"] == "anomaly",
    )
    should_alert = operational_type and confirmed and confidence_pct >= 80.0
    _persist_streaming_prediction(
        sensor_id=reading.sensor_id,
        floor=str(payload.get("floor") or ""),
        features=features,
        prediction=prediction,
        processed_at=current_window[-1].timestamp,
        should_alert=should_alert,
        shadow_mode=shadow_mode,
    )
    logger.info(
        "ML streaming shadow=%s sensor=%s window=%s schema=%s prediction=%s type=%s score=%.6f alert=%s features=%s",
        shadow_mode,
        reading.sensor_id,
        window_id,
        FEATURE_SCHEMA_VERSION,
        prediction["prediction"],
        prediction["anomaly_type"],
        prediction["score"],
        bool(should_alert and not shadow_mode),
        features,
    )
    print(
        "[ML] streaming "
        f"shadow={shadow_mode} sensor={reading.sensor_id} "
        f"prediction={prediction['prediction']} type={prediction['anomaly_type']} "
        f"score={float(prediction['score']):.6f} alert={bool(should_alert and not shadow_mode)}"
    )


def _load_active_model() -> IsolationForestModel:
    global _model_cache, _model_cache_mtime_ns
    path = ACTIVE_MODEL_PATH
    if not path.exists():
        raise RuntimeError("No existe active.joblib para inferencia streaming")
    mtime_ns = path.stat().st_mtime_ns
    if _model_cache is None or _model_cache_mtime_ns != mtime_ns:
        _model_cache = IsolationForestModel.load(path)
        _model_cache_mtime_ns = mtime_ns
    return _model_cache


def _hydrate_buffer_from_influx(stream_buffer: SensorStreamBuffer, reading: FlowReading) -> None:
    try:
        points = get_latest_telemetry(device_id=reading.sensor_id, field="flow_lpm", limit=60)
    except Exception:
        logger.exception("No se pudo hidratar buffer desde Influx sensor=%s", reading.sensor_id)
        return
    ordered = sorted(
        [
            point for point in points
            if getattr(point, "source", "real") == "real"
            and point.time is not None
            and point.value is not None
            and point.time < reading.timestamp
        ],
        key=lambda point: point.time,
    )
    warmup_points = ordered[-59:]
    first_sequence = None
    if reading.sequence_number is not None:
        first_sequence = max(0, reading.sequence_number - len(warmup_points))
    for index, point in enumerate(warmup_points):
        try:
            stream_buffer.append(
                FlowReading(
                    timestamp=point.time,
                    sensor_id=reading.sensor_id,
                    flow_lpm=float(point.value),
                    sequence_number=(first_sequence + index) if first_sequence is not None else None,
                    sample_seconds=5,
                    status="ok",
                    simulated=False,
                    scenario=None,
                    scenario_event_id=None,
                )
            )
        except ValueError:
            continue
    if ordered:
        print(f"[ML] hydrated sensor={reading.sensor_id} samples={stream_buffer.count(reading.sensor_id)}")


def _predict_window(feature_vector: np.ndarray, features: dict[str, float]) -> dict:
    model = _load_active_model()
    prediction = model.predict(feature_vector)
    anomaly_type = _classify_streaming_anomaly(features, prediction["prediction"])
    if anomaly_type == "microfuga" and prediction["prediction"] == "normal":
        prediction = {
            **prediction,
            "prediction": "anomaly",
            "severity": "medium",
            "confidence": max(float(prediction["confidence"]), 0.72),
        }
    return {**prediction, "anomaly_type": anomaly_type}


def _confidence_percentage(value: float) -> float:
    if value <= 1.0:
        return round(max(0.0, min(1.0, value)) * 100.0, 2)
    return round(max(0.0, min(100.0, value)), 2)


def _severity_from_confidence(confidence_pct: float) -> str:
    if confidence_pct > 80:
        return "critical"
    if confidence_pct >= 60:
        return "medium"
    return "low"


def _confirmed_continuous_alert(sensor_id: str, anomaly_type: str, anomalous: bool) -> bool:
    key = (sensor_id, anomaly_type)
    required = max(1, int(np.ceil(CONFIRMATION_SECONDS / SAMPLE_SECONDS)))
    if not anomalous:
        _confirmation_state[key] = 0
        return False
    _confirmation_state[key] = _confirmation_state.get(key, 0) + 1
    return _confirmation_state[key] >= required


def _classify_streaming_anomaly(features: dict[str, float], prediction: str) -> str:
    if bool(microleak_rule(pd.DataFrame([features])).iloc[0]):
        return "microfuga"
    if prediction != "anomaly":
        return "normal"
    if features["horario_laboral"] == 0 and features["mu_q"] > 1.5 and features["min_q"] > 0.5:
        return "fuga_sostenida_nocturna"
    if features["min_q"] > 0.2 and features["sigma_q"] < 0.15:
        return "flujo_sostenido"
    if features["slope_q"] > 0.2:
        return "consumo_creciente"
    return "anomalia_no_clasificada"


def _persist_streaming_prediction(
    *,
    sensor_id: str,
    floor: str,
    features: dict[str, float],
    prediction: dict,
    processed_at,
    should_alert: bool,
    shadow_mode: bool,
) -> None:
    db = SessionLocal()
    try:
        model_status = ModelManager().get_status()
        model_label = "IsolationForest"
        if model_status.active_version:
            model_label = f"IsolationForest:{model_status.active_version[:16]}"
        analysis = MLAnalysis(
            alert_id=None,
            device_id=sensor_id,
            floor=floor or None,
            observed_value=float(features["mu_q"]),
            model_name=model_label,
            anomaly_score=float(prediction["score"]),
            prediction=str(prediction["prediction"]),
            confidence=float(prediction["confidence"]),
            processed_at=_naive_utc(processed_at),
        )
        db.add(analysis)
        db.flush()
        if should_alert and not shadow_mode:
            alert = _find_recent_streaming_alert(db, sensor_id, str(prediction["anomaly_type"]))
            if alert is None:
                alert = Alert(
                    device_id=sensor_id,
                    floor=floor or None,
                    anomaly_type=str(prediction["anomaly_type"]),
                    severity=str(prediction["severity"]),
                    risk_percentage=float(prediction["confidence"]),
                    status="pendiente",
                    description=(
                        "Origen: modelo ML streaming. "
                        f"Tipo: {prediction['anomaly_type']}. "
                        f"Ventana deslizante: 60 lecturas / 5 minutos. "
                        f"Caudal promedio: {float(features['mu_q']):.2f} L/min."
                    ),
                    detected_at=_naive_utc(processed_at),
                )
                db.add(alert)
                db.flush()
            analysis.alert_id = alert.id
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("No se pudo persistir inferencia streaming sensor=%s", sensor_id)
    finally:
        db.close()


def _find_recent_streaming_alert(db, sensor_id: str, anomaly_type: str) -> Alert | None:
    from datetime import datetime, timedelta

    cooldown_minutes = int(os.getenv("ML_ALERT_COOLDOWN_MINUTES", "15"))
    cutoff = datetime.utcnow() - timedelta(minutes=cooldown_minutes)
    return (
        db.query(Alert)
        .filter(
            Alert.device_id == sensor_id,
            Alert.anomaly_type == anomaly_type,
            Alert.status == "pendiente",
            Alert.detected_at >= cutoff,
        )
        .order_by(Alert.detected_at.desc())
        .first()
    )


def _naive_utc(value) -> object:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


if __name__ == "__main__":
    main()




