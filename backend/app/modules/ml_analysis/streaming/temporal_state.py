from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SensorTemporalState:
    predictions: deque[str] = field(default_factory=lambda: deque(maxlen=3))
    windows: deque[str] = field(default_factory=lambda: deque(maxlen=6))
    consecutive_microflow_windows: int = 0
    last_score: float | None = None
    last_window_id: str | None = None
    open_alert_by_type: dict[str, str] = field(default_factory=dict)
    last_alert_at: dict[str, datetime] = field(default_factory=dict)
    normal_windows_by_type: dict[str, int] = field(default_factory=dict)
    persistent_deviation_windows: int = 0
    low_variability_windows: int = 0


class TemporalStateStore:
    def __init__(self) -> None:
        self._state: dict[str, SensorTemporalState] = {}

    def for_sensor(self, sensor_id: str) -> SensorTemporalState:
        return self._state.setdefault(sensor_id, SensorTemporalState())

    def update_prediction(self, sensor_id: str, prediction: str, score: float, window_id: str) -> SensorTemporalState:
        state = self.for_sensor(sensor_id)
        if state.last_window_id and window_id <= state.last_window_id:
            return state
        state.predictions.append(prediction)
        state.windows.append(window_id)
        state.last_score = score
        state.last_window_id = window_id
        return state

    def update_microflow(self, sensor_id: str, pct_microflow_5min: float) -> SensorTemporalState:
        state = self.for_sensor(sensor_id)
        if pct_microflow_5min >= 0.90:
            state.consecutive_microflow_windows += 1
        else:
            state.consecutive_microflow_windows = 0
        return state

    def update_microleak_context(self, sensor_id: str, pct_microflow_5min: float, deviation_vs_pattern: float, sigma_q: float) -> SensorTemporalState:
        state = self.update_microflow(sensor_id, pct_microflow_5min)
        if deviation_vs_pattern > 0.15:
            state.persistent_deviation_windows += 1
        else:
            state.persistent_deviation_windows = 0
        if sigma_q < 0.20:
            state.low_variability_windows += 1
        else:
            state.low_variability_windows = 0
        return state

    def reset_sensor(self, sensor_id: str) -> None:
        self._state.pop(sensor_id, None)




