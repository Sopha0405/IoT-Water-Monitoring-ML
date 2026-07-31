from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import joblib

from app.modules.ml_analysis.data.io import sha256_file, write_json
from app.modules.ml_analysis.features.constants import FEATURE_NAMES, FEATURE_SCHEMA_VERSION, PIPELINE_VERSION


def promote(
    candidate: str | Path,
    active: str | Path,
    archive_dir: str | Path,
    *,
    test_report: str | Path,
    confirm: bool,
    force: bool = False,
    reason: str | None = None,
) -> dict:
    if not confirm:
        raise RuntimeError("La promocion requiere --confirm")
    if force and not reason:
        raise RuntimeError("--force requiere --reason")
    candidate_path = Path(candidate)
    active_path = Path(active)
    archive = Path(archive_dir)
    artifact = joblib.load(candidate_path)
    _validate_artifact(artifact, force=force)
    report_path = Path(test_report)
    report = _load_test_report(report_path)
    _validate_test_report(report, candidate_path, artifact, force=force)
    metrics = report.get("test_metrics") or report.get("window_metrics") or {}
    violations = []
    if metrics.get("precision", 0.0) < 0.80:
        violations.append("precision")
    if metrics.get("recall", 0.0) < 0.60:
        violations.append("recall")
    if metrics.get("fpr", 1.0) > 0.02:
        violations.append("fpr")
    if violations and not force:
        raise RuntimeError("Metricas insuficientes para promover: " + ", ".join(violations))
    archive.mkdir(parents=True, exist_ok=True)
    archived_active = None
    if active_path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archived_active = archive / f"active_{stamp}_{uuid4().hex[:8]}.joblib"
        shutil.copy2(active_path, archived_active)
    active_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(candidate_path, active_path)
    promoted_at = datetime.now(timezone.utc).isoformat()
    candidate_sha256 = sha256_file(candidate_path)
    active_sha256 = sha256_file(active_path)
    metadata = {
        "active_version": _version_from_date("active", promoted_at),
        "version": _version_from_date("active", promoted_at),
        "status": "active",
        "algorithm": artifact.get("model_type", "IsolationForest"),
        "schema_version": artifact.get("feature_schema_version"),
        "pipeline_version": artifact.get("artifact_version", PIPELINE_VERSION),
        "artifact_version": artifact.get("artifact_version", PIPELINE_VERSION),
        "feature_names": artifact.get("feature_names", FEATURE_NAMES),
        "trained_at": artifact.get("trained_at") or report.get("generated_at"),
        "promoted_at": promoted_at,
        "model_path": str(active_path),
        "sha256": active_sha256,
        "candidate": str(candidate_path),
        "candidate_sha256": candidate_sha256,
        "active": str(active_path),
        "active_sha256": active_sha256,
        "archived_previous_active": str(archived_active) if archived_active else None,
        "forced": force,
        "force_reason": reason,
        "metrics": metrics,
        "validation_metrics": artifact.get("metrics", {}),
        "test_report": str(report_path),
        "test_report_sha256": sha256_file(report_path),
        "feature_schema_version": artifact.get("feature_schema_version"),
        "threshold": artifact.get("threshold"),
    }
    write_json(active_path.parent / "metadata.json", metadata)
    write_json(active_path.with_suffix(".metadata.json"), metadata)
    candidate_path.unlink(missing_ok=True)
    (candidate_path.parent / "candidate_metadata.json").unlink(missing_ok=True)
    return metadata


def rollback(active: str | Path, archive_dir: str | Path) -> dict:
    active_path = Path(active)
    archive = Path(archive_dir)
    candidates = sorted(archive.glob("active_*.joblib"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        raise RuntimeError("No hay active archivado para rollback")
    selected = candidates[0]
    shutil.copy2(selected, active_path)
    return {"rolled_back_at": datetime.now(timezone.utc).isoformat(), "restored": str(selected), "active": str(active_path)}


def _validate_artifact(artifact: dict, *, force: bool) -> None:
    if artifact.get("feature_schema_version") != FEATURE_SCHEMA_VERSION:
        raise RuntimeError("Schema invalido")
    if artifact.get("feature_names") != FEATURE_NAMES:
        raise RuntimeError("Orden de features invalido")
    if "threshold" not in artifact:
        raise RuntimeError("El candidato no contiene threshold")
    if not artifact.get("metrics") and not force:
        raise RuntimeError("El candidato no contiene metricas")


def _load_test_report(path: Path) -> dict:
    if not path.exists():
        raise RuntimeError("--test-report es obligatorio y debe existir")
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise RuntimeError("test-report invalido")
    return payload


def _validate_test_report(report: dict, candidate_path: Path, artifact: dict, *, force: bool) -> None:
    candidate_hash = sha256_file(candidate_path)
    if report.get("model_sha256") != candidate_hash:
        raise RuntimeError("El hash del modelo no coincide con el test-report")
    if bool(report.get("test_used_for_selection")):
        raise RuntimeError("El test-report indica uso de test para seleccion")
    if report.get("threshold") != artifact.get("threshold"):
        raise RuntimeError("El threshold del reporte no coincide con el artefacto")
    if artifact.get("feature_schema_version") != FEATURE_SCHEMA_VERSION:
        raise RuntimeError("Feature schema invalido")
    metrics = report.get("test_metrics") or report.get("window_metrics") or {}
    required = {"precision", "recall", "fpr", "pr_auc", "roc_auc"}
    missing = [name for name in required if metrics.get(name) is None]
    if missing and not force:
        raise RuntimeError("Metricas test faltantes: " + ", ".join(missing))
    if report.get("validation_metrics") == metrics and not force:
        raise RuntimeError("Las metricas de test parecen copiadas de validation")


def _version_from_date(prefix: str, value: str) -> str:
    parsed = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(parsed)
    except ValueError:
        dt = datetime.now(timezone.utc)
    return f"{prefix}-{dt.strftime('%Y%m%d-%H%M%S')}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Promocion manual de candidate")
    parser.add_argument("--candidate", default="/app/app/models/ml_analysis/candidate.joblib")
    parser.add_argument("--active", default="/app/app/models/ml_analysis/active.joblib")
    parser.add_argument("--archive-dir", default="/app/app/models/ml_analysis/archive")
    parser.add_argument("--test-report", required=False)
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--reason", default=None)
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    try:
        if args.rollback:
            result = rollback(args.active, args.archive_dir)
        else:
            if not args.test_report:
                raise RuntimeError("La promocion requiere --test-report")
            result = promote(args.candidate, args.active, args.archive_dir, test_report=args.test_report, confirm=args.confirm, force=args.force, reason=args.reason)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()




