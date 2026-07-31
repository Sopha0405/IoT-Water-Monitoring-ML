from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


VALID_OPERATOR_LABELS = {
    "true_positive", "false_positive", "false_negative", "normal_use", "guard_use",
    "cleaning", "maintenance", "sensor_error", "unknown",
}
VALID_FEEDBACK_STATUS = {"pending", "reviewed", "approved_for_training", "excluded", "disputed"}


class FeedbackIn(BaseModel):
    sensor_id: str
    model_version: str | None = None
    feature_schema_version: str = "water-flow-24f-1"
    prediction_score: float
    decision_threshold: float
    predicted_anomaly: bool
    operator_label: str
    operator_event_type: str | None = None
    feedback_status: str = "pending"
    notes: str | None = None
    reviewed_by: int | None = None
    window_start: datetime
    window_end: datetime
    source_data_hash: str


class FeedbackOut(BaseModel):
    values: dict[str, Any]


class FeedbackStats(BaseModel):
    total: int
    by_status: dict[str, int]
    by_label: dict[str, int]

