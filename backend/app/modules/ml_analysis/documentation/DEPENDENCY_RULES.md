# Reglas de dependencias

Estas reglas evitan dependencias circulares y mezcla de responsabilidades.

## Capas permitidas

- `features` no debe depender de API, base de datos, MQTT ni entrenamiento.
- `data` puede depender de `features` y `streaming.types` para construir ventanas, pero no de FastAPI ni PostgreSQL.
- `training` puede depender de `data`, `features` e `inference` solo para formato de artefacto.
- `inference` puede depender de `features`, modelos SQLAlchemy y servicios externos de telemetria.
- `streaming` puede depender de `features`, `alerts` e `inference` desde el worker.
- `alerts` debe contener politica temporal y acumuladores, no rutas FastAPI.
- `feedback` puede depender de SQLAlchemy, Pydantic y FastAPI en archivos separados.
- `api` puede depender de servicios de inferencia, feedback y modelos SQLAlchemy.
- `cli` solo debe leer argumentos, llamar una funcion de capa y mostrar JSON.

## Reglas practicas

- No importar routers desde modelos o schemas.
- No importar `api.router` desde `api.__init__`; eso genera ciclos al cargar schemas.
- No cargar modelos archivados automaticamente.
- No modificar `active.joblib` fuera de `training.promotion`.
- No usar `event_id`, labels, scenario o columnas de auditoria como features.
- No duplicar formulas de features entre procesamiento offline y streaming.
