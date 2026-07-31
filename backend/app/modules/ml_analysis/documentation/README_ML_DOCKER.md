# Ejecucion del ciclo de vida ML con Docker

Todos los comandos se ejecutan dentro del contenedor `backend`.

## Preparar el entorno

```bash
docker compose build --pull=false backend
docker compose up -d --force-recreate backend
```

## 1. Auditar dataset raw

Entrada: CSV historico sin modificar.

Salida: reporte de calidad con columnas, fechas, sensores, duplicados, intervalos irregulares, errores tecnicos, distribucion de caudal y conteo de eventos.

```bash
docker compose exec backend python -m app.modules.ml_analysis.cli.audit_dataset \
  --input /app/data/raw/dataset_sensor_pb_augmented_2026-07-28_2026-10-25.csv \
  --report /app/data/processed/ml/audit_report.json
```

## 2. Preparar lecturas limpias

Normaliza columnas y excluye lecturas no aptas: timestamps invalidos, sensor vacio, caudal negativo, duplicados, intervalos irregulares, errores tecnicos y mantenimiento.

```bash
docker compose exec backend python -m app.modules.ml_analysis.cli.prepare_dataset \
  --input /app/data/raw/dataset_sensor_pb_augmented_2026-07-28_2026-10-25.csv \
  --output /app/data/processed/ml/readings_clean.parquet \
  --report-output /app/data/processed/ml/cleaning_report.json
```

## 3. Construir dataset Gold de ventanas

Agrupa lecturas limpias por sensor y ventanas de 5 minutos. Cada ventana valida tiene 60 lecturas de 5 segundos y no cruza cambio de dia.

```bash
docker compose exec backend python -m app.modules.ml_analysis.cli.build_gold \
  --input /app/data/processed/ml/readings_clean.parquet \
  --output /app/data/processed/ml/windows_gold.parquet \
  --report-output /app/data/processed/ml/gold_report.json
```

## 4. Split temporal

Divide por sensor en entrenamiento, validacion y prueba con proporciones 70/15/15. Los eventos con `event_id` se mantienen juntos para no filtrar informacion entre particiones.

```bash
docker compose exec backend python -m app.modules.ml_analysis.cli.temporal_split \
  --input /app/data/processed/ml/windows_gold.parquet \
  --output-dir /app/data/processed/ml/splits
```

## 5. Entrenar candidato

Entrena Isolation Forest solo con normalidad limpia de entrenamiento. Validacion se usa para elegir hiperparametros y threshold. Prueba no se usa para seleccion.

```bash
docker compose exec backend python -m app.modules.ml_analysis.cli.train \
  --train /app/data/processed/ml/splits/train.parquet \
  --validation /app/data/processed/ml/splits/validation.parquet \
  --output /app/app/models/ml_analysis/candidate.joblib \
  --report-output /app/data/evaluation/ml/training_report.json
```

## 6. Evaluar prueba

Evalua una vez el candidato contra la particion de prueba. Recalcula PR-AUC y ROC-AUC con `-decision_score` de prueba y separa `validation_metrics` de `test_metrics`.

```bash
docker compose exec backend python -m app.modules.ml_analysis.cli.evaluate_test \
  --model /app/app/models/ml_analysis/candidate.joblib \
  --test /app/data/processed/ml/splits/test.parquet \
  --predictions-output /app/data/evaluation/ml/test_predictions.parquet \
  --report-output /app/data/evaluation/ml/test_report.json
```

## 7. Promover manualmente

Solo se promueve con confirmacion explicita y reporte de prueba valido. La promocion valida hash del modelo, schema de features, threshold, metricas de prueba y que la particion de prueba no haya sido usada para seleccion.

```bash
docker compose exec backend python -m app.modules.ml_analysis.cli.promote_model \
  --candidate /app/app/models/ml_analysis/candidate.joblib \
  --active /app/app/models/ml_analysis/active.joblib \
  --archive-dir /app/app/models/ml_analysis/archive \
  --test-report /app/data/evaluation/ml/test_report.json \
  --confirm
```

## 8. Rollback

```bash
docker compose exec backend python -m app.modules.ml_analysis.cli.promote_model \
  --active /app/app/models/ml_analysis/active.joblib \
  --archive-dir /app/app/models/ml_analysis/archive \
  --rollback
```

## 9. Exportar feedback aprobado

```bash
docker compose exec backend python -m app.modules.ml_analysis.cli.export_feedback \
  --output /app/data/processed/ml/feedback_approved.parquet \
  --report-output /app/data/processed/ml/feedback_export_report.json
```

## 10. Validar aplicacion

```bash
docker compose exec backend pytest -q
docker compose exec backend python -c "import app.main"
```

## Reglas de seguridad

- No sobrescribir datos raw.
- No promover sin `--confirm`.
- No promover sin `--test-report`.
- No modificar `active.joblib` durante auditoria, preparacion, Gold, split, entrenamiento ni prueba.
- No reentrenar automaticamente desde feedback.
