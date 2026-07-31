from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.postgres import get_db
from app.modules.ml_analysis.feedback.model import MLAlertFeedback
from app.modules.ml_analysis.feedback.schemas import FeedbackIn
from app.modules.ml_analysis.feedback.service import (
    export_feedback_rows,
    feedback_stats,
    list_pending_feedback,
    submit_alert_feedback,
)

router = APIRouter(prefix="/api/v1/ml/feedback", tags=["ml-feedback"])


@router.get("/pending")
def pending_feedback(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return list_pending_feedback(db)


@router.post("/{alert_id}")
def submit_feedback(alert_id: int, payload: FeedbackIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    return submit_alert_feedback(alert_id, payload, db)


@router.get("/stats")
def get_feedback_stats(db: Session = Depends(get_db)) -> dict[str, Any]:
    return feedback_stats(db)


@router.post("/export")
def export_feedback(db: Session = Depends(get_db)) -> dict[str, Any]:
    return export_feedback_rows(db)

