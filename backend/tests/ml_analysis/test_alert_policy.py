from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from app.modules.ml_analysis.alerts.policy import group_operational_incidents, incident_metrics


def _frame(rows):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    out = []
    for index, row in enumerate(rows):
        item = {
            "sensor_id": "S1",
            "window_end": base + timedelta(minutes=5 * index),
            "predicted_anomaly": row.get("predicted", False),
            "actual_label": row.get("actual_label", 0),
            "actual_type": row.get("actual_type", "normal"),
            "event_id": row.get("event_id"),
            "anomaly_score": row.get("anomaly_score", 0.1 if row.get("predicted", False) else 0.0),
            "mu_q": row.get("mu_q", 1.0),
            "pct_microflujo_5min": row.get("pct_microflujo_5min", 0.0),
            "duracion_microflujo_continuo_seg": row.get("duracion_microflujo_continuo_seg", 0.0),
            "rule_predicted_microleak": row.get("rule_predicted_microleak", False),
        }
        out.append(item)
    return pd.DataFrame(out)


def test_general_anomaly_single_window_is_not_confirmed():
    incidents = group_operational_incidents(_frame([{"predicted": True}, {}, {}]))
    assert incidents == []


def test_general_anomaly_two_of_three_is_not_operational_incident():
    incidents = group_operational_incidents(_frame([{"predicted": True}, {}, {"predicted": True}]))
    assert incidents == []


def test_sustained_leak_two_consecutive_is_confirmed():
    frame = _frame([
        {"predicted": True, "actual_type": "fuga_sostenida", "actual_label": 1, "event_id": "f1"},
        {"predicted": True, "actual_type": "fuga_sostenida", "actual_label": 1, "event_id": "f1"},
    ])
    incidents = group_operational_incidents(frame)
    assert len(incidents) == 1
    assert incidents[0]["alert_type"] == "fuga_sostenida"


def test_single_normal_gap_does_not_fragment_incident():
    frame = _frame([
        {"predicted": True, "actual_type": "fuga_sostenida", "actual_label": 1, "event_id": "f1"},
        {"predicted": True, "actual_type": "fuga_sostenida", "actual_label": 1, "event_id": "f1"},
        {"actual_type": "fuga_sostenida", "actual_label": 1, "event_id": "f1"},
        {"predicted": True, "actual_type": "fuga_sostenida", "actual_label": 1, "event_id": "f1"},
        {"predicted": True, "actual_type": "fuga_sostenida", "actual_label": 1, "event_id": "f1"},
    ])
    incidents = group_operational_incidents(frame)
    assert len(incidents) == 1


def test_same_event_fragmentation_counts_duplicates_not_extra_true_positives():
    frame = _frame([
        {"predicted": True, "actual_type": "fuga_sostenida", "actual_label": 1, "event_id": "f1"},
        {"predicted": True, "actual_type": "fuga_sostenida", "actual_label": 1, "event_id": "f1"},
        {"window_gap": True},
        {"predicted": True, "actual_type": "fuga_sostenida", "actual_label": 1, "event_id": "f1"},
        {"predicted": True, "actual_type": "fuga_sostenida", "actual_label": 1, "event_id": "f1"},
        {"window_gap": True},
        {"predicted": True, "actual_type": "fuga_sostenida", "actual_label": 1, "event_id": "f1"},
        {"predicted": True, "actual_type": "fuga_sostenida", "actual_label": 1, "event_id": "f1"},
    ])
    frame.loc[2, "window_end"] += timedelta(minutes=60)
    frame.loc[3:, "window_end"] += timedelta(minutes=60)
    frame.loc[5, "window_end"] += timedelta(minutes=60)
    frame.loc[6:, "window_end"] += timedelta(minutes=120)
    metrics = incident_metrics(frame)
    assert metrics["true_incidents"] == 1
    assert metrics["duplicate_incidents"] == 2
    assert metrics["incident_recall"] <= 1


def test_offline_merge_by_event_id_fuses_fragments_for_metrics():
    frame = _frame([
        {"predicted": True, "actual_type": "fuga_sostenida", "actual_label": 1, "event_id": "f1"},
        {"predicted": True, "actual_type": "fuga_sostenida", "actual_label": 1, "event_id": "f1"},
        {},
        {"predicted": True, "actual_type": "fuga_sostenida", "actual_label": 1, "event_id": "f1"},
        {"predicted": True, "actual_type": "fuga_sostenida", "actual_label": 1, "event_id": "f1"},
    ])
    frame.loc[2, "window_end"] += timedelta(minutes=60)
    frame.loc[3:, "window_end"] += timedelta(minutes=60)
    incidents = group_operational_incidents(frame, merge_by_event_id=True)
    metrics = incident_metrics(frame, merge_by_event_id=True)
    assert len(incidents) == 1
    assert metrics["true_incidents"] == 1
    assert metrics["duplicate_incidents"] == 0


def test_incident_without_event_id_is_false_incident():
    frame = _frame([
        {"predicted": True, "actual_type": "fuga_sostenida"},
        {"predicted": True, "actual_type": "fuga_sostenida"},
    ])
    metrics = incident_metrics(frame)
    assert metrics["false_incidents"] == 1


def test_missed_event_is_counted():
    metrics = incident_metrics(_frame([{"actual_label": 1, "actual_type": "fuga_sostenida", "event_id": "f1"}]))
    assert metrics["missed_incidents"] == 1
    assert metrics["incident_recall"] == 0


def test_persistent_microleak_confirms_one_incident():
    frame = _frame([
        {"actual_label": 1, "actual_type": "microfuga", "event_id": "m1", "pct_microflujo_5min": 0.5, "duracion_microflujo_continuo_seg": 30},
        {"actual_label": 1, "actual_type": "microfuga", "event_id": "m1", "pct_microflujo_5min": 0.5, "duracion_microflujo_continuo_seg": 30},
        {"actual_label": 1, "actual_type": "microfuga", "event_id": "m1", "pct_microflujo_5min": 0.5, "duracion_microflujo_continuo_seg": 30},
    ])
    incidents = group_operational_incidents(frame)
    assert len(incidents) == 1
    assert incidents[0]["alert_type"] == "microfuga"


def test_isolated_microleak_rule_window_is_not_confirmed():
    frame = _frame([
        {"pct_microflujo_5min": 0.5, "duracion_microflujo_continuo_seg": 30},
        {},
    ])
    assert group_operational_incidents(frame) == []


def test_no_real_events_has_no_nan_or_division_by_zero():
    metrics = incident_metrics(_frame([{}, {}, {}]))
    assert metrics["incident_precision"] == 0
    assert metrics["incident_recall"] == 0
    assert metrics["incident_f1"] == 0
