from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


class MLAlertFeedback(Base):
    __tablename__ = "ml_alert_feedback"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id"), index=True, nullable=False)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True, nullable=False)
    operator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)

    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    feature_schema_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    prediction_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    decision_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_anomaly: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    operator_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    operator_event_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    feedback_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)

    alert = relationship("Alert", back_populates="feedback_entries")
    operator = relationship("User", foreign_keys=[operator_id])
    device = relationship("Device", back_populates="feedback_entries", foreign_keys=[device_id])
