from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_supervisor
from app.db.postgres import get_db
from app.modules.devices.model import Device
from app.modules.devices.schemas import DeviceOut
from app.modules.floors.schemas import FloorCreate, FloorOut, FloorUpdate
from app.modules.floors.service import (
    create_floor,
    delete_floor,
    floor_to_dict,
    get_floor_or_404,
    list_floors,
    update_floor,
)
from app.modules.users.model import User

router = APIRouter(prefix="/api/v1/floors", tags=["floors"])


@router.get("/", response_model=list[FloorOut])
def get_floors(
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    del current_user
    return list_floors(db, include_inactive=include_inactive)


@router.get("/{floor_id}", response_model=FloorOut)
def get_floor(
    floor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    del current_user
    floor = get_floor_or_404(db, floor_id)
    device_count = db.query(Device).filter(Device.floor_id == floor.id).count()
    return floor_to_dict(floor, device_count)


@router.get("/{floor_id}/devices", response_model=list[DeviceOut])
def get_floor_devices(
    floor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    del current_user
    floor = get_floor_or_404(db, floor_id)
    return db.query(Device).filter(Device.floor_id == floor.id).order_by(Device.device_id.asc()).all()


@router.post("/", response_model=FloorOut, status_code=status.HTTP_201_CREATED)
def post_floor(
    data: FloorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor),
):
    del current_user
    floor = create_floor(db, data)
    return floor_to_dict(floor, 0)


@router.put("/{floor_id}", response_model=FloorOut)
def put_floor(
    floor_id: int,
    data: FloorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor),
):
    del current_user
    floor = update_floor(db, floor_id, data)
    device_count = db.query(Device).filter(Device.floor_id == floor.id).count()
    return floor_to_dict(floor, device_count)


@router.delete("/{floor_id}")
def remove_floor(
    floor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor),
):
    del current_user
    delete_floor(db, floor_id)
    return {"deleted": True}
