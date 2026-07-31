from __future__ import annotations

import importlib
import os
from datetime import datetime, timedelta, timezone

import numpy as np

from app.modules.ml_analysis.alerts.policy import AlertPolicy
from app.modules.ml_analysis.features.constants import FEATURE_NAMES
from app.modules.ml_analysis.features.extractor import extract_features
from app.modules.ml_analysis.streaming.buffer import SensorStreamBuffer
from app.modules.ml_analysis.streaming.types import FlowReading
from app.modules.ml_analysis.streaming.validator import StreamValidator
from app.modules.ml_analysis.streaming.temporal_state import TemporalStateStore
from app.modules.ml_analysis.streaming.window_manager import WindowManager


def reading(index: int, flow: float = 0.0, sensor_id: str = "PM-04", start: datetime | None = None) -> FlowReading:
    start = start or datetime(2026, 7, 25, 16, 0, 0, tzinfo=timezone.utc)
    return FlowReading(start + timedelta(seconds=5 * index), sensor_id, flow, index + 1, 5, "ok", True, "normal", None)


def test_buffer_keeps_max_360_readings() -> None:
    buffer = SensorStreamBuffer()
    for index in range(400):
        buffer.append(reading(index))
    assert buffer.count("PM-04") == 360


def test_buffer_rejects_duplicate_timestamp() -> None:
    buffer = SensorStreamBuffer()
    item = reading(0)
    buffer.append(item)
    duplicate = FlowReading(item.timestamp, item.sensor_id, 1.0, 2, 5, "ok", True, "normal", None)
    try:
        buffer.append(duplicate)
    except ValueError as exc:
        assert "duplicate" in str(exc)
    else:
        raise AssertionError("duplicate timestamp accepted")


def test_validator_detects_missing_sequence_and_irregular_interval() -> None:
    buffer = SensorStreamBuffer()
    validator = StreamValidator()
    first = reading(0)
    buffer.append(first)
    assert validator.validate(reading(2), buffer).error_type == "missing_sequence"
    irregular = FlowReading(first.timestamp + timedelta(seconds=9), "PM-04", 0.0, 2, 5, "ok", True, "normal", None)
    assert validator.validate(irregular, buffer).error_type == "irregular_interval"


def test_window_has_exactly_60_and_does_not_cross_day() -> None:
    manager = WindowManager()
    start = datetime(2026, 7, 25, 16, 0, 0, tzinfo=timezone.utc)
    history = [reading(index, start=start) for index in range(60)]
    closed = manager.close_if_ready("PM-04", history)
    assert closed is not None
    assert len(closed.readings) == 60

    crossing = [reading(index, start=datetime(2026, 7, 26, 3, 57, 0, tzinfo=timezone.utc)) for index in range(60)]
    try:
        manager.close_if_ready("PM-04", crossing)
    except ValueError as exc:
        assert "dia" in str(exc)
    else:
        raise AssertionError("cross-day window accepted")


def test_features_have_24_ordered_values_and_no_future_mean() -> None:
    history = [reading(index, flow=1.0 if index < 359 else 10.0) for index in range(360)]
    features = extract_features(history[-60:], history, {}, {})
    assert len(features) == 24
    assert list(features) == FEATURE_NAMES
    np.testing.assert_allclose(features["caudal_promedio_30min"], (359.0 + 10.0) / 360.0, rtol=1e-6, atol=1e-8)


def test_microflow_30_minutes_produces_six_consecutive_windows() -> None:
    state = TemporalStateStore()
    for _ in range(6):
        state.update_microflow("PM-04", 1.0)
    assert state.for_sensor("PM-04").consecutive_microflow_windows == 6


def test_alert_policy_rules_and_deduplication() -> None:
    policy = AlertPolicy(critical_peak_lpm=8.0, cooldown_minutes=15)
    store = TemporalStateStore()
    now = datetime.now(timezone.utc)
    state = store.for_sensor("PM-04")
    assert policy.evaluate("PM-04", now, 9.0, 9.0, 0.9, "normal", state).should_alert

    store.reset_sensor("PM-05")
    state = store.update_prediction("PM-05", "anomaly", 0.7, "w1")
    assert not policy.evaluate("PM-05", now, 1.0, 1.0, 0.7, "anomaly", state).should_alert
    state = store.update_prediction("PM-05", "normal", 0.1, "w2")
    state = store.update_prediction("PM-05", "anomaly", 0.8, "w3")
    assert policy.evaluate("PM-05", now, 1.0, 1.0, 0.8, "anomaly", state).should_alert
    assert not policy.evaluate("PM-05", now, 1.0, 1.0, 0.8, "anomaly", state).should_alert


def test_three_normal_windows_close_alert_and_later_event_reopens() -> None:
    policy = AlertPolicy(critical_peak_lpm=8.0, cooldown_minutes=0)
    store = TemporalStateStore()
    now = datetime.now(timezone.utc)
    state = store.for_sensor("PM-10")
    assert policy.evaluate("PM-10", now, 9.0, 9.0, 0.9, "normal", state).should_alert
    for offset in range(1, 4):
        policy.evaluate("PM-10", now + timedelta(minutes=5 * offset), 0.0, 0.0, 0.1, "normal", state)
    assert "critical_peak" not in state.open_alert_by_type
    assert policy.evaluate("PM-10", now + timedelta(minutes=25), 9.0, 9.0, 0.9, "normal", state).should_alert


def test_different_sensors_keep_alert_state_separate() -> None:
    policy = AlertPolicy(critical_peak_lpm=8.0, cooldown_minutes=15)
    store = TemporalStateStore()
    now = datetime.now(timezone.utc)
    assert policy.evaluate("PM-11", now, 9.0, 9.0, 0.9, "normal", store.for_sensor("PM-11")).should_alert
    assert policy.evaluate("PM-12", now, 9.0, 9.0, 0.9, "normal", store.for_sensor("PM-12")).should_alert


def test_sensor_error_does_not_generate_leak_alert() -> None:
    validator = StreamValidator()
    buffer = SensorStreamBuffer()
    item = FlowReading(datetime.now(timezone.utc), "PM-04", float("nan"), 1, 5, "sensor_error", True, "sensor_error", "e1")
    assert validator.validate(item, buffer).error_type == "sensor_error"


def test_simulator_seed_and_liters_math() -> None:
    os.environ["SIM_RANDOM_SEED"] = "42"
    os.environ["SIM_SCENARIO"] = "normal"
    sim = importlib.import_module("app.workers.sim_flow_sensors")
    sim = importlib.reload(sim)
    now = datetime(2026, 7, 25, 16, 0, 0, tzinfo=timezone.utc)
    first = sim.simulate_flow("floor1-python", now)[0]
    sim = importlib.reload(sim)
    second = sim.simulate_flow("floor1-python", now)[0]
    assert first == second
    assert sim.INTERVAL_SEC == 5
    assert np.isclose(12.0 * (sim.INTERVAL_SEC / 60.0), 1.0)


def test_offline_and_streaming_features_match() -> None:
    history = [reading(index, flow=float(index % 5) / 10.0) for index in range(360)]
    streaming = extract_features(history[-60:], history, {}, {})
    offline = extract_features(list(history[-60:]), list(history), {}, {})
    np.testing.assert_allclose(list(streaming.values()), list(offline.values()), rtol=1e-6, atol=1e-8)




