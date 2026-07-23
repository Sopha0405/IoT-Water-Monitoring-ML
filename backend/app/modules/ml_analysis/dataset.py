from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from app.modules.ml_analysis.features import FEATURE_NAMES, extract_features

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {
    "timestamp",
    "sensor_id",
    "zona",
    "piso",
    "caudal_lpm",
    "volumen_intervalo_l",
    "volumen_acumulado_dia_m3",
    "pulsos",
    "estado",
}

WINDOW_SIZE = 60
SAMPLE_SECONDS = 5


@dataclass(frozen=True)
class DataQualityReport:
    source_file: str
    original_rows: int
    valid_rows: int
    removed_duplicates: int
    removed_invalid_rows: int
    sensors: list[str]
    start_at: str | None
    end_at: str | None
    expected_sample_seconds: int


def load_and_validate_csv(path: str | Path) -> tuple[pd.DataFrame, DataQualityReport]:
    """Carga, limpia y valida un CSV de telemetría cruda."""
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"No existe el dataset: {source}")

    frame = pd.read_csv(source)
    original_rows = len(frame)

    missing_columns = REQUIRED_COLUMNS.difference(frame.columns)
    if missing_columns:
        raise ValueError(
            "Faltan columnas obligatorias: "
            + ", ".join(sorted(missing_columns))
        )

    frame = frame.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame["caudal_lpm"] = pd.to_numeric(frame["caudal_lpm"], errors="coerce")
    frame["volumen_intervalo_l"] = pd.to_numeric(
        frame["volumen_intervalo_l"], errors="coerce"
    )
    frame["volumen_acumulado_dia_m3"] = pd.to_numeric(
        frame["volumen_acumulado_dia_m3"], errors="coerce"
    )
    frame["sensor_id"] = frame["sensor_id"].astype("string").str.strip()
    frame["estado"] = frame["estado"].astype("string").str.strip().str.lower()

    duplicates = frame.duplicated(
        subset=["timestamp", "sensor_id"], keep="first"
    )
    removed_duplicates = int(duplicates.sum())
    frame = frame.loc[~duplicates].copy()

    valid_mask = (
        frame["timestamp"].notna()
        & frame["sensor_id"].notna()
        & frame["sensor_id"].ne("")
        & frame["caudal_lpm"].notna()
        & np.isfinite(frame["caudal_lpm"])
        & frame["caudal_lpm"].ge(0)
        & frame["volumen_intervalo_l"].notna()
        & frame["volumen_acumulado_dia_m3"].notna()
        & frame["estado"].eq("activo")
    )

    before_invalid_filter = len(frame)
    frame = frame.loc[valid_mask].copy()
    removed_invalid_rows = before_invalid_filter - len(frame)

    frame.sort_values(["sensor_id", "timestamp"], inplace=True)
    frame.reset_index(drop=True, inplace=True)

    report = DataQualityReport(
        source_file=str(source),
        original_rows=original_rows,
        valid_rows=len(frame),
        removed_duplicates=removed_duplicates,
        removed_invalid_rows=removed_invalid_rows,
        sensors=sorted(frame["sensor_id"].dropna().astype(str).unique().tolist()),
        start_at=(
            frame["timestamp"].min().isoformat()
            if not frame.empty
            else None
        ),
        end_at=(
            frame["timestamp"].max().isoformat()
            if not frame.empty
            else None
        ),
        expected_sample_seconds=SAMPLE_SECONDS,
    )
    return frame, report


def build_daily_baseline(normal_frame: pd.DataFrame) -> pd.Series:
    """
    Calcula el volumen acumulado diario histórico esperado por minuto del día.

    La serie resultante usa minute_of_day como índice y la mediana histórica
    de volumen_acumulado_dia_m3 como valor.
    """
    baseline_frame = normal_frame.copy()
    baseline_frame["minute_of_day"] = (
        baseline_frame["timestamp"].dt.hour * 60
        + baseline_frame["timestamp"].dt.minute
    )
    return baseline_frame.groupby("minute_of_day")[
        "volumen_acumulado_dia_m3"
    ].median()


def _validate_window(window: pd.DataFrame) -> bool:
    """Comprueba tamaño, sensor único e intervalo regular de cinco segundos."""
    if len(window) != WINDOW_SIZE:
        return False
    if window["sensor_id"].nunique() != 1:
        return False

    differences = window["timestamp"].diff().dropna().dt.total_seconds()
    return bool((differences == SAMPLE_SECONDS).all())


def create_feature_dataset(
    frame: pd.DataFrame,
    label: int,
    label_name: str,
    daily_baseline: pd.Series,
) -> pd.DataFrame:
    """
    Convierte telemetría cruda en ventanas no solapadas de 60 lecturas.

    label:
    - 0: normal
    - 1: anomalía
    """
    rows: list[dict[str, object]] = []

    for sensor_id, sensor_frame in frame.groupby("sensor_id", sort=False):
        sensor_frame = sensor_frame.sort_values("timestamp").reset_index(drop=True)

        for start in range(0, len(sensor_frame) - WINDOW_SIZE + 1, WINDOW_SIZE):
            window = sensor_frame.iloc[start : start + WINDOW_SIZE]
            if not _validate_window(window):
                continue

            window_end = window.iloc[-1]
            timestamp = window_end["timestamp"]
            minute_of_day = int(timestamp.hour * 60 + timestamp.minute)

            expected_daily_volume = float(
                daily_baseline.get(
                    minute_of_day,
                    daily_baseline.median() if not daily_baseline.empty else 0.0,
                )
            )
            current_daily_volume = float(
                window_end["volumen_acumulado_dia_m3"]
            )
            delta_v_dia = current_daily_volume - expected_daily_volume

            features = extract_features(
                readings=window["caudal_lpm"].to_numpy(dtype=float),
                sensor_id=str(sensor_id),
                context={
                    "timestamp": timestamp.to_pydatetime(),
                    "sample_seconds": SAMPLE_SECONDS,
                    "delta_v_dia": delta_v_dia,
                    "r_hora": timestamp.hour,
                },
            )[0]

            row: dict[str, object] = {
                "window_start": window.iloc[0]["timestamp"],
                "window_end": timestamp,
                "sensor_id": str(sensor_id),
                "zona": str(window_end["zona"]),
                "piso": str(window_end["piso"]),
                **dict(zip(FEATURE_NAMES, features)),
                "label": int(label),
                "label_name": label_name,
            }
            rows.append(row)

    return pd.DataFrame(rows)


def generate_processed_dataset(
    normal_csv: str | Path,
    anomaly_csv: str | Path,
    output_csv: str | Path,
    quality_report_path: str | Path | None = None,
) -> pd.DataFrame:
    """Genera un único dataset de features con clases normal y anomalía."""
    normal_frame, normal_report = load_and_validate_csv(normal_csv)
    anomaly_frame, anomaly_report = load_and_validate_csv(anomaly_csv)

    baseline = build_daily_baseline(normal_frame)

    normal_features = create_feature_dataset(
        normal_frame,
        label=0,
        label_name="normal",
        daily_baseline=baseline,
    )
    anomaly_features = create_feature_dataset(
        anomaly_frame,
        label=1,
        label_name="anomaly",
        daily_baseline=baseline,
    )

    processed = pd.concat(
        [normal_features, anomaly_features],
        ignore_index=True,
    )
    processed.sort_values(
        ["window_end", "label", "sensor_id"],
        inplace=True,
    )
    processed.reset_index(drop=True, inplace=True)

    target = Path(output_csv)
    target.parent.mkdir(parents=True, exist_ok=True)
    processed.to_csv(target, index=False)

    if quality_report_path is not None:
        report_target = Path(quality_report_path)
        report_target.parent.mkdir(parents=True, exist_ok=True)
        report_target.write_text(
            json.dumps(
                {
                    "normal": asdict(normal_report),
                    "anomaly": asdict(anomaly_report),
                    "window_size": WINDOW_SIZE,
                    "sample_seconds": SAMPLE_SECONDS,
                    "generated_windows": {
                        "normal": len(normal_features),
                        "anomaly": len(anomaly_features),
                        "total": len(processed),
                    },
                    "feature_names": FEATURE_NAMES,
                    "output_file": str(target),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    logger.info(
        "Dataset procesado generado en %s con %s ventanas",
        target,
        len(processed),
    )
    return processed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ETL de telemetría para el modelo Isolation Forest"
    )
    parser.add_argument("--normal", required=True, help="Ruta del CSV normal")
    parser.add_argument("--anomalies", required=True, help="Ruta del CSV de anomalías")
    parser.add_argument(
        "--output",
        default="backend/data/processed/pm04_features_v1.csv",
        help="Ruta del CSV procesado",
    )
    parser.add_argument(
        "--report",
        default="backend/data/processed/pm04_quality_report_v1.json",
        help="Ruta del reporte de calidad",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    dataset = generate_processed_dataset(
        normal_csv=args.normal,
        anomaly_csv=args.anomalies,
        output_csv=args.output,
        quality_report_path=args.report,
    )

    print(
        json.dumps(
            {
                "rows": len(dataset),
                "normal_windows": int((dataset["label"] == 0).sum()),
                "anomaly_windows": int((dataset["label"] == 1).sum()),
                "output": args.output,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
