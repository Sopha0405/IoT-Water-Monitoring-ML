from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class FlowReading:
    timestamp: datetime
    sensor_id: str
    flow_lpm: float
    sequence_number: int | None
    sample_seconds: int
    status: str
    simulated: bool
    scenario: str | None
    scenario_event_id: str | None


def parse_flow_payload(payload: dict[str, Any]) -> FlowReading:
    required = ["device_id", "flow_lpm", "sample_seconds", "status", "simulated", "ts"]
    missing = [field for field in required if field not in payload]
    if missing:
        raise ValueError(f"Faltan campos obligatorios: {', '.join(missing)}")

    sensor_id = str(payload["device_id"]).strip()
    if not sensor_id:
        raise ValueError("device_id no puede estar vacio")

    timestamp = _parse_timestamp(payload["ts"])
    sequence_number = payload.get("sequence_number")
    if sequence_number is not None:
        if isinstance(sequence_number, bool):
            raise ValueError("sequence_number debe ser entero")
        sequence_number = int(sequence_number)
        if sequence_number < 0:
            raise ValueError("sequence_number no puede ser negativo")

    try:
        flow_lpm = float(payload["flow_lpm"])
    except (TypeError, ValueError):
        if str(payload.get("status", "")).strip() != "ok":
            flow_lpm = float("nan")
        else:
            raise ValueError("flow_lpm debe ser numerico")
    sample_seconds = int(payload["sample_seconds"])
    if sample_seconds <= 0:
        raise ValueError("sample_seconds debe ser positivo")

    status = str(payload["status"]).strip()
    if not status:
        raise ValueError("status no puede estar vacio")

    simulated = payload["simulated"]
    if not isinstance(simulated, bool):
        raise ValueError("simulated debe ser booleano")

    scenario = payload.get("scenario")
    scenario_event_id = payload.get("scenario_event_id")
    return FlowReading(
        timestamp=timestamp,
        sensor_id=sensor_id,
        flow_lpm=flow_lpm,
        sequence_number=sequence_number,
        sample_seconds=sample_seconds,
        status=status,
        simulated=simulated,
        scenario=str(scenario) if scenario is not None else None,
        scenario_event_id=str(scenario_event_id) if scenario_event_id is not None else None,
    )


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("ts debe ser texto ISO-8601")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("ts debe tener formato ISO-8601") from exc
    if timestamp.tzinfo is None:
        raise ValueError("ts debe incluir zona horaria")
    if not math.isfinite(timestamp.timestamp()):
        raise ValueError("ts invalido")
    return timestamp




