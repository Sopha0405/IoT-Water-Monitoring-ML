# Monitoreo inteligente de agua — Sofia/Indatta

Sistema local de monitoreo de consumo y detección de anomalías con FS300A, ESP32, MQTT, InfluxDB, FastAPI, PostgreSQL, React e Isolation Forest.

## Flujo real

```text
FS300A → ESP32 → MQTT/Mosquitto → water-ingestor → InfluxDB
                                                    ↓
React ← PostgreSQL ← FastAPI ← active.joblib ← 60 lecturas
```

- El sensor publica cada 5 segundos.
- La inferencia exige exactamente 60 lecturas válidas y ordenadas: una ventana de 5 minutos.
- InfluxDB conserva telemetría cruda.
- PostgreSQL registra todas las predicciones en `ml_analysis` y crea `alerts` solo para anomalías.
- Una alerta equivalente y pendiente no se duplica durante el periodo de enfriamiento configurado.

## Metodología y datos

- **CRISP-DM** organiza comprensión, preparación, modelado, evaluación e implementación.
- La estructura **Bronze/Silver/Gold** organiza datos crudos, limpios y listos para ML.
- El entrenamiento usa solo ventanas normales.
- Las etiquetas se usan únicamente para evaluación.
- La división es temporal: el entrenamiento usa el pasado y la evaluación usa ventanas posteriores al corte.
- La referencia de `delta_v_dia` se calcula solo con el tramo normal de entrenamiento para evitar fuga de información.

## Artefactos MLOps local nivel 0

```text
backend/app/models/ml_analysis/
├── active.joblib
├── candidate.joblib
├── metadata.json
├── candidate_metadata.json
└── archive/
```

1. El reentrenamiento genera `candidate.joblib`.
2. La evaluación y la comparación de métricas son automáticas.
3. La promoción, el rechazo y el rollback requieren una acción humana explícita.
4. El entrenamiento nunca sobrescribe `active.joblib`.

## 16 features

`mu_q`, `sigma_q`, `min_q`, `max_q`, `iqr_q`, `slope_q`, `v_ventana`, `delta_v_dia`, `r_hora`, `hora_sin`, `hora_cos`, `dia_semana`, `horario_laboral`, `mes_sin`, `mes_cos`, `sensor_id_enc`.

Las variables propuestas para microfugas todavía no forman parte del contrato del modelo.

## Inicio local

1. Cree `.env` y defina al menos:

```env
POSTGRES_PASSWORD=...
INFLUX_PASSWORD=...
INFLUX_TOKEN=...
JWT_SECRET_KEY=...
DATABASE_URL=postgresql+psycopg://water_user:CLAVE@postgres:5432/water_app
```

2. Levante la infraestructura real:

```bash
docker compose up -d --build
```

3. Para incluir el simulador, use el perfil explícito:

```bash
docker compose --profile simulation up -d --build
```

## Endpoints del módulo ML

El prefijo final depende de cómo se incluya el router en FastAPI.

- `POST /analyze`: inferencia y persistencia de la predicción.
- `GET /status`: activo, candidato y diferencia de métricas.
- `POST /retrain`: genera y evalúa solamente el candidato.
- `POST /promote`: promoción manual.
- `POST /reject`: rechazo manual con motivo.
- `POST /rollback`: restauración manual de una versión archivada.
- `GET /drift`: último reporte calculado con datos productivos reales.

## Compatibilidad de modelos

Los archivos `joblib` deben generarse con la misma versión de scikit-learn utilizada por el backend. Tras cambiar dependencias, se debe reentrenar el candidato; no es recomendable reutilizar un artefacto serializado con otra versión.
