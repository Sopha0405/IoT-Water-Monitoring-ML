from fastapi import APIRouter, Depends, Query

from app.core.deps import get_current_user
from app.modules.telemetry.schemas import TelemetryPoint
from app.modules.telemetry.service import get_latest_telemetry, get_telemetry_series
from app.modules.users.model import User

router = APIRouter(prefix="/api/v1/telemetry", tags=["telemetry"])


@router.get("/latest", response_model=list[TelemetryPoint])
def latest_telemetry(
    device_id: str | None = None,
    site: str | None = None,
    floor: str | None = None,
    field: str | None = None,
    limit: int = Query(default=50, ge=1, le=2000),
    current_user: User = Depends(get_current_user),
):
    return get_latest_telemetry(device_id=device_id, site=site, floor=floor, field=field, limit=limit)


@router.get("/series", response_model=list[TelemetryPoint])
def telemetry_series(
    device_id: str,
    field: str = "flow_lpm",
    hours: int = Query(default=24, ge=1, le=168),
    limit: int = Query(default=500, ge=1, le=2000),
    current_user: User = Depends(get_current_user),
):
    return get_telemetry_series(device_id=device_id, field=field, hours=hours, limit=limit)
