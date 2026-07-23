import json
import os
import random
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

SITE = os.getenv("SITE", "indatta")
INTERVAL_SEC = int(os.getenv("INTERVAL_SEC", "10"))

DEFAULT_DEVICES = [
    {"device_id": "floor1-python", "floor": "P1", "tenant": "python", "meter_role": "submeter"},
    {"device_id": "floor3-python", "floor": "P3", "tenant": "python", "meter_role": "submeter"},
]


def load_devices() -> list[dict]:
    raw = os.getenv("SIM_DEVICES_JSON", "").strip()
    if not raw:
        return DEFAULT_DEVICES
    try:
        devices = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"SIM_DEVICES_JSON invalido: {exc}") from exc
    if not isinstance(devices, list):
        raise SystemExit("SIM_DEVICES_JSON debe ser una lista de dispositivos.")
    return devices


DEVICES = load_devices()

state = {
    d["device_id"]: {
        "total_liters": 0.0,
        "flow_lpm": 7.5 if "floor1" in d["device_id"] else 10.5,
    }
    for d in DEVICES
}

def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def simulate_flow(device_id: str) -> float:
    base = 7.5 if "floor1" in device_id else 10.5
    current = state[device_id]["flow_lpm"]
    drift = (base - current) * 0.18
    noise = random.gauss(0, 0.18)
    pulse = random.uniform(0.35, 0.9) if random.random() < 0.04 else 0.0
    next_value = current + drift + noise + pulse
    low = max(0.3, base * 0.68)
    high = base * 1.32
    next_value = min(high, max(low, next_value))
    state[device_id]["flow_lpm"] = next_value
    return round(next_value, 2)

def topic_for(device_id: str) -> str:
    return f"water/flow/{SITE}/{device_id}/telemetry"

def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    print(f"[SIM] connecting {MQTT_HOST}:{MQTT_PORT} devices={len(DEVICES)}")
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_start()

    try:
        while True:
            for d in DEVICES:
                device_id = d["device_id"]
                flow_lpm = simulate_flow(device_id)

                # litros en este intervalo: (L/min) * (sec/60)
                delta_liters = flow_lpm * (INTERVAL_SEC / 60.0)
                state[device_id]["total_liters"] += delta_liters

                payload = {
                    "schema_version": 1,
                    "site": SITE,
                    "device_id": device_id,
                    "sensor_type": "flow",
                    "meter_role": d["meter_role"],
                    "floor": d["floor"],
                    "tenant": d["tenant"],
                    "flow_lpm": flow_lpm,
                    "total_liters": round(state[device_id]["total_liters"], 3),
                    "ts": now_iso(),
                }

                t = topic_for(device_id)
                client.publish(t, json.dumps(payload), qos=1, retain=False)
                print(f"PUB {t} -> {payload}")

            time.sleep(INTERVAL_SEC)
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
