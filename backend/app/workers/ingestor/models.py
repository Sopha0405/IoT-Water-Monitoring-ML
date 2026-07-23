from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Tuple

from influxdb_client import Point, WritePrecision


def parse_ts(ts: str) -> datetime:
    if ts.endswith("Z"):
        ts = ts.replace("Z", "+00:00")
    return datetime.fromisoformat(ts)


def extract_from_topic(topic: str) -> Tuple[str | None, str | None]:
    parts = topic.split("/")
    if len(parts) >= 5:
        return parts[2], parts[3]
    return None, None


FIELD_LIMITS = {
    "flow_lpm": (0.0, 60.0),
    "total_liters": (0.0, 1_000_000.0),
    "battery_v": (0.0, 5.5),
    "rssi": (-130.0, 0.0),
}


def clean_float(field: str, value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    low, high = FIELD_LIMITS[field]
    return round(min(high, max(low, number)), 3)


@dataclass(frozen=True)
class Telemetry:
    schema_version: int
    site: str
    device_id: str
    sensor_type: str
    meter_role: str
    floor: str
    tenant: str
    ts: datetime
    fields: Dict[str, float]

    @staticmethod
    def from_message(topic: str, payload: Dict[str, Any]) -> "Telemetry":
        site_t, device_t = extract_from_topic(topic)

        schema_version = int(payload.get("schema_version", 1))
        if schema_version != 1:
            raise ValueError(f"schema_version no soportado: {schema_version}")

        site = str(payload.get("site") or site_t or "unknown")
        device_id = str(payload.get("device_id") or device_t or "unknown")
        sensor_type = str(payload.get("sensor_type", "flow"))

        meter_role = str(payload.get("meter_role", "submeter"))
        floor = str(payload.get("floor", "unknown"))
        tenant = str(payload.get("tenant", "unknown"))

        if "ts" not in payload:
            raise ValueError("Falta campo ts en payload")
        ts = parse_ts(str(payload["ts"]))

        fields: Dict[str, float] = {}
        for k in FIELD_LIMITS:
            cleaned = clean_float(k, payload.get(k))
            if cleaned is not None:
                fields[k] = cleaned

        return Telemetry(
            schema_version=schema_version,
            site=site,
            device_id=device_id,
            sensor_type=sensor_type,
            meter_role=meter_role,
            floor=floor,
            tenant=tenant,
            ts=ts,
            fields=fields,
        )

    def to_point(self, measurement: str) -> Point:
        p = (
            Point(measurement)
            .tag("site", self.site)
            .tag("device_id", self.device_id)
            .tag("sensor_type", self.sensor_type)
            .tag("floor", self.floor)
            .tag("tenant", self.tenant)
            .tag("meter_role", self.meter_role)
            .time(self.ts, WritePrecision.NS)
        )
        for k, v in self.fields.items():
            p.field(k, v)
        return p
