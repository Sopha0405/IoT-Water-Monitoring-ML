from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.postgres import Base
from app.modules.alerts.model import Alert  # noqa: F401
from app.modules.devices.model import Device
from app.modules.floors.model import Floor  # noqa: F401
from app.modules.floors.schemas import FloorCreate, FloorUpdate
from app.modules.floors.service import create_floor, delete_floor, list_floors, update_floor
from app.modules.ml_analysis.feedback.model import MLAlertFeedback  # noqa: F401
from app.modules.ml_analysis.inference.model import MLAnalysis  # noqa: F401
from app.modules.roles.model import Role  # noqa: F401
from app.modules.users.model import User  # noqa: F401


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_create_list_update_and_delete_floor():
    db = make_session()
    floor = create_floor(db, FloorCreate(code="PB", name="Planta Baja", description=None))

    assert floor.id is not None
    assert list_floors(db)[0]["code"] == "PB"

    updated = update_floor(db, floor.id, FloorUpdate(name="Nivel PB"))
    assert updated.name == "Nivel PB"

    delete_floor(db, floor.id)
    assert list_floors(db, include_inactive=True) == []


def test_reject_duplicate_floor_code():
    db = make_session()
    create_floor(db, FloorCreate(code="PB", name="Planta Baja", description=None))

    try:
      create_floor(db, FloorCreate(code="PB", name="Duplicado", description=None))
    except Exception as exc:
      assert getattr(exc, "status_code", None) == 409
    else:
      raise AssertionError("duplicate code was accepted")


def test_reject_delete_floor_with_devices():
    db = make_session()
    floor = create_floor(db, FloorCreate(code="PB", name="Planta Baja", description=None))
    db.add(Device(device_id="sensor-pb", floor_id=floor.id, floor="PB", sensor_type="FS300A", status="active"))
    db.commit()

    try:
      delete_floor(db, floor.id)
    except Exception as exc:
      assert getattr(exc, "status_code", None) == 409
    else:
      raise AssertionError("floor with devices was deleted")
