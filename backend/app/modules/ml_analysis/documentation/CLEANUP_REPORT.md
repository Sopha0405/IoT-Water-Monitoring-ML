# Reporte de limpieza ML

## Objetivo

Consolidar el pipeline oficial de Machine Learning y eliminar codigo duplicado o no usado del modulo `ml_analysis`.

## Codigo eliminado

- Pipeline heredado de 16 features.
- Scripts experimentales antiguos.
- Aplicador inseguro de threshold.
- Envoltorios temporales de compatibilidad ubicados en la raiz de `ml_analysis`.
- Modulos de marcador sin referencias.

## Codigo conservado

- Pipeline oficial de 24 features.
- Procesamiento offline y streaming.
- Promocion manual y rollback.
- Feedback de operador.
- Modelos y archivos archivados fuera del modulo Python.

## Correcciones funcionales conservadas

- PR-AUC y ROC-AUC se calculan sobre prueba.
- `recall_by_type` excluye normales.
- Severidad se normaliza a `low`, `medium`, `high` o `none`.
- Alertas cierran por tres ventanas normales o 15 minutos de inactividad.
- Promocion exige `--test-report`.

## Validacion

- Docker build correcto.
- Backend recreado correctamente.
- Tests: `23 passed`.
- Import de FastAPI: `import app.main` correcto.
