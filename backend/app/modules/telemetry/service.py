from datetime import datetime, timedelta
import math
import random

from influxdb_client import InfluxDBClient

from app.core.config import settings
from app.modules.telemetry.schemas import TelemetryPoint


def flux_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def floor_filter_values(value: str) -> list[str]:
    normalized = value.strip()
    aliases = {
        "PB": ["PB"],
        "Piso 1": ["P1", "1", "Piso 1"],
        "Piso 2": ["P2", "2", "Piso 2"],
        "Piso 3": ["P3", "3", "Piso 3"],
    }
    return aliases.get(normalized, [normalized])


def flux_string_list(values: list[str]) -> str:
    return "[" + ", ".join(f'"{flux_string(value)}"' for value in values) + "]"


def query_flux(flux: str) -> list[TelemetryPoint]:
    if not settings.influx_token:
        return []

    try:
        with InfluxDBClient(
            url=settings.influx_url,
            token=settings.influx_token,
            org=settings.influx_org,
        ) as client:
            tables = client.query_api().query(flux, org=settings.influx_org)
    except Exception:
        return []

    points: list[TelemetryPoint] = []
    for table in tables:
        for record in table.records:
            values = record.values
            points.append(
                TelemetryPoint(
                    time=record.get_time(),
                    device_id=values.get("device_id"),
                    site=values.get("site"),
                    floor=values.get("floor"),
                    tenant=values.get("tenant"),
                    field=record.get_field(),
                    value=float(record.get_value()),
                )
            )
    return points


def demo_telemetry(
    device_id: str | None = None,
    floor: str | None = None,
    field: str | None = "flow_lpm",
    limit: int = 120,
) -> list[TelemetryPoint]:
    devices = [
        ("pb-wokwi", "PB", 6.8),
        ("floor1-python", "P1", 7.5),
        ("floor3-python", "P3", 10.5),
    ]
    if device_id:
        devices = [item for item in devices if item[0] == device_id]
    if floor:
        floor_values = set(floor_filter_values(floor))
        devices = [item for item in devices if item[1] in floor_values]

    now = datetime.utcnow().replace(microsecond=0)
    per_device = max(12, min(80, limit // max(1, len(devices))))
    points: list[TelemetryPoint] = []
    rng = random.Random(42)
    for device_index, (demo_device_id, floor, base) in enumerate(devices):
        value = base
        for index in range(per_device):
            daily_wave = math.sin(index / 9 + device_index * 0.7) * (base * 0.05)
            drift = (base + daily_wave - value) * 0.22
            noise = rng.uniform(-0.18, 0.18)
            pulse = rng.uniform(0.35, 0.8) if rng.random() < 0.04 else 0
            value = value + drift + noise + pulse
            value = min(base * 1.3, max(base * 0.7, value))
            points.append(
                TelemetryPoint(
                    time=now - timedelta(seconds=(per_device - index) * 15),
                    device_id=demo_device_id,
                    site="Edificio Corporativo Sofia",
                    floor=floor,
                    tenant="wokwi" if demo_device_id == "pb-wokwi" else "python",
                    field=field or "flow_lpm",
                    value=max(0, round(value, 3)),
                )
            )
    points.sort(key=lambda item: item.time or now, reverse=True)
    return points[:limit]


def get_latest_telemetry(
    device_id: str | None = None,
    site: str | None = None,
    floor: str | None = None,
    field: str | None = None,
    limit: int = 50,
) -> list[TelemetryPoint]:
    filters = [
        f'r["_measurement"] == "{flux_string(settings.influx_measurement)}"',
    ]
    if device_id:
        filters.append(f'r["device_id"] == "{flux_string(device_id)}"')
    if site:
        filters.append(f'r["site"] == "{flux_string(site)}"')
    if floor:
        filters.append(f'contains(value: r["floor"], set: {flux_string_list(floor_filter_values(floor))})')
    if field:
        filters.append(f'r["_field"] == "{flux_string(field)}"')

    flux = f'''
from(bucket: "{flux_string(settings.influx_bucket)}")
  |> range(start: -24h)
  |> filter(fn: (r) => {' and '.join(filters)})
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: {limit})
'''
    points = query_flux(flux)
    return points or demo_telemetry(device_id=device_id, floor=floor, field=field, limit=limit)


def get_telemetry_series(
    device_id: str,
    field: str = "flow_lpm",
    hours: int = 24,
    limit: int = 500,
) -> list[TelemetryPoint]:
    flux = f'''
from(bucket: "{flux_string(settings.influx_bucket)}")
  |> range(start: -{hours}h)
  |> filter(fn: (r) => r["_measurement"] == "{flux_string(settings.influx_measurement)}" and r["device_id"] == "{flux_string(device_id)}" and r["_field"] == "{flux_string(field)}")
  |> sort(columns: ["_time"], desc: false)
  |> limit(n: {limit})
'''
    points = query_flux(flux)
    demo_points = demo_telemetry(device_id=device_id, field=field, limit=limit)
    return points or list(reversed(demo_points))
