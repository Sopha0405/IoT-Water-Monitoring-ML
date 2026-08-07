from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    device_id: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    floor_id: Mapped[int | None] = mapped_column(ForeignKey("floors.id", ondelete="RESTRICT"), index=True, nullable=True)
    floor: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    location: Mapped[str | None] = mapped_column(String(160), nullable=True)
    sensor_type: Mapped[str] = mapped_column(String(40), nullable=False, default="FS300A")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    last_calibration: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    floor_ref = relationship("Floor", back_populates="devices")
    alerts = relationship("Alert", back_populates="device")
    ml_analyses = relationship("MLAnalysis", back_populates="device")
    feedback_entries = relationship("MLAlertFeedback", back_populates="device")

    @property
    def floor_info(self):
        return self.floor_ref




