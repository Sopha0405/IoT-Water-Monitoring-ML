from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np

from app.modules.ml_analysis.streaming.types import FlowReading

WINDOW_SIZE = 60
HISTORY_SIZE = 360
DEFAULT_TIMEZONE = "America/La_Paz"


@dataclass(frozen=True)
class ClosedWindow:
    sensor_id: str
    window_start: datetime
    window_end: datetime
    readings: list[FlowReading]
    history: list[FlowReading]
    window_id: str


class WindowManager:
    def __init__(self, timezone_name: str = DEFAULT_TIMEZONE) -> None:
        self.timezone = ZoneInfo(timezone_name)
        self._last_window: dict[str, str] = {}

    def close_if_ready(self, sensor_id: str, history: list[FlowReading]) -> ClosedWindow | None:
        if len(history) < WINDOW_SIZE:
            return None
        latest = history[-1]
        current_window = history[-WINDOW_SIZE:]
        if any(item.sensor_id != sensor_id for item in current_window):
            raise ValueError("La ventana cruza sensores")
        if current_window[0].timestamp.astimezone(self.timezone).date() != latest.timestamp.astimezone(self.timezone).date():
            raise ValueError("La ventana cruza el dia local")
        _validate_regular(current_window)

        local_end = latest.timestamp.astimezone(self.timezone)
        if local_end.second % 5 != 0:
            return None
        block_minute = (local_end.minute // 5) * 5
        block_start = local_end.replace(minute=block_minute, second=0, microsecond=0)
        block_end = block_start + timedelta(minutes=4, seconds=55)
        if local_end != block_end:
            return None

        values = np.asarray([item.flow_lpm for item in current_window], dtype=float)
        if not np.all(np.isfinite(values)):
            raise ValueError("La ventana contiene NaN o infinito")
        window_id = f"{sensor_id}:{block_start.isoformat()}"
        if self._last_window.get(sensor_id) == window_id:
            return None
        self._last_window[sensor_id] = window_id
        hist = history[-HISTORY_SIZE:]
        return ClosedWindow(sensor_id, current_window[0].timestamp, current_window[-1].timestamp, current_window, hist, window_id)


def _validate_regular(readings: list[FlowReading]) -> None:
    for previous, current in zip(readings, readings[1:]):
        delta = (current.timestamp - previous.timestamp).total_seconds()
        if abs(delta - current.sample_seconds) > 1:
            raise ValueError("Intervalo irregular en ventana")




