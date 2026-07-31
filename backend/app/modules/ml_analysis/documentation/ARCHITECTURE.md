# Arquitectura del modulo ML Analysis

Este modulo implementa el ciclo de vida completo del modelo de deteccion de anomalias de consumo de agua. La organizacion actual separa responsabilidades para evitar que entrenamiento, inferencia, flujo streaming, API, feedback y preparacion de datos queden mezclados.

## Estructura

```text
backend/app/modules/ml_analysis/
  api/              Rutas FastAPI y schemas publicos.
  alerts/           Politica temporal de alertas.
  cli/              Entrypoints pequenos para ejecutar con python -m.
  data/             IO, auditoria, limpieza, Gold y split temporal.
  documentation/    Documentacion operativa y tecnica.
  features/         Constantes, referencias temporales y extractor oficial.
  feedback/         Modelo SQLAlchemy, schemas, servicio, router y exportador de feedback.
  inference/        Artefacto del modelo, carga segura e inferencia en ejecucion.
  streaming/        Tipos MQTT, buffer, validacion, ventanas y estado temporal.
  training/         Entrenamiento, optimizacion de threshold, evaluacion y promocion.
```

## Flujo de entrenamiento

El entrenamiento es manual y corre dentro del contenedor `backend`.

1. `data.audit` revisa el CSV raw y genera un reporte de calidad.
2. `data.preparation` normaliza columnas, elimina lecturas invalidas y conserva casos utiles para evaluacion.
3. `data.gold` agrupa lecturas en ventanas de 5 minutos y calcula las 24 features oficiales.
4. `data.split` hace split temporal 70/15/15 por sensor, cuidando que eventos completos no se mezclen entre particiones.
5. `training.trainer` entrena Isolation Forest solo con normalidad limpia de train.
6. `training.threshold_optimizer` selecciona hiperparametros y threshold usando validacion.
7. El candidato se guarda en `candidate.joblib` solo si validacion cumple las restricciones.
8. `training.evaluator` evalua prueba una vez, recalculando metricas sobre scores de prueba.
9. `training.promotion` promueve manualmente solo con `--confirm` y `--test-report` valido.

## Flujo de inferencia streaming

1. MQTT entrega lecturas cada 5 segundos.
2. `streaming.types` parsea el payload.
3. `streaming.validator` descarta lecturas invalidas, duplicadas, fuera de secuencia o con error tecnico.
4. `streaming.buffer` conserva hasta 360 lecturas por sensor.
5. `streaming.window_manager` cierra ventanas completas de 60 lecturas.
6. `features.extractor.extract_features` calcula las mismas 24 features que se usan offline.
7. `inference.model_artifact` valida `active.joblib`, aplica scaler/modelo/threshold y devuelve prediccion.
8. `alerts.policy` aplica reglas temporales para reducir falsas alertas.
9. `inference.service` persiste `MLAnalysis` y crea alertas operativas cuando corresponde.

## Flujo de feedback

El feedback de operador se recibe por `feedback.router`, se valida con `feedback.schemas`, se actualiza con `feedback.service` y se persiste en `feedback.model`.

Solo feedback `approved_for_training` puede exportarse. Los `false_positive` confirmados pueden alimentar normalidad dificil. Los `true_positive` y `false_negative` se conservan para evaluacion y mejora de reglas, no como normalidad de Isolation Forest.

## Modelo y artefacto

El artefacto oficial es un `joblib` con:

- `model`: Isolation Forest entrenado.
- `scaler`: `StandardScaler` ajustado en train.
- `threshold`: umbral seleccionado con validacion.
- `feature_names`: lista exacta de 24 features.
- `feature_schema_version`: `water-flow-24f-1`.
- `metrics`: metricas de validacion.
- `dataset_hashes`: hashes de entrenamiento/validacion.
- metadata tecnica de ejecucion.

La inferencia usa la regla:

```text
score < threshold => anomaly
score >= threshold => normal
```

`active.joblib` solo cambia con promocion manual. Entrenar o evaluar no modifica el modelo activo.
