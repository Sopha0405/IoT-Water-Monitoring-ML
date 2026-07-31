FEATURE_SCHEMA_VERSION = "water-flow-24f-1"
PIPELINE_VERSION = "1.0.0"
FEATURE_NAMES = [
    "mu_q", "sigma_q", "min_q", "max_q", "iqr_q", "slope_q", "v_ventana",
    "pct_tiempo_con_flujo_5min", "pct_microflujo_5min", "mediana_caudal_5min",
    "duracion_microflujo_continuo_seg", "num_arranques_5min", "caudal_promedio_30min",
    "num_ventanas_consecutivas_microflujo", "delta_v_dia", "desviacion_vs_patron_hora",
    "r_hora", "hora_sin", "hora_cos", "dia_semana", "horario_laboral",
    "mes_sin", "mes_cos", "sensor_id_enc",
]
FLOW_ACTIVE_MIN_LPM = 0.03
MICROFLOW_MAX_LPM = 0.50
WINDOW_SIZE = 60
HISTORY_SIZE = 360
SAMPLE_SECONDS = 5
DEFAULT_TIMEZONE = "America/La_Paz"