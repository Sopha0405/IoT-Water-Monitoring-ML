from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.db.postgres import SessionLocal
from app.modules.ml_analysis.router import compute_daily_drift

from .config import load_config, validate_config
from .influx_writer import InfluxWriter
from .mqtt_consumer import MqttConsumer

logger = logging.getLogger(__name__)


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

    def handle_payload(topic: str, payload: dict):
        ok = writer.enqueue(topic, payload)
        if ok:
            print(f"[OK] {topic} -> queue")
        else:
            print(f"[DROP] queue full topic={topic}")

    consumer = MqttConsumer(cfg.mqtt, handle_payload)

    try:
        print(f"[BOOT] Influx {cfg.influx.url} bucket={cfg.influx.bucket} org={cfg.influx.org}")
        print(f"[BOOT] MQTT {cfg.mqtt.host}:{cfg.mqtt.port} filter={cfg.mqtt.topic_filter}")
        consumer.start_forever()
    finally:
        scheduler.shutdown(wait=False)
        writer.stop()

if __name__ == "__main__":
    main()
