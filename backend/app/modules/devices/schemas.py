from datetime import datetime

from pydantic import BaseModel, Field


class DeviceBase(BaseModel):
    device_id: str = Field(min_length=1, max_length=80)
    floor: str | None = None
    location: str | None = None
    sensor_type: str = "FS300A"
    status: str = "active"
    last_calibration: datetime | None = None


class DeviceCreate(DeviceBase):
    pass


class DeviceUpdate(BaseModel):
    device_id: str | None = Field(default=None, min_length=1, max_length=80)
    floor: str | None = None
    location: str | None = None
    sensor_type: str | None = None
    status: str | None = None
    last_calibration: datetime | None = None


class DeviceOut(DeviceBase):
    id: int
    created_at: datetime | None = None

    class Config:
        from_attributes = True




