from __future__ import annotations

import threading
from collections import defaultdict, deque
from dataclasses import dataclass

from app.modules.ml_analysis.streaming.types import FlowReading


@dataclass(frozen=True)
class SensorStreamBuffer:
    """
    Buffer por sensor seguro para concurrencia en un solo proceso.

    Si el ingestor corre con varios workers o replicas, este estado debe migrarse
    a Redis para preservar orden y unicidad entre procesos.
    """

    maxlen: int = 360

    def __post_init__(self) -> None:
        object.__setattr__(self, "_data", defaultdict(lambda: deque(maxlen=self.maxlen)))
        object.__setattr__(self, "_lock", threading.RLock())

    def append(self, reading: FlowReading) -> None:
        with self._lock:
            readings = self._data[reading.sensor_id]
            if readings:
                previous = readings[-1]
                if reading.timestamp == previous.timestamp:
                    raise ValueError("duplicate timestamp")
                if reading.timestamp < previous.timestamp:
                    raise ValueError("out_of_order timestamp")
                if (
                    reading.sequence_number is not None
                    and previous.sequence_number is not None
                    and reading.sequence_number <= previous.sequence_number
                    and reading.timestamp <= previous.timestamp
                ):
                    raise ValueError("duplicate sequence")
            readings.append(reading)

    def latest(self, sensor_id: str, count: int) -> list[FlowReading]:
        with self._lock:
            readings = list(self._data.get(sensor_id, ()))
            return readings[-count:]

    def count(self, sensor_id: str) -> int:
        with self._lock:
            return len(self._data.get(sensor_id, ()))

    def clear(self, sensor_id: str) -> None:
        with self._lock:
            self._data.pop(sensor_id, None)

    def last(self, sensor_id: str) -> FlowReading | None:
        with self._lock:
            readings = self._data.get(sensor_id)
            return readings[-1] if readings else None




