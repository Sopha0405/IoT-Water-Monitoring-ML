from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.devices.registry import ensure_device_registered
from app.modules.ml_analysis.feedback.model import MLAlertFeedback
from app.modules.ml_analysis.feedback.schemas import FeedbackIn, VALID_FEEDBACK_STATUS, VALID_OPERATOR_LABELS


def list_pending_feedback(db: Session) -> list[dict[str, Any]]:
    rows = db.query(MLAlertFeedback).filter(MLAlertFeedback.feedback_status == "pending").order_by(MLAlertFeedback.reviewed_at.desc()).limit(200).all()
    return [feedback_row(row) for row in rows]


def submit_alert_feedback(alert_id: int, payload: FeedbackIn, db: Session) -> dict[str, Any]:
    if payload.operator_label not in VALID_OPERATOR_LABELS:
        raise HTTPException(status_code=400, detail="operator_label invalido")
    if payload.feedback_status not in VALID_FEEDBACK_STATUS:
        raise HTTPException(status_code=400, detail="feedback_status invalido")
    existing = (
        db.query(MLAlertFeedback)
        .filter(MLAlertFeedback.alert_id == alert_id)
        .order_by(MLAlertFeedback.reviewed_at.desc())
        .first()
    )
    previous_status = existing.feedback_status if existing is not None else None
    transition = f"status:{previous_status or 'new'}->{payload.feedback_status}; reviewer:{payload.reviewed_by}; timestamp:{datetime.utcnow().isoformat()}"
    device = ensure_device_registered(db, payload.sensor_id)
    data = payload.model_dump()
    data.pop("sensor_id", None)
    data.pop("reviewed_by", None)
    data.pop("source_data_hash", None)
    data["device_id"] = device.id
    data["operator_id"] = payload.reviewed_by or 1
    data["notes"] = f"{payload.notes or ''}\n{transition}".strip()
    if existing is not None and existing.feedback_status == "pending":
        row = existing
        for key, value in data.items():
            setattr(row, key, value)
        row.reviewed_at = datetime.utcnow()
    elif existing is not None:
        raise HTTPException(status_code=409, detail="feedback existente no pendiente; requiere versionado externo")
    else:
        row = MLAlertFeedback(alert_id=alert_id, reviewed_at=datetime.utcnow(), **data)
        db.add(row)
    db.commit()
    db.refresh(row)
    return feedback_row(row)


def feedback_stats(db: Session) -> dict[str, Any]:
    rows = db.query(MLAlertFeedback.feedback_status, MLAlertFeedback.operator_label).all()
    by_status: dict[str, int] = {}
    by_label: dict[str, int] = {}
    for status, label in rows:
        by_status[status] = by_status.get(status, 0) + 1
        by_label[label] = by_label.get(label, 0) + 1
    return {"total": len(rows), "by_status": by_status, "by_label": by_label}


def export_feedback_rows(db: Session) -> dict[str, Any]:
    rows = db.query(MLAlertFeedback).filter(MLAlertFeedback.feedback_status == "approved_for_training").all()
    usable = [
        feedback_row(row)
        for row in rows
        if row.operator_label not in {"unknown", "sensor_error", "maintenance"}
    ]
    return {"rows": len(usable), "feedback": usable}


def feedback_row(row: MLAlertFeedback) -> dict[str, Any]:
    return {
        "id": row.id,
        "alert_id": row.alert_id,
        "sensor_id": row.device.device_id if row.device else None,
        "device_id": row.device_id,
        "model_version": row.model_version,
        "feature_schema_version": row.feature_schema_version,
        "prediction_score": row.prediction_score,
        "decision_threshold": row.decision_threshold,
        "predicted_anomaly": row.predicted_anomaly,
        "operator_label": row.operator_label,
        "operator_event_type": row.operator_event_type,
        "feedback_status": row.feedback_status,
        "notes": row.notes,
        "reviewed_by": row.operator_id,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "window_start": row.window_start.isoformat(),
        "window_end": row.window_end.isoformat(),
        "source_data_hash": row.source_data_hash,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }

