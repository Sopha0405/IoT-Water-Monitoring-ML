# IoT Water Monitoring

Smart water consumption monitoring system using IoT, MQTT, InfluxDB, Postgres, FastAPI and React.

## Real System Flow

FS300A Sensor -> ESP32 -> MQTT -> InfluxDB -> Python + ML -> PostgreSQL -> React dashboard.

InfluxDB stores raw time-series telemetry. PostgreSQL stores processed domain data such as users, roles, devices, alerts and ML analysis results.

## Quick start

1. Copy `.env.example` to `.env` and replace every `change_me` value.
2. Start the stack:

```bash
docker compose up -d --build
```

3. Open the API health check at `http://localhost:8000/health`.
4. Start the frontend during development:

```bash
cd frontend
npm start
```

The React app expects the API at `http://localhost:8000`. Override it with `REACT_APP_API_BASE` if needed.

On first startup the backend creates default roles, an initial admin user from `INITIAL_ADMIN_*` environment variables, and demo users/devices/alerts for the dashboard.

Demo access:

- `admin@corp.com` / `admin123`
- `ana@corp.com` / `ana12345`
- `carlos@corp.com` / `carlos123`

Telemetry is read from InfluxDB when available; if InfluxDB is empty or unavailable, the API returns demo flow data so the charts still render.

The IA module uses Isolation Forest only. `POST /api/v1/ml-analysis/run` reads recent telemetry, trains the anomaly detector separately per floor, stores every model result as a saved prediction (`normal` or `anomaly`), and creates alerts only when the model detects an anomaly.

MQTT source mapping:

- PB: Wokwi ESP32 publishes to `broker.hivemq.com`.
- Piso 1: Python simulator publishes to `broker.hivemq.com`.
- Piso 3: Python simulator publishes to `broker.hivemq.com`.

`water-ingestor` subscribes to `water/flow/+/+/telemetry` on HiveMQ and writes every matching message to InfluxDB.

## Main API Areas

- `POST /api/v1/auth/login`
- `GET /api/v1/roles/`
- `GET /api/v1/users/me`
- `GET /api/v1/users/`
- `GET /api/v1/devices/`
- `POST /api/v1/devices/`
- `GET /api/v1/alerts/`
- `PATCH /api/v1/alerts/{alert_id}/attend`
- `GET /api/v1/ml-analysis/`
- `POST /api/v1/ml-analysis/run`
- `GET /api/v1/telemetry/latest`
- `GET /api/v1/telemetry/series`
