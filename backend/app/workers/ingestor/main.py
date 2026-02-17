from __future__ import annotations

from .config import load_config, validate_config
from .influx_writer import InfluxWriter
from .mqtt_consumer import MqttConsumer

def main():
    cfg = load_config()
    validate_config(cfg)

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
        writer.stop()

if __name__ == "__main__":
    main()