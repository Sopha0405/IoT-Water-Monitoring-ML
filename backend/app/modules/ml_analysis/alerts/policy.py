from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from app.modules.ml_analysis.streaming.temporal_state import SensorTemporalState

logger = logging.getLogger(__name__)

GENERAL_CONFIRMATION_WINDOW = 3
GENERAL_MIN_ANOMALOUS = 2
SUSTAINED_MIN_CONSECUTIVE = 2
MICROFLOW_MIN_CONSECUTIVE = 2
INCIDENT_MERGE_GAP_MINUTES = 45
ALERT_CLOSE_GAP_MINUTES = 15
MAX_NORMAL_WINDOWS_BEFORE_CLOSE = 1


@dataclass(frozen=True)
class AlertDecision:
    should_alert: bool
    alert_type: str | None = None
    reason: str | None = None


@dataclass
class AlertAccumulator:
    sensor_id: str
    alert_type: str
    started_at: datetime
    last_seen_at: datetime
    window_count: int
    max_score: float
    mean_flow_lpm: float
    status: str
    source_model_version: str
    feature_schema_version: str


@dataclass
class PendingIncident:
    sensor_id: str
    alert_type: str
    started_at: datetime
    last_seen_at: datetime
    triggering_windows: int
    maximum_score: float
    mean_flow_lpm: float
    event_ids: list[str]
    normal_windows: int = 0


def microleak_rule(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["pct_microflujo_5min"].ge(0.38)
        & frame["duracion_microflujo_continuo_seg"].ge(25)
        & frame["mu_q"].ge(0.30)
    )


def classify_operational_alert_type(row: pd.Series) -> str:
    actual = str(row.get("actual_type") or "").lower().strip()
    if actual in {"microfuga", "fuga_sostenida", "pico_anomalo", "consumo_creciente"}:
        return actual
    if bool(row.get("rule_predicted_microleak")) or bool(microleak_rule(pd.DataFrame([row])).iloc[0]):
        return "microfuga"
    return "general_anomaly"


def confirmed_windows(frame: pd.DataFrame) -> pd.Series:
    confirmed = pd.Series(False, index=frame.index)
    if frame.empty:
        return confirmed
    working = frame.copy()
    if "alert_type" not in working:
        working["alert_type"] = working.apply(classify_operational_alert_type, axis=1)
    for _, sensor in working.groupby("sensor_id", sort=False):
        for alert_type, section in sensor.groupby("alert_type", sort=False):
            idx = list(section.index)
            predicted = section["predicted_anomaly"].astype(bool).tolist()
            micro = microleak_rule(section).astype(bool).tolist()
            for pos, row_index in enumerate(idx):
                if alert_type == "microfuga":
                    recent = micro[max(0, pos - MICROFLOW_MIN_CONSECUTIVE + 1) : pos + 1]
                    confirmed.loc[row_index] = len(recent) >= MICROFLOW_MIN_CONSECUTIVE and all(recent)
                elif not predicted[pos]:
                    logger.debug("ventana pendiente de confirmacion type=%s", alert_type)
                    continue
                elif alert_type == "fuga_sostenida":
                    recent = predicted[max(0, pos - SUSTAINED_MIN_CONSECUTIVE + 1) : pos + 1]
                    confirmed.loc[row_index] = len(recent) >= SUSTAINED_MIN_CONSECUTIVE and all(recent)
                elif alert_type == "general_anomaly":
                    confirmed.loc[row_index] = False
                elif alert_type == "consumo_creciente":
                    recent = predicted[max(0, pos - GENERAL_CONFIRMATION_WINDOW + 1) : pos + 1]
                    confirmed.loc[row_index] = sum(recent) >= GENERAL_MIN_ANOMALOUS
                else:
                    confirmed.loc[row_index] = True
                logger.debug(
                    "ventana anomala observada type=%s confirmed=%s",
                    alert_type,
                    bool(confirmed.loc[row_index]),
                )
    return confirmed


def group_operational_incidents(
    frame: pd.DataFrame,
    *,
    merge_by_event_id: bool = False,
) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    ordered = frame.sort_values(["sensor_id", "window_end"]).copy()
    ordered["window_end"] = pd.to_datetime(ordered["window_end"], utc=True)
    ordered["alert_type"] = ordered.apply(classify_operational_alert_type, axis=1)
    ordered["confirmed_window"] = confirmed_windows(ordered)
    incidents: list[dict[str, Any]] = []
    open_by_key: dict[tuple[str, str], PendingIncident] = {}
    for _, row in ordered.iterrows():
        sensor_id = str(row.get("sensor_id"))
        alert_type = str(row.get("alert_type"))
        now = row["window_end"].to_pydatetime()
        _close_stale(open_by_key, incidents, sensor_id, now)
        if not bool(row.get("confirmed_window")):
            if bool(row.get("predicted_anomaly")) or (alert_type == "microfuga" and bool(microleak_rule(pd.DataFrame([row])).iloc[0])):
                logger.debug("ventana pendiente de confirmacion sensor=%s type=%s", sensor_id, alert_type)
                continue
            _count_normal(open_by_key, incidents, sensor_id, now)
            continue
        incident = _find_merge_target(open_by_key, sensor_id, alert_type, now, row)
        if incident is None:
            incident = PendingIncident(
                sensor_id=sensor_id,
                alert_type=alert_type,
                started_at=now,
                last_seen_at=now,
                triggering_windows=0,
                maximum_score=float(row.get("anomaly_score", 0.0)),
                mean_flow_lpm=0.0,
                event_ids=[],
            )
            open_by_key[(sensor_id, alert_type)] = incident
            logger.debug("alerta confirmada sensor=%s type=%s", sensor_id, alert_type)
        else:
            logger.debug("alerta fusionada sensor=%s type=%s", sensor_id, alert_type)
        _add_window(incident, row, now)
    incidents.extend(_serialize_incident(incident) for incident in open_by_key.values())
    return _merge_incidents_by_event_id(incidents) if merge_by_event_id else incidents


def incident_metrics(frame: pd.DataFrame, *, merge_by_event_id: bool = False) -> dict[str, Any]:
    incidents = group_operational_incidents(frame, merge_by_event_id=merge_by_event_id)
    actual_events = set(
        frame.loc[frame["actual_label"].eq(1) & frame["event_id"].notna(), "event_id"]
        .astype(str)
        .tolist()
    )
    detected_events: set[str] = set()
    true_incidents = 0
    false_incidents = 0
    duplicate_incidents = 0
    for incident in incidents:
        event_ids = [event_id for event_id in incident["event_ids"] if event_id in actual_events]
        new_events = [event_id for event_id in event_ids if event_id not in detected_events]
        if new_events:
            true_incidents += 1
            detected_events.update(new_events)
            logger.debug("evento real detectado events=%s", new_events)
        elif event_ids:
            duplicate_incidents += 1
            logger.debug("incidente duplicado events=%s", event_ids)
        else:
            false_incidents += 1
    missed_events = actual_events - detected_events
    for event_id in sorted(missed_events):
        logger.debug("evento real perdido event_id=%s", event_id)
    denominator = true_incidents + false_incidents + duplicate_incidents
    precision = true_incidents / denominator if denominator else 0.0
    recall = len(detected_events) / len(actual_events) if actual_events else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    days = max(1, pd.to_datetime(frame["window_end"], utc=True).dt.date.nunique()) if not frame.empty else 1
    return {
        "raw_anomalous_windows": int(frame["predicted_anomaly"].sum()) if "predicted_anomaly" in frame else 0,
        "confirmed_windows": int(sum(item["triggering_windows"] for item in incidents)),
        "grouped_incidents": len(incidents),
        "true_incidents": true_incidents,
        "false_incidents": false_incidents,
        "missed_incidents": len(missed_events),
        "duplicate_incidents": duplicate_incidents,
        "incident_precision": precision,
        "incident_recall": recall,
        "incident_f1": f1,
        "operational_false_alerts_per_day": false_incidents / days,
        "detected_event_ids": sorted(detected_events),
        "missed_event_ids": sorted(missed_events),
        "items": incidents,
    }


def _find_merge_target(
    open_by_key: dict[tuple[str, str], PendingIncident],
    sensor_id: str,
    alert_type: str,
    now: datetime,
    row: pd.Series,
) -> PendingIncident | None:
    existing = open_by_key.get((sensor_id, alert_type))
    if existing is not None and now - existing.last_seen_at <= timedelta(minutes=INCIDENT_MERGE_GAP_MINUTES):
        return existing
    row_event = str(row.get("event_id")) if pd.notna(row.get("event_id")) else None
    if row_event:
        for incident in open_by_key.values():
            if incident.sensor_id == sensor_id and row_event in incident.event_ids:
                return incident
    return None


def _add_window(incident: PendingIncident, row: pd.Series, now: datetime) -> None:
    incident.normal_windows = 0
    incident.triggering_windows += 1
    incident.last_seen_at = now
    incident.maximum_score = max(incident.maximum_score, float(row.get("anomaly_score", 0.0)))
    count = incident.triggering_windows
    incident.mean_flow_lpm = ((incident.mean_flow_lpm * (count - 1)) + float(row.get("mu_q", 0.0))) / count
    if pd.notna(row.get("event_id")):
        event_id = str(row.get("event_id"))
        if event_id not in incident.event_ids:
            incident.event_ids.append(event_id)


def _close_stale(
    open_by_key: dict[tuple[str, str], PendingIncident],
    incidents: list[dict[str, Any]],
    sensor_id: str,
    now: datetime,
) -> None:
    for key, incident in list(open_by_key.items()):
        if key[0] == sensor_id and now - incident.last_seen_at > timedelta(minutes=INCIDENT_MERGE_GAP_MINUTES):
            incidents.append(_serialize_incident(incident, closed_at=now))
            del open_by_key[key]
            logger.debug("alerta cerrada sensor=%s type=%s", incident.sensor_id, incident.alert_type)


def _count_normal(
    open_by_key: dict[tuple[str, str], PendingIncident],
    incidents: list[dict[str, Any]],
    sensor_id: str,
    now: datetime,
) -> None:
    for key, incident in list(open_by_key.items()):
        if key[0] != sensor_id:
            continue
        incident.normal_windows += 1
        if incident.normal_windows > MAX_NORMAL_WINDOWS_BEFORE_CLOSE:
            incidents.append(_serialize_incident(incident, closed_at=now))
            del open_by_key[key]
            logger.debug("alerta cerrada por normalidad sensor=%s type=%s", incident.sensor_id, incident.alert_type)


def _serialize_incident(incident: PendingIncident, closed_at: datetime | None = None) -> dict[str, Any]:
    return {
        "sensor_id": incident.sensor_id,
        "alert_type": incident.alert_type,
        "started_at": incident.started_at.isoformat(),
        "last_seen_at": incident.last_seen_at.isoformat(),
        "closed_at": closed_at.isoformat() if closed_at else None,
        "triggering_windows": incident.triggering_windows,
        "maximum_score": incident.maximum_score,
        "mean_flow_lpm": incident.mean_flow_lpm,
        "event_ids": incident.event_ids,
        "confirmed_by_policy": True,
    }


def _merge_incidents_by_event_id(incidents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    by_event: dict[tuple[str, str, str], dict[str, Any]] = {}
    for incident in incidents:
        event_ids = [str(event_id) for event_id in incident.get("event_ids", [])]
        target = None
        for event_id in event_ids:
            key = (str(incident["sensor_id"]), str(incident["alert_type"]), event_id)
            if key in by_event:
                target = by_event[key]
                break
        if target is None:
            merged.append(incident)
            for event_id in event_ids:
                by_event[(str(incident["sensor_id"]), str(incident["alert_type"]), event_id)] = incident
            continue

        logger.debug("alerta fusionada por event_id events=%s", event_ids)
        old_count = int(target["triggering_windows"])
        new_count = int(incident["triggering_windows"])
        total = old_count + new_count
        target["started_at"] = min(str(target["started_at"]), str(incident["started_at"]))
        target["last_seen_at"] = max(str(target["last_seen_at"]), str(incident["last_seen_at"]))
        if incident.get("closed_at"):
            target["closed_at"] = incident["closed_at"]
        target["triggering_windows"] = total
        target["maximum_score"] = max(float(target["maximum_score"]), float(incident["maximum_score"]))
        target["mean_flow_lpm"] = (
            float(target["mean_flow_lpm"]) * old_count + float(incident["mean_flow_lpm"]) * new_count
        ) / total
        for event_id in event_ids:
            if event_id not in target["event_ids"]:
                target["event_ids"].append(event_id)
            by_event[(str(incident["sensor_id"]), str(incident["alert_type"]), event_id)] = target
    return merged




class AlertPolicy:
    def __init__(
        self,
        critical_peak_lpm: float = 20.0,
        cooldown_minutes: int = 15,
        normal_windows_required_to_close: int = 3,
        inactivity_timeout_minutes: int = 15,
    ) -> None:
        self.critical_peak_lpm = critical_peak_lpm
        self.cooldown = timedelta(minutes=cooldown_minutes)
        self.normal_windows_required_to_close = normal_windows_required_to_close
        self.inactivity_timeout = timedelta(minutes=inactivity_timeout_minutes)
        self._open_alerts: dict[tuple[str, str], AlertAccumulator] = {}

    def evaluate_sensor_error(self, sensor_id: str, now: datetime, state: SensorTemporalState) -> AlertDecision:
        self.close_stale_alerts(now, state)
        return self._dedupe(sensor_id, "sensor_error", now, state, "error tecnico del sensor")

    def evaluate(
        self,
        sensor_id: str,
        now: datetime,
        max_flow_lpm: float,
        mean_flow_lpm: float,
        score: float,
        prediction: str,
        state: SensorTemporalState,
    ) -> AlertDecision:
        self.close_stale_alerts(now, state)
        if max_flow_lpm >= self.critical_peak_lpm:
            return self._dedupe(sensor_id, "critical_peak", now, state, "pico critico")
        if prediction == "normal":
            self.update_normal_window(sensor_id, now, state)
            return AlertDecision(False)
        if state.consecutive_microflow_windows >= 6 or (
            state.persistent_deviation_windows >= 4 and state.low_variability_windows >= 4
        ):
            return self._dedupe(sensor_id, "microleak", now, state, "microflujo sostenido")
        recent = list(state.predictions)
        if len(recent) >= 2 and recent[-2:] == ["anomaly", "anomaly"]:
            return self._dedupe(sensor_id, "sustained_leak", now, state, "dos ventanas anomalas consecutivas")
        if recent.count("anomaly") >= 2:
            return self._dedupe(sensor_id, "general_anomaly", now, state, "dos de tres ventanas anomalas")
        return AlertDecision(False)

    def close_alert(self, sensor_id: str, alert_type: str, now: datetime, state: SensorTemporalState, reason: str = "closed") -> AlertAccumulator | None:
        key = (sensor_id, alert_type)
        alert = self._open_alerts.pop(key, None)
        state.open_alert_by_type.pop(alert_type, None)
        state.normal_windows_by_type.pop(alert_type, None)
        if alert is not None:
            alert.status = reason
            alert.last_seen_at = now
        return alert

    def close_stale_alerts(self, now: datetime, state: SensorTemporalState) -> None:
        for sensor_id, alert_type in list(self._open_alerts):
            alert = self._open_alerts[(sensor_id, alert_type)]
            if now - alert.last_seen_at > self.inactivity_timeout:
                self.close_alert(sensor_id, alert_type, now, state, "closed_stale")

    def update_normal_window(self, sensor_id: str, now: datetime, state: SensorTemporalState) -> None:
        for alert_type in list(state.open_alert_by_type):
            state.normal_windows_by_type[alert_type] = state.normal_windows_by_type.get(alert_type, 0) + 1
            if state.normal_windows_by_type[alert_type] >= self.normal_windows_required_to_close:
                self.close_alert(sensor_id, alert_type, now, state, "closed_normal")

    def upsert_alert(
        self,
        sensor_id: str,
        alert_type: str,
        now: datetime,
        score: float,
        mean_flow_lpm: float,
        source_model_version: str,
        feature_schema_version: str,
    ) -> AlertAccumulator:
        key = (sensor_id, alert_type)
        existing = self._open_alerts.get(key)
        if existing is None:
            existing = AlertAccumulator(sensor_id, alert_type, now, now, 1, score, mean_flow_lpm, "open", source_model_version, feature_schema_version)
            self._open_alerts[key] = existing
            return existing
        total = existing.mean_flow_lpm * existing.window_count + mean_flow_lpm
        existing.window_count += 1
        existing.last_seen_at = now
        existing.max_score = max(existing.max_score, score)
        existing.mean_flow_lpm = total / existing.window_count
        return existing

    def _dedupe(self, sensor_id: str, alert_type: str, now: datetime, state: SensorTemporalState, reason: str) -> AlertDecision:
        last = state.last_alert_at.get(alert_type)
        if alert_type in state.open_alert_by_type:
            return AlertDecision(False, alert_type, "alerta abierta existente")
        if last is not None and now - last < self.cooldown:
            return AlertDecision(False, alert_type, "cooldown activo")
        state.last_alert_at[alert_type] = now
        state.open_alert_by_type[alert_type] = f"{sensor_id}:{alert_type}"
        state.normal_windows_by_type[alert_type] = 0
        return AlertDecision(True, alert_type, reason)
