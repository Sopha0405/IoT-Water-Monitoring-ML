# Metodologia del modelo ML

## Objetivo del modelo

El modelo detecta ventanas anormales de consumo de agua a partir de lecturas de caudal (`flow_lpm`) tomadas cada 5 segundos. Cada decision se hace sobre una ventana cerrada de 5 minutos, es decir, 60 lecturas por sensor.

El enfoque principal es no supervisado: se entrena un `IsolationForest` con normalidad limpia y luego se evalua contra eventos etiquetados para seleccionar threshold, medir desempeno y decidir promocion manual.

## Unidad de analisis

- Lectura base: una muestra cada 5 segundos.
- Ventana operativa: 60 lecturas, equivalente a 5 minutos.
- Historia corta: hasta 360 lecturas, equivalente a 30 minutos.
- Zona horaria operativa: `America/La_Paz`.
- Schema oficial: `water-flow-24f-1`.
- Cantidad exacta de features: 24.

No se usan como features:

- `event_id`
- labels
- scenario
- tipo real de evento
- severidad real
- columnas de auditoria

Esas columnas solo sirven para evaluar, auditar o reportar.

## Features oficiales

Las 24 features se calculan en `features/extractor.py` y se ordenan segun `features/constants.py`.

1. `mu_q`: promedio de caudal en la ventana de 5 minutos.
2. `sigma_q`: desviacion estandar del caudal en la ventana.
3. `min_q`: caudal minimo observado.
4. `max_q`: caudal maximo observado.
5. `iqr_q`: rango intercuartil, percentil 75 menos percentil 25.
6. `slope_q`: pendiente lineal del caudal dentro de la ventana.
7. `v_ventana`: volumen estimado de la ventana en litros.
8. `pct_tiempo_con_flujo_5min`: proporcion de lecturas con flujo activo, usando `flow_lpm >= 0.03`.
9. `pct_microflujo_5min`: proporcion de lecturas entre `0.03` y `0.50` L/min.
10. `mediana_caudal_5min`: mediana del caudal de la ventana.
11. `duracion_microflujo_continuo_seg`: duracion del tramo continuo mas largo de microflujo.
12. `num_arranques_5min`: cantidad de arranques de flujo dentro de la ventana.
13. `caudal_promedio_30min`: promedio de caudal usando hasta 30 minutos de historia.
14. `num_ventanas_consecutivas_microflujo`: contador temporal de ventanas consecutivas con microflujo.
15. `delta_v_dia`: diferencia contra volumen diario esperado, provista por contexto temporal.
16. `desviacion_vs_patron_hora`: promedio de la ventana menos referencia esperada para esa hora.
17. `r_hora`: referencia horaria esperada de caudal.
18. `hora_sin`: codificacion senoidal de la hora.
19. `hora_cos`: codificacion cosenoidal de la hora.
20. `dia_semana`: dia de semana local, de 0 a 6.
21. `horario_laboral`: 1 si es lunes a viernes de 07:00 a 18:59; 0 en otro caso.
22. `mes_sin`: codificacion senoidal del mes.
23. `mes_cos`: codificacion cosenoidal del mes.
24. `sensor_id_enc`: codificacion hash estable del sensor.

## Por que estas features

El conjunto combina cinco tipos de senales:

- Estadistica de ventana: promedio, variabilidad, minimo, maximo, mediana e IQR.
- Forma temporal: pendiente, arranques y persistencia.
- Volumen: volumen de ventana y diferencia diaria.
- Contexto horario/calendario: hora, mes, dia laboral y referencia horaria.
- Identidad del sensor: codificacion estable para capturar diferencias entre sensores.

Esto permite detectar picos, fugas sostenidas, microfugas y consumos crecientes sin enviar features al ESP32 ni depender de etiquetas durante inferencia.

## Preparacion de datos

La preparacion excluye lecturas que no deben alimentar entrenamiento:

- timestamps invalidos;
- `sensor_id` faltante;
- caudal nulo, infinito o negativo;
- duplicados;
- intervalos irregulares;
- estados tecnicos de sensor;
- mantenimiento;
- estados desconocidos sospechosos con flujo alto.

Las anomalias etiquetadas y normalidad dificil se conservan para evaluacion, pero el entrenamiento del Isolation Forest usa solo normalidad limpia.

## Construccion Gold

El dataset Gold se compone de ventanas validas:

- 60 lecturas exactas;
- intervalos regulares de 5 segundos;
- mismo sensor;
- mismo dia local;
- caudales finitos;
- 24 features calculadas por el extractor oficial;
- columnas de auditoria para evaluar labels, eventos y severidad.

La misma funcion `extract_features()` se usa en Gold offline y en el flujo de streaming.

## Split temporal

El split se hace por sensor y por orden temporal:

- 70 % train;
- 15 % validacion;
- 15 % prueba.

Los grupos con `event_id` se mantienen juntos. Entrenamiento se filtra para quedarse con normalidad limpia y elegible. Validacion y prueba conservan normales, normales dificiles y anomalias etiquetadas para medir precision, recall y falsos positivos.

## Entrenamiento

Se entrena `IsolationForest` con `StandardScaler`.

El grid actual explora:

- `n_estimators`: 100, 200, 300, 500.
- `contamination`: 0.01, 0.02, 0.03, 0.04, 0.05.
- `max_samples`: `auto`, 0.70, 0.90.
- `max_features`: 0.70, 0.85, 1.00.
- `random_state`: 42.

Cada candidato se evalua en validacion. Se guarda candidato solo si cumple:

- precision en validacion >= 0.80;
- recall en validacion >= 0.60;
- FPR en validacion <= 0.02.

No hay fallback silencioso salvo que se pida explicitamente `--allow-fallback`.

## Threshold

Isolation Forest entrega `decision_score`.

La regla oficial es:

```text
decision_score < threshold => anomaly
decision_score >= threshold => normal
```

Para calcular PR-AUC y ROC-AUC se usa `anomaly_score = -decision_score`, porque mayor `anomaly_score` significa mayor anomalia.

El threshold se selecciona con validacion, no con prueba.

## Evaluacion de prueba

Prueba se usa una vez para medicion final. El reporte incluye:

- `validation_metrics`: metricas guardadas durante seleccion.
- `test_metrics`: metricas recalculadas sobre prueba.
- PR-AUC y ROC-AUC calculadas sobre prueba.
- recall por tipo, excluyendo normales.
- recall por severidad categorica.
- metricas de normales dificiles: true negatives, false positives, specificity, FPR y false-alert rate.
- agrupacion de incidentes.
- falsas alertas por dia.

## Politica de microfugas

La microfuga no se interpreta solo como caudal total bajo. Si hay consumo base superpuesto, el caudal total puede superar `0.50` L/min.

La politica combina:

- microflujo absoluto: alta proporcion de lecturas entre `0.03` y `0.50` L/min;
- desviacion persistente contra patron horario;
- baja variabilidad;
- persistencia por varias ventanas.

Esta politica se calibra con validacion y prueba no modifica reglas.

## Alertas operativas

La politica temporal puede alertar por:

- pico critico;
- microfuga;
- fuga sostenida;
- anomalia general;
- error tecnico de sensor.

Las alertas se deduplican por sensor y tipo. Una alerta abierta cierra por:

- tres ventanas normales consecutivas;
- mas de 15 minutos de inactividad;
- cierre explicito por stale/normalidad.

Una alerta cerrada puede reabrirse si aparece un nuevo evento despues del cooldown.

## Promocion

La promocion es manual y requiere:

- `--confirm`;
- `--test-report`;
- hash del modelo coincidente;
- threshold coincidente;
- schema de features oficial;
- prueba no usada para seleccion;
- precision de prueba >= 0.80;
- recall de prueba >= 0.60;
- FPR de prueba <= 0.02;
- PR-AUC y ROC-AUC presentes.

`active.joblib` no cambia durante entrenamiento ni evaluacion.
