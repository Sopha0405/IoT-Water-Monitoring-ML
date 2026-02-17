import json
import os
import random
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

SITE = os.getenv("SITE", "indatta")
INTERVAL_SEC = int(os.getenv("INTERVAL_SEC", "60"))  # <- 60s

DEVICES = [
    {"device_id": "pb-esp32", "floor": "PB", "tenant": "sofia", "meter_role": "submeter"},
    {"device_id": "floor3-esp32", "floor": "3", "tenant": "indatta", "meter_role": "submeter"},
]

state = {d["device_id"]: {"total_liters": 0.0} for d in DEVICES}

def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def simulate_flow(device_id: str) -> float:
    base = 6.0 if device_id.startswith("pb") else 10.0
    return max(0.0, round(random.gauss(base, 1.0), 3))

def topic_for(device_id: str) -> str:
    return f"water/flow/{SITE}/{device_id}/telemetry"

def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
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