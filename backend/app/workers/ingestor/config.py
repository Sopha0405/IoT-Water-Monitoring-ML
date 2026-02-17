import os
from dataclasses import dataclass

@dataclass(frozen=True)
class MqttConfig:
    host: str
    port: int
    topic_filter: str
    qos: int

@dataclass(frozen=True)
class InfluxConfig:
    url: str
    token: str
    org: str
    bucket: str
    measurement: str

@dataclass(frozen=True)
class BatchConfig:
    batch_size: int
    flush_interval_ms: int
    jitter_interval_ms: int
    retry_interval_ms: int
    queue_max: int

@dataclass(frozen=True)
class AppConfig:
    mqtt: MqttConfig
    influx: InfluxConfig
    batch: BatchConfig

def _get_int(name: str, default: int) -> int:
    v = os.getenv(name, str(default)).strip()
    try:
        return int(v)
    except ValueError:
        raise ValueError(f"ENV {name} debe ser int. Valor: {v!r}")

def load_config() -> AppConfig:
    mqtt = MqttConfig(
        host=os.getenv("MQTT_HOST", "mosquitto"),
        port=_get_int("MQTT_PORT", 1883),
        topic_filter=os.getenv("MQTT_TOPIC_FILTER", "water/flow/+/+/telemetry"),
        qos=_get_int("MQTT_QOS", 1),
    )

    influx = InfluxConfig(
        url=os.getenv("INFLUX_URL", "http://influxdb:8086"),
        token=os.getenv("INFLUX_TOKEN", ""),
        org=os.getenv("INFLUX_ORG", ""),
        bucket=os.getenv("INFLUX_BUCKET", "water-data"),
        measurement=os.getenv("INFLUX_MEASUREMENT", "water_telemetry"),
    )

    batch = BatchConfig(
        batch_size=_get_int("INFLUX_BATCH_SIZE", 500),
        flush_interval_ms=_get_int("INFLUX_FLUSH_INTERVAL_MS", 1000),
        jitter_interval_ms=_get_int("INFLUX_JITTER_INTERVAL_MS", 500),
        retry_interval_ms=_get_int("INFLUX_RETRY_INTERVAL_MS", 2000),
        queue_max=_get_int("INGEST_QUEUE_MAX", 20000),
    )

    return AppConfig(mqtt=mqtt, influx=influx, batch=batch)

def validate_config(cfg: AppConfig) -> None:
    if not cfg.influx.token:
        raise SystemExit("Falta INFLUX_TOKEN")
    if not cfg.influx.org:
        raise SystemExit("Falta INFLUX_ORG")
    if cfg.mqtt.qos not in (0, 1, 2):
        raise SystemExit("MQTT_QOS debe ser 0, 1 o 2")
