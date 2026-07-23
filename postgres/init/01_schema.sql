CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY,
    name VARCHAR(80) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    email VARCHAR(180) UNIQUE NOT NULL,
    password TEXT NOT NULL,
    phone VARCHAR(40),
    floor VARCHAR(40),
    role_id INTEGER NOT NULL REFERENCES roles(id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);
CREATE INDEX IF NOT EXISTS ix_users_floor ON users(floor);

CREATE TABLE IF NOT EXISTS devices (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(80) UNIQUE NOT NULL,
    floor VARCHAR(40),
    location VARCHAR(160),
    sensor_type VARCHAR(40) NOT NULL DEFAULT 'FS300A',
    status VARCHAR(40) NOT NULL DEFAULT 'active',
    last_calibration TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_devices_device_id ON devices(device_id);
CREATE INDEX IF NOT EXISTS ix_devices_floor ON devices(floor);

CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(80) NOT NULL,
    floor VARCHAR(40),
    anomaly_type VARCHAR(80) NOT NULL,
    severity VARCHAR(40) NOT NULL,
    risk_percentage DOUBLE PRECISION NOT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'open',
    description TEXT,
    detected_at TIMESTAMP NOT NULL DEFAULT NOW(),
    attended_by INTEGER REFERENCES users(id),
    attended_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_alerts_device_id ON alerts(device_id);
CREATE INDEX IF NOT EXISTS ix_alerts_floor ON alerts(floor);

CREATE TABLE IF NOT EXISTS ml_analysis (
    id SERIAL PRIMARY KEY,
    alert_id INTEGER REFERENCES alerts(id),
    device_id VARCHAR(80),
    floor VARCHAR(40),
    observed_value DOUBLE PRECISION,
    model_name VARCHAR(120) NOT NULL,
    anomaly_score DOUBLE PRECISION NOT NULL,
    prediction VARCHAR(120) NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_ml_analysis_alert_id ON ml_analysis(alert_id);
CREATE INDEX IF NOT EXISTS ix_ml_analysis_device_id ON ml_analysis(device_id);
CREATE INDEX IF NOT EXISTS ix_ml_analysis_floor ON ml_analysis(floor);

INSERT INTO roles (id, name) VALUES
    (1, 'Supervisor'),
    (2, 'Tecnico'),
    (3, 'Admin')
ON CONFLICT (id) DO NOTHING;
