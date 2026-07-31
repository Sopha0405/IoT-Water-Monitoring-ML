from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import pandas as pd

from app.db.postgres import SessionLocal
from app.modules.ml_analysis.data.io import write_dataframe, write_json
from app.modules.ml_analysis.feedback.model import MLAlertFeedback


def export_feedback(output: str, report_output: str) -> dict:
    db = SessionLocal()
    try:
        rows = db.query(MLAlertFeedback).filter(MLAlertFeedback.feedback_status == "approved_for_training").all()
        data = []
        for row in rows:
            if row.operator_label in {"unknown", "sensor_error", "maintenance"}:
                continue
            export_role = {
                "false_positive": "normal_difficult",
                "true_positive": "evaluation_positive",
                "false_negative": "evaluation_miss",
            }.get(row.operator_label)
            if export_role is None:
                continue
            data.append({
                "alert_id": row.alert_id,
                "sensor_id": row.sensor_id,
                "model_version": row.model_version,
                "feature_schema_version": row.feature_schema_version,
                "prediction_score": row.prediction_score,
                "decision_threshold": row.decision_threshold,
                "predicted_anomaly": row.predicted_anomaly,
                "operator_label": row.operator_label,
                "operator_event_type": row.operator_event_type,
                "export_role": export_role,
                "baseline_train_eligible": export_role == "normal_difficult",
                "window_start": row.window_start,
                "window_end": row.window_end,
                "source_data_hash": row.source_data_hash,
            })
    finally:
        db.close()
    frame = pd.DataFrame(data)
    write_dataframe(frame, output)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output": output,
        "rows": int(len(frame)),
        "policy": "solo approved_for_training; false_positive=>normal_difficult; true_positive/false_negative solo evaluacion; exclude unknown, sensor_error y maintenance",
    }
    write_json(report_output, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Exporta feedback aprobado para revision offline")
    parser.add_argument("--output", default="/app/data/processed/ml/feedback_approved.parquet")
    parser.add_argument("--report-output", default="/app/data/processed/ml/feedback_export_report.json")
    args = parser.parse_args()
    report = export_feedback(args.output, args.report_output)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()




