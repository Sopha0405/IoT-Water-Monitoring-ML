from datetime import datetime

from pydantic import BaseModel


class TelemetryPoint(BaseModel):
    time: datetime | None = None
    device_id: str | None = None
    site: str | None = None
    floor: str | None = None
    tenant: str | None = None
    source: str = "real"
    field: str
    value: float




