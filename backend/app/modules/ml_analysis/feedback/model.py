from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class MLAlertFeedback(Base):
    __tablename__ = "ml_alert_feedback"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    alert_id: Mapped[int | None] = mapped_column(ForeignKey("alerts.id"), index=True, nullable=True)
    sensor_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    feature_schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    prediction_score: Mapped[float] = mapped_column(Float, nullable=False)
    decision_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_anomaly: Mapped[bool] = mapped_column(Boolean, nullable=False)
    operator_label: Mapped[str] = mapped_column(String(40), nullable=False)
    operator_event_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    feedback_status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    source_data_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=func.now(), nullable=False)

