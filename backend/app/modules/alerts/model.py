from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True, nullable=False)
    ml_analysis_id: Mapped[int | None] = mapped_column(ForeignKey("ml_analysis.id"), unique=True, index=True, nullable=True)
    attended_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    anomaly_type: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(40), nullable=False)
    risk_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="open")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    attended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)

    attended_by_user = relationship("User", back_populates="attended_alerts")
    device = relationship("Device", back_populates="alerts")
    ml_analysis = relationship("MLAnalysis", back_populates="generated_alert", foreign_keys=[ml_analysis_id])
    ml_analyses = relationship("MLAnalysis", back_populates="alert", foreign_keys="MLAnalysis.alert_id")
    feedback_entries = relationship("MLAlertFeedback", back_populates="alert")
