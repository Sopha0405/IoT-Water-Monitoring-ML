from datetime import datetime

from pydantic import BaseModel, Field


class AlertBase(BaseModel):
    device_id: str = Field(min_length=1, max_length=80)
    floor: str | None = None
    anomaly_type: str = Field(min_length=1, max_length=80)
    severity: str = Field(min_length=1, max_length=40)
    risk_percentage: float = Field(ge=0, le=100)
    status: str = "open"
    description: str | None = None


class AlertCreate(AlertBase):
    detected_at: datetime | None = None


class AlertUpdate(BaseModel):
    severity: str | None = None
    risk_percentage: float | None = Field(default=None, ge=0, le=100)
    status: str | None = None
    description: str | None = None


class AlertOut(AlertBase):
    id: int
    detected_at: datetime | None = None
    attended_by: int | None = None
    attended_at: datetime | None = None
    observed_value: float | None = None
    last_detected_at: datetime | None = None

    class Config:
        from_attributes = True




