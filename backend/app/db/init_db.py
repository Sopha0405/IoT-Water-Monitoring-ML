from datetime import datetime

from sqlalchemy import text

from app.core.config import settings
from app.core.security import hash_password
from app.db.postgres import Base, engine

# Import models so SQLAlchemy registers them before create_all.
from app.modules.alerts.model import Alert  # noqa: F401
from app.modules.devices.model import Device  # noqa: F401
from app.modules.ml_analysis.model import MLAnalysis  # noqa: F401
from app.modules.roles.model import Role
from app.modules.users.model import User


def init_db() -> None:
    Base.metadata.create_all(bind=engine)

    from app.db.postgres import SessionLocal

    db = SessionLocal()
    try:
        _ensure_ml_analysis_columns(db)
        default_roles = {
            1: "Supervisor",
            2: "Tecnico",
            3: "Admin",
        }
        for role_id, name in default_roles.items():
            exists = db.query(Role).filter(Role.id == role_id).first()
            if not exists:
                db.add(Role(id=role_id, name=name))

        admin = db.query(User).filter(User.email == settings.initial_admin_email).first()
        if not admin:
            db.add(
                User(
                    name=settings.initial_admin_name,
                    email=settings.initial_admin_email,
                    password=hash_password(settings.initial_admin_password),
                    phone=None,
                    floor=settings.initial_admin_floor,
                    role_id=settings.admin_role_id,
                    is_active=True,
                )
            )
        demo_users = [
            ("Admin Sistema", "admin@corp.com", "admin123", "+591 7000-0001", "PB", 3),
            ("Ana Martinez", "ana@corp.com", "ana12345", "+591 7234-5678", "P1", 1),
            ("Maria Gonzalez", "maria@corp.com", "maria12345", "+591 7012-3456", "P2", 1),
            ("Carlos Rodriguez", "carlos@corp.com", "carlos123", "+591 7123-4567", "P3", 3),
            ("Lucia Perez", "lucia@corp.com", "lucia12345", "+591 7456-7890", "P1", 2),
        ]
        for name, email, password, phone, floor, role_id in demo_users:
            exists = db.query(User).filter(User.email == email).first()
            if not exists:
                db.add(
                    User(
                        name=name,
                        email=email,
                        password=hash_password(password),
                        phone=phone,
                        floor=floor,
                        role_id=role_id,
                        is_active=True,
                    )
                )

        demo_devices = [
            ("pb-wokwi", "PB", "Medidor Wokwi - Planta Baja", "active", datetime(2026, 5, 29)),
            ("floor1-python", "P1", "Simulador Python - Piso 1", "active", datetime(2026, 5, 29)),
            ("floor3-python", "P3", "Simulador Python - Piso 3", "active", datetime(2026, 5, 29)),
        ]
        for device_id, floor, location, device_status, last_calibration in demo_devices:
            exists = db.query(Device).filter(Device.device_id == device_id).first()
            if not exists:
                db.add(
                    Device(
                        device_id=device_id,
                        floor=floor,
                        location=location,
                        sensor_type="FS300A",
                        status=device_status,
                        last_calibration=last_calibration,
                    )
                )

        demo_alerts = [
            ("SENS-002-PB", "PB", "Fuga Detectada", "critical", 87, "open", "Posible fuga detectada por patron anormal de consumo", datetime(2026, 2, 22, 14, 35)),
            ("SENS-003-P1", "P1", "Consumo Elevado", "warning", 45, "resolved", "Consumo elevado durante horas no laborales", datetime(2026, 2, 22, 13, 20)),
            ("SENS-007-P3", "P3", "Sensor Offline", "critical", 92, "investigating", "Sensor desconectado; requiere mantenimiento", datetime(2026, 2, 22, 12, 10)),
            ("SENS-006-P2", "P2", "Consumo Elevado", "info", 23, "resolved", "Pico de consumo durante limpieza", datetime(2026, 2, 22, 10, 45)),
            ("SENS-001-PB", "PB", "Fuga Detectada", "critical", 78, "open", "Discrepancia en balance hidrico principal", datetime(2026, 2, 22, 9, 15)),
        ]
        for device_id, floor, anomaly_type, severity, risk, alert_status, description, detected_at in demo_alerts:
            exists = (
                db.query(Alert)
                .filter(Alert.device_id == device_id, Alert.detected_at == detected_at)
                .first()
            )
            if not exists:
                db.add(
                    Alert(
                        device_id=device_id,
                        floor=floor,
                        anomaly_type=anomaly_type,
                        severity=severity,
                        risk_percentage=risk,
                        status=alert_status,
                        description=description,
                        detected_at=detected_at,
                    )
                )
        db.commit()
    finally:
        db.close()


def _ensure_ml_analysis_columns(db) -> None:
    statements = [
        "ALTER TABLE ml_analysis ALTER COLUMN alert_id DROP NOT NULL",
        "ALTER TABLE ml_analysis ADD COLUMN IF NOT EXISTS device_id VARCHAR(80)",
        "ALTER TABLE ml_analysis ADD COLUMN IF NOT EXISTS floor VARCHAR(40)",
        "ALTER TABLE ml_analysis ADD COLUMN IF NOT EXISTS observed_value DOUBLE PRECISION",
        "CREATE INDEX IF NOT EXISTS ix_ml_analysis_device_id ON ml_analysis(device_id)",
        "CREATE INDEX IF NOT EXISTS ix_ml_analysis_floor ON ml_analysis(floor)",
    ]
    for statement in statements:
        db.execute(text(statement))
    db.commit()
