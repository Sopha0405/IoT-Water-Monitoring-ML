# Reporte de reorganizacion del modulo ML

El modulo `ml_analysis` esta organizado por responsabilidad para que cada capa tenga una funcion clara.

## Distribucion actual

- `api/`: rutas FastAPI y schemas.
- `alerts/`: politica temporal de alertas.
- `cli/`: entrypoints ejecutables con `python -m`.
- `data/`: lectura/escritura, auditoria, limpieza, Gold y split.
- `documentation/`: documentacion tecnica y operativa.
- `features/`: constantes, referencias, funciones temporales y extractor.
- `feedback/`: modelo SQLAlchemy, schemas, servicio, router y exportador de feedback.
- `inference/`: artefacto, modelo SQLAlchemy de resultados y servicio de inferencia.
- `streaming/`: tipos, buffer, validador, estado temporal y ventanas.
- `training/`: entrenamiento, threshold, evaluacion, promocion y recomendacion desde feedback.

## Limpieza aplicada

Se eliminaron envoltorios temporales y modulos de marcador no usados dentro de la raiz de `ml_analysis`. La raiz del modulo conserva solo `__init__.py`; la logica vive en subcarpetas.

## Validacion ejecutada

- `docker compose build --pull=false backend`: correcto.
- `docker compose up -d --force-recreate backend`: correcto.
- `docker compose exec -T backend pytest -q`: `23 passed`.
- `docker compose exec -T backend python -c "import app.main"`: correcto.

## Estado de modelos

No se modifico `active.joblib`. Los artefactos archivados permanecen fuera del modulo Python en `backend/app/models/ml_analysis/archive/`.
