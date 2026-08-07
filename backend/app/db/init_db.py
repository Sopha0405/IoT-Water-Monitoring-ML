from datetime import datetime

from sqlalchemy import text

from app.core.config import settings
from app.core.security import hash_password
from app.db.postgres import Base, engine

# Import models so SQLAlchemy registers them before create_all.
from app.modules.alerts.model import Alert  # noqa: F401
from app.modules.devices.model import Device  # noqa: F401
from app.modules.floors.model import Floor
from app.modules.ml_analysis.inference.model import MLAnalysis  # noqa: F401
from app.modules.ml_analysis.feedback.model import MLAlertFeedback  # noqa: F401
from app.modules.roles.model import Role
from app.modules.users.model import User


def init_db() -> None:
    Base.metadata.create_all(bind=engine)

    from app.db.postgres import SessionLocal

    db = SessionLocal()
    try:
        _ensure_role_schema(db)
        _ensure_floor_schema(db)
        _ensure_user_scope_columns(db)
        _ensure_ml_analysis_columns(db)
        _ensure_ml_feedback_table(db)
        _ensure_logical_relationship_constraints(db)
        default_roles = {
            1: "Supervisor",
            2: "Tecnico",
            3: "Admin",
        }
        for role_id, name in default_roles.items():
            exists = db.query(Role).filter(Role.id == role_id).first()
            if not exists:
                db.add(Role(id=role_id, name=name))

        default_floors = [
            ("PB", "Planta Baja", "Nivel principal del edificio"),
            ("P1", "Piso 1", "Primer piso"),
            ("P2", "Piso 2", "Segundo piso"),
            ("P3", "Piso 3", "Tercer piso"),
        ]
        for code, name, description in default_floors:
            exists = db.query(Floor).filter(Floor.code == code).first()
            if not exists:
                db.add(Floor(code=code, name=name, description=description, is_active=True))

        admin_floor = db.query(Floor).filter(Floor.code == settings.initial_admin_floor).first()
        admin = db.query(User).filter(User.email == settings.initial_admin_email).first()
        if not admin:
            db.add(
                User(
                    name=settings.initial_admin_name,
                    email=settings.initial_admin_email,
                    password=hash_password(settings.initial_admin_password),
                    phone=None,
                    floor_id=admin_floor.id if admin_floor else None,
                    floor=settings.initial_admin_floor,
                        limit_to_floor=False,
                        role_id=settings.admin_role_id,
                    is_active=True,
                )
            )
        else:
            admin.name = settings.initial_admin_name
            admin.password = hash_password(settings.initial_admin_password)
            admin.floor_id = admin_floor.id if admin_floor else None
            admin.floor = settings.initial_admin_floor
            admin.limit_to_floor = False
            admin.role_id = settings.admin_role_id
            admin.is_active = True

        demo_users = [
            ("Admin Sistema", "admin@corp.com", "admin123", "+591 7000-0001", "PB", 3),
            ("Ana Martinez", "ana@corp.com", "ana12345", "+591 7234-5678", "P1", 1),
            ("Maria Gonzalez", "maria@corp.com", "maria12345", "+591 7012-3456", "P2", 1),
            ("Carlos Rodriguez", "carlos@corp.com", "carlos123", "+591 7123-4567", "P3", 3),
            ("Lucia Perez", "lucia@corp.com", "lucia12345", "+591 7456-7890", "P1", 2),
        ]
        demo_users = []
        for name, email, password, phone, floor, role_id in demo_users:
            exists = db.query(User).filter(User.email == email).first()
            floor_row = db.query(Floor).filter(Floor.code == floor).first()
            if not exists:
                db.add(
                    User(
                        name=name,
                        email=email,
                        password=hash_password(password),
                        phone=phone,
                        floor_id=floor_row.id if floor_row else None,
                        floor=floor,
                        limit_to_floor=False,
                        role_id=role_id,
                        is_active=True,
                    )
                )
            else:
                exists.name = name
                exists.password = hash_password(password)
                exists.phone = phone
                exists.floor_id = floor_row.id if floor_row else None
                exists.floor = floor
                exists.limit_to_floor = False
                exists.role_id = role_id
                exists.is_active = True

        demo_devices = [
            ("pb-wokwi", "PB", "Medidor Wokwi - Planta Baja", "active", datetime(2026, 5, 29)),
            ("floor1-python", "P1", "Simulador Python - Piso 1", "active", datetime(2026, 5, 29)),
            ("floor2-python", "P2", "Simulador Python - Piso 2", "active", datetime(2026, 5, 29)),
            ("floor3-python", "P3", "Simulador Python - Piso 3", "active", datetime(2026, 5, 29)),
        ]
        demo_devices = []
        for device_id, floor, location, device_status, last_calibration in demo_devices:
            exists = db.query(Device).filter(Device.device_id == device_id).first()
            floor_row = db.query(Floor).filter(Floor.code == floor).first()
            if not exists:
                db.add(
                    Device(
                        device_id=device_id,
                        floor_id=floor_row.id if floor_row else None,
                        floor=floor,
                        location=location,
                        sensor_type="FS300A",
                        status=device_status,
                        last_calibration=last_calibration,
                    )
                )
            elif floor_row and exists.floor_id is None:
                exists.floor_id = floor_row.id

        demo_alerts = [
            ("pb-wokwi", "PB", "Fuga Detectada", "critical", 87, "open", "Posible fuga detectada por patron anormal de consumo", datetime(2026, 2, 22, 14, 35)),
            ("floor1-python", "P1", "Consumo Elevado", "warning", 45, "resolved", "Consumo elevado durante horas no laborales", datetime(2026, 2, 22, 13, 20)),
            ("floor3-python", "P3", "Sensor Offline", "critical", 92, "investigating", "Sensor desconectado; requiere mantenimiento", datetime(2026, 2, 22, 12, 10)),
            ("floor2-python", "P2", "Consumo Elevado", "info", 23, "resolved", "Pico de consumo durante limpieza", datetime(2026, 2, 22, 10, 45)),
            ("pb-wokwi", "PB", "Fuga Detectada", "critical", 78, "open", "Discrepancia en balance hidrico principal", datetime(2026, 2, 22, 9, 15)),
        ]
        demo_alerts = []
        for device_id, floor, anomaly_type, severity, risk, alert_status, description, detected_at in demo_alerts:
            device = db.query(Device).filter(Device.device_id == device_id).first()
            if not device:
                continue
            exists = (
                db.query(Alert)
                .filter(Alert.device_id == device.id, Alert.detected_at == detected_at)
                .first()
            )
            if not exists:
                db.add(
                    Alert(
                        device_id=device.id,
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


def _ensure_floor_schema(db) -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS floors (
            id SERIAL PRIMARY KEY,
            code VARCHAR(20) NOT NULL UNIQUE,
            name VARCHAR(100) NOT NULL,
            description VARCHAR(255),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP
        )
        """,
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_floors_code ON floors(code)",
        "ALTER TABLE devices ADD COLUMN IF NOT EXISTS floor_id INTEGER",
        "CREATE INDEX IF NOT EXISTS ix_devices_floor_id ON devices(floor_id)",
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'fk_devices_floor_id_floors'
          ) THEN
            ALTER TABLE devices
            ADD CONSTRAINT fk_devices_floor_id_floors
            FOREIGN KEY (floor_id) REFERENCES floors(id) ON DELETE RESTRICT;
          END IF;
        END $$;
        """,
    ]
    for statement in statements:
        db.execute(text(statement))
    db.commit()


def _ensure_role_schema(db) -> None:
    statements = [
        "ALTER TABLE roles ADD COLUMN IF NOT EXISTS description TEXT",
    ]
    for statement in statements:
        db.execute(text(statement))
    db.commit()


def _ensure_user_scope_columns(db) -> None:
    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS floor_id INTEGER",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS limit_to_floor BOOLEAN NOT NULL DEFAULT FALSE",
        "CREATE INDEX IF NOT EXISTS ix_users_floor_id ON users(floor_id)",
        "CREATE INDEX IF NOT EXISTS ix_users_limit_to_floor ON users(limit_to_floor)",
    ]
    for statement in statements:
        db.execute(text(statement))
    db.commit()


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


def _ensure_ml_feedback_table(db) -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS ml_alert_feedback (
            id SERIAL PRIMARY KEY,
            alert_id INTEGER REFERENCES alerts(id),
            sensor_id VARCHAR(80) NOT NULL,
            model_version VARCHAR(120),
            feature_schema_version VARCHAR(40) NOT NULL,
            prediction_score DOUBLE PRECISION NOT NULL,
            decision_threshold DOUBLE PRECISION NOT NULL,
            predicted_anomaly BOOLEAN NOT NULL,
            operator_label VARCHAR(40) NOT NULL,
            operator_event_type VARCHAR(80),
            feedback_status VARCHAR(40) NOT NULL DEFAULT 'pending',
            notes TEXT,
            reviewed_by INTEGER,
            reviewed_at TIMESTAMP,
            window_start TIMESTAMP NOT NULL,
            window_end TIMESTAMP NOT NULL,
            source_data_hash VARCHAR(128) NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """,
        "ALTER TABLE ml_alert_feedback ADD COLUMN IF NOT EXISTS device_id INTEGER",
        "ALTER TABLE ml_alert_feedback ADD COLUMN IF NOT EXISTS operator_id INTEGER",
        "CREATE INDEX IF NOT EXISTS ix_ml_alert_feedback_alert_id ON ml_alert_feedback(alert_id)",
        "CREATE INDEX IF NOT EXISTS ix_ml_alert_feedback_device_id ON ml_alert_feedback(device_id)",
        "CREATE INDEX IF NOT EXISTS ix_ml_alert_feedback_operator_id ON ml_alert_feedback(operator_id)",
    ]
    for statement in statements:
        db.execute(text(statement))
    db.commit()


def _ensure_logical_relationship_constraints(db) -> None:
    statements = []
    for statement in statements:
        db.execute(text(statement))
    db.commit()




