import json
import logging
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

SITE = os.getenv("SITE", "indatta")
INTERVAL_SEC = int(os.getenv("INTERVAL_SEC", "5"))
SIM_SCENARIO = os.getenv("SIM_SCENARIO", "normal").strip().lower()
SIM_RANDOM_SEED = os.getenv("SIM_RANDOM_SEED")
SIM_NOISE_LPM = float(os.getenv("SIM_NOISE_LPM", "0.015"))
LOCAL_TZ = ZoneInfo(os.getenv("TZ", "America/La_Paz"))
VALID_SCENARIOS = {
    "normal",
    "microleak",
    "sustained_leak",
    "peak",
    "growing_consumption",
    "sensor_error",
    "mixed",
}

logger = logging.getLogger(__name__)
if SIM_RANDOM_SEED is not None:
    random.seed(int(SIM_RANDOM_SEED))

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

@dataclass
class ScenarioEvent:
    name: str
    event_id: str
    start: datetime
    end: datetime
    intensity_lpm: float
    growth_lpm: float = 0.0


state = {
    d["device_id"]: {
        "total_liters": 0.0,
        "sequence_number": 0,
        "event": None,
    }
    for d in DEVICES
}

def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def _normal_flow(local_now: datetime) -> float:
    weekday = local_now.weekday()
    hour = local_now.hour
    p = 0.015
    if weekday < 5 and 7 <= hour < 18:
        p = 0.08
    if weekday < 5 and 12 <= hour < 14:
        p = 0.16
    if weekday >= 5:
        p *= 0.35
    if 0 <= hour < 6:
        p = 0.008

    if random.random() > p:
        return max(0.0, random.gauss(0.0, SIM_NOISE_LPM))
    if hour < 7 or hour >= 18:
        return random.uniform(0.25, 2.0)
    return random.uniform(0.4, 6.0)


def _new_event(device_id: str, now: datetime, scenario: str) -> ScenarioEvent | None:
    scenario = random.choice(["normal", "microleak", "sustained_leak", "peak", "growing_consumption"]) if scenario == "mixed" else scenario
    event_id = f"{device_id}-{int(now.timestamp())}-{scenario}"
    if scenario == "microleak":
        return ScenarioEvent(scenario, event_id, now, now + timedelta(minutes=random.randint(20, 90)), random.uniform(0.08, 0.50))
    if scenario == "sustained_leak":
        return ScenarioEvent(scenario, event_id, now, now + timedelta(minutes=random.randint(10, 60)), random.uniform(0.50, 4.00))
    if scenario == "peak":
        return ScenarioEvent(scenario, event_id, now, now + timedelta(seconds=random.randint(5, 40)), random.uniform(8.0, 20.0))
    if scenario == "growing_consumption":
        duration = random.randint(15, 60)
        return ScenarioEvent(scenario, event_id, now, now + timedelta(minutes=duration), random.uniform(0.15, 0.5), random.uniform(1.5, 5.0))
    return None


def simulate_flow(device_id: str, now: datetime) -> tuple[float | None, str, str, str | None]:
    local_now = now.astimezone(LOCAL_TZ)
    if SIM_SCENARIO not in VALID_SCENARIOS:
        raise ValueError(f"SIM_SCENARIO invalido: {SIM_SCENARIO}")
    if SIM_SCENARIO == "sensor_error":
        return None, "sensor_error", "sensor_error", f"{device_id}-sensor-error"

    flow = _normal_flow(local_now)
    scenario = "normal"
    event: ScenarioEvent | None = state[device_id].get("event")
    if event is not None and now >= event.end:
        state[device_id]["event"] = None
        event = None
    if event is None and SIM_SCENARIO != "normal":
        start_probability = 1.0 if state[device_id]["sequence_number"] == 0 else 0.01
        if random.random() < start_probability:
            event = _new_event(device_id, now, SIM_SCENARIO)
            state[device_id]["event"] = event

    event_id = None
    if event is not None:
        scenario = event.name
        event_id = event.event_id
        elapsed = max((now - event.start).total_seconds(), 0.0)
        total = max((event.end - event.start).total_seconds(), 1.0)
        if event.name == "growing_consumption":
            flow += event.intensity_lpm + event.growth_lpm * (elapsed / total)
        else:
            flow += event.intensity_lpm

    return round(max(flow, 0.0), 3), "ok", scenario, event_id

def topic_for(device_id: str) -> str:
    return f"water/flow/{SITE}/{device_id}/telemetry"

def main():
    import paho.mqtt.client as mqtt

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    print(f"[SIM] connecting {MQTT_HOST}:{MQTT_PORT} devices={len(DEVICES)}")
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_start()

    try:
        while True:
            for d in DEVICES:
                device_id = d["device_id"]
                now = datetime.now(timezone.utc)
                flow_lpm, status, scenario, event_id = simulate_flow(device_id, now)
                state[device_id]["sequence_number"] += 1

                # litros en este intervalo: (L/min) * (sec/60)
                delta_liters = (flow_lpm or 0.0) * (INTERVAL_SEC / 60.0)
                state[device_id]["total_liters"] += delta_liters

                payload = {
                    "schema_version": 2,
                    "site": SITE,
                    "device_id": device_id,
                    "sensor_type": "flow",
                    "meter_role": d["meter_role"],
                    "floor": d["floor"],
                    "tenant": d["tenant"],
                    "flow_lpm": flow_lpm,
                    "total_liters": round(state[device_id]["total_liters"], 3),
                    "sequence_number": state[device_id]["sequence_number"],
                    "sample_seconds": INTERVAL_SEC,
                    "status": status,
                    "simulated": True,
                    "scenario": scenario,
                    "scenario_event_id": event_id,
                    "ts": now.isoformat().replace("+00:00", "Z"),
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




