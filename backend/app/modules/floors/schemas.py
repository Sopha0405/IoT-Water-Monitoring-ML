from datetime import datetime

from pydantic import BaseModel, Field


class FloorBase(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    is_active: bool = True


class FloorCreate(FloorBase):
    pass


class FloorUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=20)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class FloorOut(FloorBase):
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
    device_count: int = 0

    class Config:
        from_attributes = True
