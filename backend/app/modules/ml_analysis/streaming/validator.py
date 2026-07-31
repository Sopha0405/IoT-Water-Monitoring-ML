from __future__ import annotations

import math
import os
from dataclasses import dataclass

from app.modules.ml_analysis.streaming.buffer import SensorStreamBuffer
from app.modules.ml_analysis.streaming.types import FlowReading

EXPECTED_SECONDS = 5
TOLERANCE_SECONDS = 1
VALID_STATUS = {"ok", "sensor_error", "maintenance", "offline"}


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    error_type: str | None = None
    message: str | None = None


class StreamValidator:
    def __init__(self, known_sensors: set[str] | None = None) -> None:
        raw = os.getenv("STREAM_KNOWN_SENSORS", "").strip()
        self.known_sensors = known_sensors or {item.strip() for item in raw.split(",") if item.strip()}

    def validate(self, reading: FlowReading, buffer: SensorStreamBuffer) -> ValidationResult:
        if self.known_sensors and reading.sensor_id not in self.known_sensors:
            return ValidationResult(False, "sensor_error", "sensor desconocido")
        if reading.status not in VALID_STATUS:
            return ValidationResult(False, "sensor_error", "status invalido")
        if reading.status != "ok":
            return ValidationResult(False, "sensor_error", reading.status)
        if not math.isfinite(reading.flow_lpm):
            return ValidationResult(False, "invalid_numeric", "flow_lpm no finito")
        if reading.flow_lpm < 0:
            return ValidationResult(False, "negative_flow", "flow_lpm negativo")
        if abs(reading.sample_seconds - EXPECTED_SECONDS) > TOLERANCE_SECONDS:
            return ValidationResult(False, "irregular_interval", "sample_seconds irregular")

        previous = buffer.last(reading.sensor_id)
        if previous is None:
            if reading.sequence_number is None:
                return ValidationResult(False, "missing_sequence", "sequence_number faltante")
            return ValidationResult(True)

        if reading.timestamp == previous.timestamp:
            return ValidationResult(False, "duplicate", "timestamp duplicado")
        if reading.timestamp < previous.timestamp:
            return ValidationResult(False, "out_of_order", "timestamp fuera de orden")
        if reading.sequence_number is None:
            return ValidationResult(False, "missing_sequence", "sequence_number faltante")
        if (
            previous.sequence_number is not None
            and reading.sequence_number <= previous.sequence_number
            and reading.timestamp > previous.timestamp
        ):
            return ValidationResult(True)
        if previous.sequence_number is not None and reading.sequence_number != previous.sequence_number + 1:
            return ValidationResult(False, "missing_sequence", "secuencia no consecutiva")

        delta = (reading.timestamp - previous.timestamp).total_seconds()
        if abs(delta - EXPECTED_SECONDS) > TOLERANCE_SECONDS:
            return ValidationResult(False, "irregular_interval", "intervalo temporal irregular")
        return ValidationResult(True)




