# Archivo de modelos ML

Esta carpeta conserva artefactos historicos o descartados. No forma parte de la ejecucion automatica.

## Carpetas

- `legacy/`: artefactos heredados o incompatibles que se mantienen por trazabilidad.
- `rejected/`: candidatos descartados durante revision manual.

## Reglas

- Produccion solo debe cargar `active.joblib`.
- Evaluacion previa puede usar `candidate.joblib`.
- Los artefactos archivados no deben cargarse automaticamente.
- No mover archivos `joblib` dentro de `backend/app/modules/ml_analysis/`.
- No eliminar artefactos archivados sin una decision explicita de retencion.
