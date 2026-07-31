from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from app.modules.ml_analysis.data.io import read_dataframe, write_json


def analyze_feedback(input_path: str, report_output: str) -> dict:
    frame = read_dataframe(input_path)
    false_positives = int(frame["operator_label"].eq("false_positive").sum()) if "operator_label" in frame else 0
    true_positives = int(frame["operator_label"].eq("true_positive").sum()) if "operator_label" in frame else 0
    approved = int(len(frame))
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": input_path,
        "approved_feedbacks": approved,
        "false_positives": false_positives,
        "confirmed_anomalies": true_positives,
        "retraining_recommended": approved >= 100 or false_positives >= 30 or true_positives >= 20,
        "automatic_retraining_executed": False,
        "policy": {
            "false_positive": "agregar como normal dificil para Isolation Forest",
            "true_positive": "reservar para evaluacion y futuro modelo supervisado",
            "false_negative": "usar para diseno de features y evaluacion",
            "sensor_error": "excluir",
            "maintenance": "excluir",
            "unknown": "excluir",
        },
    }
    write_json(report_output, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Analiza feedback; no reentrena automaticamente")
    parser.add_argument("--input", default="/app/data/processed/ml/feedback_approved.parquet")
    parser.add_argument("--report-output", default="/app/data/processed/ml/retrain_feedback_recommendation.json")
    args = parser.parse_args()
    report = analyze_feedback(args.input, args.report_output)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()




