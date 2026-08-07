"""rebuild formal physical schema and seed defense data

Revision ID: 20260804_0004
Revises: 20260804_0003
Create Date: 2026-08-04
"""

from alembic import op


revision = "20260804_0004"
down_revision = "20260804_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS ml_alert_feedback CASCADE;
        DROP TABLE IF EXISTS alerts CASCADE;
        DROP TABLE IF EXISTS ml_analysis CASCADE;
        DROP TABLE IF EXISTS devices CASCADE;
        DROP TABLE IF EXISTS users CASCADE;
        DROP TABLE IF EXISTS floors CASCADE;
        DROP TABLE IF EXISTS roles CASCADE;

        CREATE TABLE roles (
            id SERIAL PRIMARY KEY,
            name VARCHAR(80) NOT NULL UNIQUE,
            description TEXT
        );

        CREATE TABLE floors (
            id SERIAL PRIMARY KEY,
            code VARCHAR(20) NOT NULL UNIQUE,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        );

        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(120) NOT NULL,
            email VARCHAR(180) NOT NULL UNIQUE,
            password TEXT NOT NULL,
            phone VARCHAR(40),
            floor_id INTEGER REFERENCES floors(id),
            floor VARCHAR(40),
            limit_to_floor BOOLEAN NOT NULL DEFAULT FALSE,
            role_id INTEGER NOT NULL REFERENCES roles(id),
            is_active BOOLEAN NOT NULL DEFAULT TRUE
        );

        CREATE TABLE devices (
            id SERIAL PRIMARY KEY,
            device_id VARCHAR(80) NOT NULL UNIQUE,
            floor_id INTEGER REFERENCES floors(id),
            floor VARCHAR(40),
            location VARCHAR(160),
            sensor_type VARCHAR(40) NOT NULL,
            status VARCHAR(40) NOT NULL,
            last_calibration TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE ml_analysis (
            id SERIAL PRIMARY KEY,
            alert_id INTEGER,
            device_id INTEGER NOT NULL REFERENCES devices(id),
            observed_value DOUBLE PRECISION,
            model_name VARCHAR(120) NOT NULL,
            model_version VARCHAR(50),
            anomaly_score DOUBLE PRECISION NOT NULL,
            prediction BOOLEAN NOT NULL,
            confidence DOUBLE PRECISION,
            processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE alerts (
            id SERIAL PRIMARY KEY,
            device_id INTEGER NOT NULL REFERENCES devices(id),
            ml_analysis_id INTEGER UNIQUE REFERENCES ml_analysis(id),
            attended_by INTEGER REFERENCES users(id),
            anomaly_type VARCHAR(80) NOT NULL,
            severity VARCHAR(40) NOT NULL,
            risk_percentage DOUBLE PRECISION,
            status VARCHAR(40) NOT NULL,
            description TEXT,
            detected_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            attended_at TIMESTAMP
        );

        ALTER TABLE ml_analysis
            ADD CONSTRAINT fk_ml_analysis_alert_id_alerts
            FOREIGN KEY (alert_id) REFERENCES alerts(id);

        CREATE TABLE ml_alert_feedback (
            id SERIAL PRIMARY KEY,
            alert_id INTEGER NOT NULL REFERENCES alerts(id),
            device_id INTEGER NOT NULL REFERENCES devices(id),
            operator_id INTEGER NOT NULL REFERENCES users(id),
            model_version VARCHAR(50),
            feature_schema_version VARCHAR(50),
            prediction_score DOUBLE PRECISION,
            decision_threshold DOUBLE PRECISION,
            predicted_anomaly BOOLEAN,
            operator_label VARCHAR(80),
            operator_event_type VARCHAR(80),
            feedback_status VARCHAR(40),
            notes TEXT,
            reviewed_at TIMESTAMP,
            window_start TIMESTAMP,
            window_end TIMESTAMP
        );

        CREATE INDEX ix_users_floor_id ON users(floor_id);
        CREATE INDEX ix_users_role_id ON users(role_id);
        CREATE INDEX ix_users_limit_to_floor ON users(limit_to_floor);
        CREATE INDEX ix_devices_floor_id ON devices(floor_id);
        CREATE INDEX ix_ml_analysis_device_id ON ml_analysis(device_id);
        CREATE INDEX ix_alerts_device_id ON alerts(device_id);
        CREATE INDEX ix_alerts_status ON alerts(status);
        CREATE INDEX ix_feedback_alert_id ON ml_alert_feedback(alert_id);
        CREATE INDEX ix_feedback_device_id ON ml_alert_feedback(device_id);

        INSERT INTO roles (id, name, description) VALUES
            (1, 'Supervisor', 'Acceso administrativo para gestion y defensa del sistema'),
            (2, 'Tecnico', 'Operacion y atencion de alertas del sistema IoT'),
            (3, 'Administrador', 'Rol reservado para administracion global');

        INSERT INTO floors (id, code, name, description, is_active) VALUES
            (1, 'PB', 'Planta Baja', 'Medidor principal del edificio', TRUE),
            (2, 'P1', 'Piso 1', 'Zona administrativa y oficinas', TRUE),
            (3, 'P2', 'Piso 2', 'Zona operativa y salas de reunion', TRUE),
            (4, 'P3', 'Piso 3', 'Zona tecnica y mantenimiento', TRUE);

        INSERT INTO users (id, name, email, password, phone, floor_id, floor, limit_to_floor, role_id, is_active) VALUES
            (1, 'Supervisora IoT', 'admin@corp.com', '$2b$12$1Vs6ceFwSeGbC87f.pUZbOg2FrjiIgop4xaIir8RpKzg1oDAyYJl2', '+591 7000-0001', 1, 'PB', FALSE, 1, TRUE),
            (2, 'Tecnico Piso 1', 'tecnico.p1@corp.com', '$2b$12$1Vs6ceFwSeGbC87f.pUZbOg2FrjiIgop4xaIir8RpKzg1oDAyYJl2', '+591 7000-0002', 2, 'P1', TRUE, 2, TRUE),
            (3, 'Tecnico Global', 'tecnico.global@corp.com', '$2b$12$1Vs6ceFwSeGbC87f.pUZbOg2FrjiIgop4xaIir8RpKzg1oDAyYJl2', '+591 7000-0003', 3, 'P2', FALSE, 2, TRUE);

        INSERT INTO devices (id, device_id, floor_id, floor, location, sensor_type, status, last_calibration) VALUES
            (1, 'pb-main-meter', 1, 'PB', 'Sala de bombas - medidor principal', 'FS300A', 'active', '2026-01-15 09:00:00'),
            (2, 'floor1-flow-node', 2, 'P1', 'Piso 1 - pasillo norte', 'FS300A', 'active', '2026-01-15 09:30:00'),
            (3, 'floor2-flow-node', 3, 'P2', 'Piso 2 - area comun', 'FS300A', 'active', '2026-01-15 10:00:00'),
            (4, 'floor3-flow-node', 4, 'P3', 'Piso 3 - cuarto tecnico', 'FS300A', 'active', '2026-01-15 10:30:00');

        INSERT INTO ml_analysis (id, device_id, observed_value, model_name, model_version, anomaly_score, prediction, confidence, processed_at) VALUES
            (1, 2, 18.72, 'IsolationForest', 'candidate-defense-001', 0.89, TRUE, 91.5, CURRENT_TIMESTAMP - INTERVAL '25 minutes'),
            (2, 4, 0.00, 'IsolationForest', 'candidate-defense-001', 0.83, TRUE, 86.2, CURRENT_TIMESTAMP - INTERVAL '18 minutes'),
            (3, 1, 7.34, 'IsolationForest', 'active-baseline-001', 0.12, FALSE, 22.4, CURRENT_TIMESTAMP - INTERVAL '10 minutes');

        INSERT INTO alerts (id, device_id, ml_analysis_id, attended_by, anomaly_type, severity, risk_percentage, status, description, detected_at, attended_at) VALUES
            (1, 2, 1, NULL, 'microleak', 'critical', 91.5, 'pendiente', 'Alerta generada por el modelo ML: microflujo sostenido en ventana de 60 lecturas.', CURRENT_TIMESTAMP - INTERVAL '24 minutes', NULL),
            (2, 4, 2, NULL, 'sensor_error', 'warning', 86.2, 'reviewing', 'Alerta generada por el modelo ML: sensor sin caudal reportado durante la ventana.', CURRENT_TIMESTAMP - INTERVAL '17 minutes', NULL);

        UPDATE ml_analysis SET alert_id = 1 WHERE id = 1;
        UPDATE ml_analysis SET alert_id = 2 WHERE id = 2;

        INSERT INTO ml_alert_feedback (id, alert_id, device_id, operator_id, model_version, feature_schema_version, prediction_score, decision_threshold, predicted_anomaly, operator_label, operator_event_type, feedback_status, notes, reviewed_at, window_start, window_end) VALUES
            (1, 1, 2, 1, 'candidate-defense-001', 'water-flow-24f-1', 91.5, 85.0, TRUE, 'true_positive', 'microleak', 'reviewed', 'Revision de defensa: alerta valida para explicar el flujo ML.', CURRENT_TIMESTAMP - INTERVAL '12 minutes', CURRENT_TIMESTAMP - INTERVAL '30 minutes', CURRENT_TIMESTAMP - INTERVAL '25 minutes');

        SELECT setval('roles_id_seq', 3, TRUE);
        SELECT setval('floors_id_seq', 4, TRUE);
        SELECT setval('users_id_seq', 3, TRUE);
        SELECT setval('devices_id_seq', 4, TRUE);
        SELECT setval('ml_analysis_id_seq', 3, TRUE);
        SELECT setval('alerts_id_seq', 2, TRUE);
        SELECT setval('ml_alert_feedback_id_seq', 1, TRUE);
        """
    )


def downgrade() -> None:
    raise RuntimeError("Destructive formal schema rebuild cannot be downgraded safely.")
