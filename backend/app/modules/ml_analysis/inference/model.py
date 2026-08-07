from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import joblib
from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base
from app.modules.ml_analysis.api.schemas import ModelStatus
from app.modules.ml_analysis.features.constants import FEATURE_NAMES, FEATURE_SCHEMA_VERSION, PIPELINE_VERSION
from app.modules.ml_analysis.data.io import sha256_file

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

MODEL_DIR = Path(__file__).resolve().parents[3] / "models" / "ml_analysis"
ACTIVE_MODEL_PATH = MODEL_DIR / "active.joblib"
CANDIDATE_MODEL_PATH = MODEL_DIR / "candidate.joblib"
ARCHIVE_DIR = MODEL_DIR / "archive"
METADATA_PATH = MODEL_DIR / "metadata.json"
CANDIDATE_METADATA_PATH = MODEL_DIR / "candidate_metadata.json"
EVALUATION_DIR = Path("/app/data/evaluation/ml")
TRAINING_REPORT_PATH = EVALUATION_DIR / "training_report.json"
TEST_REPORT_PATH = EVALUATION_DIR / "test_report.json"


class MLAnalysis(Base):
    __tablename__ = "ml_analysis"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    alert_id: Mapped[int | None] = mapped_column(
        ForeignKey("alerts.id", use_alter=True), index=True, nullable=True
    )
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True, nullable=False)
    observed_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    anomaly_score: Mapped[float] = mapped_column(Float, nullable=False)
    prediction: Mapped[bool] = mapped_column(nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )

    alert = relationship("Alert", back_populates="ml_analyses", foreign_keys=[alert_id])
    generated_alert = relationship("Alert", back_populates="ml_analysis", uselist=False, foreign_keys="Alert.ml_analysis_id")
    device = relationship("Device", back_populates="ml_analyses")


class ModelManager:
    """Gestiona candidato, promoción, rechazo y rollback siempre manuales."""

    def __init__(self, model_dir: Path = MODEL_DIR) -> None:
        self.model_dir = Path(model_dir)
        self.active_path = self.model_dir / "active.joblib"
        self.candidate_path = self.model_dir / "candidate.joblib"
        self.archive_dir = self.model_dir / "archive"
        self.metadata_path = self.model_dir / "metadata.json"
        self.candidate_metadata_path = self.model_dir / "candidate_metadata.json"
        self.rejected_dir = self.archive_dir / "rejected"

        for directory in [self.model_dir, self.archive_dir, self.rejected_dir]:
            directory.mkdir(parents=True, exist_ok=True)

    def register_candidate(
        self,
        candidate_path: str | Path,
        report: dict[str, Any],
    ) -> dict[str, Any]:
        """Registra el resultado del entrenamiento sin activar el modelo."""
        source = Path(candidate_path)
        if not source.exists():
            raise FileNotFoundError(f"No existe el candidato: {source}")

        # Valida que el artefacto pueda cargarse antes de publicarlo como candidato.
        from app.modules.ml_analysis.inference.isolation_forest import IsolationForestModel

        model = IsolationForestModel.load(source)
        if source.resolve() != self.candidate_path.resolve():
            self._atomic_copy(source, self.candidate_path)

        metadata = {
            "candidate_version": uuid4().hex,
            "trained_at": _iso_datetime(model.trained_at),
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "model_path": str(self.candidate_path),
            "dataset_path": report.get("dataset_path"),
            "reference_path": report.get("reference_path"),
            "metrics": report.get("metrics", {}),
            "feature_schema_version": report.get("feature_schema_version"),
            "feature_names": report.get("feature_names", []),
            "parameters": report.get("parameters", {}),
            "data_split": report.get("data_split", {}),
        }
        self._write_json_atomic(self.candidate_metadata_path, metadata)
        return metadata

    def promote_candidate(self) -> bool:
        """Promueve el candidato únicamente tras una llamada explícita."""
        if not self.candidate_path.exists():
            return False

        from app.modules.ml_analysis.inference.isolation_forest import IsolationForestModel

        candidate_model = IsolationForestModel.load(self.candidate_path)
        candidate_metadata = self._read_json(self.candidate_metadata_path)
        if not candidate_metadata:
            raise RuntimeError("Falta candidate_metadata.json")

        if self.active_path.exists():
            self._archive_active_snapshot()

        self._atomic_copy(self.candidate_path, self.active_path)
        promoted_at = datetime.now(timezone.utc).isoformat()
        active_metadata = {
            "active_version": candidate_metadata.get("candidate_version") or uuid4().hex,
            "trained_at": candidate_metadata.get("trained_at")
            or _iso_datetime(candidate_model.trained_at),
            "promoted_at": promoted_at,
            "model_path": str(self.active_path),
            "dataset_path": candidate_metadata.get("dataset_path"),
            "reference_path": candidate_metadata.get("reference_path"),
            "metrics": candidate_metadata.get("metrics", {}),
            "feature_schema_version": candidate_metadata.get(
                "feature_schema_version"
            ),
            "feature_names": candidate_metadata.get("feature_names", []),
            "parameters": candidate_metadata.get("parameters", {}),
        }
        self._write_json_atomic(self.metadata_path, active_metadata)

        self.candidate_path.unlink(missing_ok=True)
        self.candidate_metadata_path.unlink(missing_ok=True)
        logger.warning("Candidato promovido manualmente a active.joblib")
        return True

    def reject_candidate(self, reason: str) -> bool:
        """Archiva un candidato rechazado junto con la razón humana."""
        if not self.candidate_path.exists():
            return False

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        base = self.rejected_dir / f"candidate_{stamp}_{uuid4().hex[:8]}"
        target_model = base.with_suffix(".joblib")
        target_metadata = base.with_suffix(".json")

        shutil.move(str(self.candidate_path), target_model)
        metadata = self._read_json(self.candidate_metadata_path)
        metadata.update(
            {
                "rejected_at": datetime.now(timezone.utc).isoformat(),
                "rejection_reason": reason,
                "archived_model_path": str(target_model),
            }
        )
        self._write_json_atomic(target_metadata, metadata)
        self.candidate_metadata_path.unlink(missing_ok=True)
        return True

    def rollback(self) -> bool:
        """Intercambia el activo con la versión activa archivada más reciente."""
        archived = sorted(
            self.archive_dir.glob("active_*.joblib"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if not archived:
            return False

        selected = archived[0]
        selected_metadata = selected.with_suffix(".json")
        if not selected_metadata.exists():
            raise RuntimeError("La versión archivada no tiene metadatos")

        if self.active_path.exists():
            self._archive_active_snapshot(prefix="active")

        os.replace(selected, self.active_path)
        restored_metadata = self._read_json(selected_metadata)
        selected_metadata.unlink(missing_ok=True)
        restored_metadata.update(
            {
                "model_path": str(self.active_path),
                "promoted_at": datetime.now(timezone.utc).isoformat(),
                "rollback_applied": True,
            }
        )
        self._write_json_atomic(self.metadata_path, restored_metadata)
        return True

    def get_status(self) -> ModelStatus:
        active = self._read_json(self.metadata_path)
        candidate = self._read_json(self.candidate_metadata_path)
        active_metrics = active.get("metrics", {})
        candidate_metrics = candidate.get("metrics", {})

        return ModelStatus(
            active_version=active.get("active_version"),
            metrics=active_metrics,
            trained_at=_parse_datetime(active.get("trained_at")),
            promoted_at=_parse_datetime(active.get("promoted_at")),
            model_path=(str(self.active_path) if self.active_path.exists() else None),
            candidate_version=candidate.get("candidate_version"),
            candidate_metrics=candidate_metrics,
            candidate_trained_at=_parse_datetime(candidate.get("trained_at")),
            candidate_model_path=(
                str(self.candidate_path) if self.candidate_path.exists() else None
            ),
            metric_deltas=self.compare_metrics(active_metrics, candidate_metrics),
        )

    def get_model_status(self) -> dict[str, Any]:
        logger.warning(
            "Leyendo estado ML: active=%s candidate=%s metadata=%s candidate_metadata=%s",
            self.active_path,
            self.candidate_path,
            self.metadata_path,
            self.candidate_metadata_path,
        )
        active = self._model_summary(
            kind="active",
            model_path=self.active_path,
            metadata_path=self.metadata_path,
        )
        candidate = self._model_summary(
            kind="candidate",
            model_path=self.candidate_path,
            metadata_path=self.candidate_metadata_path,
        )
        has_candidate = bool(candidate and candidate.get("exists"))
        candidate_warnings = candidate.get("warnings", []) if candidate else []
        same_as_active = bool(
            active
            and candidate
            and active.get("sha256")
            and active.get("sha256") == candidate.get("sha256")
        )
        can_promote = bool(
            has_candidate
            and candidate.get("valid")
            and not candidate_warnings
            and not same_as_active
        )
        status = {
            "active": active,
            "candidate": candidate,
            "retraining_jobs": [],
            "can_promote": can_promote,
            "can_reject": bool(has_candidate and not same_as_active),
            "can_rollback": any(self.archive_dir.glob("active_*.joblib")),
        }
        logger.warning(
            "Estado ML devuelto: active=%s candidate=%s can_promote=%s can_reject=%s can_rollback=%s",
            bool(active),
            bool(candidate),
            status["can_promote"],
            status["can_reject"],
            status["can_rollback"],
        )
        return status

    def _model_summary(self, *, kind: str, model_path: Path, metadata_path: Path) -> dict[str, Any] | None:
        logger.warning("Consultando artefacto %s en %s", kind, model_path)
        exists = model_path.exists()
        logger.warning(
            "Archivos %s: model=%s metadata=%s training_report=%s test_report=%s",
            kind,
            exists,
            metadata_path.exists(),
            TRAINING_REPORT_PATH.exists(),
            TEST_REPORT_PATH.exists(),
        )
        if not exists:
            return None

        metadata = self._read_json(metadata_path) if metadata_path.exists() else {}
        if kind == "active" and not metadata:
            legacy_metadata_path = model_path.with_suffix(".metadata.json")
            metadata = self._read_json(legacy_metadata_path) if legacy_metadata_path.exists() else {}
        if kind == "candidate" and not metadata:
            metadata = self._build_candidate_metadata()

        artifact_payload: dict[str, Any] = {}
        artifact_error: str | None = None
        try:
            artifact_payload = self._load_artifact_payload(model_path)
        except Exception as exc:
            artifact_error = str(exc)
            logger.exception("No se pudo cargar joblib %s", model_path)

        sha256 = sha256_file(model_path)
        logger.warning("Hash calculado para %s: %s", model_path, sha256)
        source = {**artifact_payload, **metadata}
        metrics = _metrics_from_metadata(source)
        schema_version = source.get("schema_version") or source.get("feature_schema_version")
        pipeline_version = source.get("pipeline_version") or source.get("artifact_version")
        feature_names = source.get("feature_names") or []
        threshold = source.get("threshold")
        warnings = list(source.get("warnings") or [])
        errors: list[str] = []
        if artifact_error:
            errors.append(artifact_error)
        if schema_version != FEATURE_SCHEMA_VERSION:
            errors.append("schema_version incompatible")
            logger.warning("Schema incompatible: %s", schema_version)
        if list(feature_names) != FEATURE_NAMES or len(feature_names) != 24:
            errors.append("feature_names incompatible")
            logger.warning("Features incompatibles: count=%s", len(feature_names) if feature_names else 0)
        if pipeline_version != PIPELINE_VERSION:
            errors.append("pipeline_version incompatible")
            logger.warning("Pipeline incompatible: %s", pipeline_version)
        if threshold is None:
            errors.append("threshold ausente")
        expected_hash = source.get("sha256") or source.get("model_sha256") or source.get("candidate_sha256")
        if expected_hash and expected_hash != sha256:
            errors.append("sha256 incompatible")
            logger.warning("Hash incompatible: esperado=%s calculado=%s", expected_hash, sha256)

        return {
            "exists": True,
            "valid": not errors,
            "version": source.get("version") or source.get(f"{kind}_version") or _version_from_date(kind, source.get("trained_at") or source.get("generated_at")),
            "status": kind if not errors else "invalid",
            "algorithm": source.get("algorithm") or source.get("model_type") or "IsolationForest",
            "schema_version": schema_version,
            "pipeline_version": pipeline_version,
            "feature_count": len(feature_names) if feature_names else None,
            "threshold": threshold,
            "metrics": metrics,
            "trained_at": source.get("trained_at") or source.get("generated_at"),
            "promoted_at": source.get("promoted_at"),
            "model_path": str(model_path),
            "sha256": sha256,
            "recommendation": source.get("recommendation") or ("manual_review" if warnings or errors else "promote_candidate"),
            "warnings": warnings,
            "errors": errors,
        }

    def _build_candidate_metadata(self) -> dict[str, Any]:
        logger.warning("candidate_metadata.json ausente; intentando construir metadata desde reportes y joblib")
        test_report = self._read_json(TEST_REPORT_PATH) if TEST_REPORT_PATH.exists() else {}
        training_report = self._read_json(TRAINING_REPORT_PATH) if TRAINING_REPORT_PATH.exists() else {}
        artifact = self._load_artifact_payload(self.candidate_path)
        report = test_report or training_report
        approved = training_report.get("approved_candidate") or {}
        test_metrics = test_report.get("test_metrics") or test_report.get("window_metrics") or {}
        if test_report.get("pr_auc") is not None:
            test_metrics = {**test_metrics, "pr_auc": test_report.get("pr_auc")}
        if test_report.get("roc_auc") is not None:
            test_metrics = {**test_metrics, "roc_auc": test_report.get("roc_auc")}
        metrics = test_metrics or approved.get("metrics") or artifact.get("metrics", {})
        warnings = _candidate_warnings(test_report)
        trained_at = artifact.get("trained_at") or training_report.get("generated_at") or test_report.get("generated_at")
        sha256 = sha256_file(self.candidate_path)
        metadata = {
            "version": _version_from_date("candidate", trained_at),
            "candidate_version": _version_from_date("candidate", trained_at),
            "status": "candidate",
            "algorithm": artifact.get("model_type", "IsolationForest"),
            "schema_version": artifact.get("feature_schema_version") or report.get("feature_schema_version"),
            "feature_schema_version": artifact.get("feature_schema_version") or report.get("feature_schema_version"),
            "pipeline_version": artifact.get("artifact_version", PIPELINE_VERSION),
            "artifact_version": artifact.get("artifact_version", PIPELINE_VERSION),
            "feature_names": artifact.get("feature_names") or report.get("feature_names", []),
            "threshold": test_report.get("threshold", artifact.get("threshold") or approved.get("threshold")),
            "metrics": metrics,
            "trained_at": trained_at,
            "generated_at": test_report.get("generated_at") or training_report.get("generated_at"),
            "model_path": str(self.candidate_path),
            "sha256": sha256,
            "model_sha256": test_report.get("model_sha256") or sha256,
            "candidate_sha256": training_report.get("candidate_sha256") or sha256,
            "recommendation": "manual_review" if warnings else "promote_candidate",
            "warnings": warnings,
            "source_reports": {
                "test_report": str(TEST_REPORT_PATH) if test_report else None,
                "training_report": str(TRAINING_REPORT_PATH) if training_report else None,
            },
        }
        self._write_json_atomic(self.candidate_metadata_path, metadata)
        logger.warning("candidate_metadata.json creado en %s", self.candidate_metadata_path)
        return metadata

    @staticmethod
    def _load_artifact_payload(path: Path) -> dict[str, Any]:
        payload = joblib.load(path)
        if not isinstance(payload, dict):
            raise RuntimeError("Artefacto ML incompatible: se esperaba dict joblib")
        return payload

    @staticmethod
    def compare_metrics(
        active_metrics: dict[str, Any],
        candidate_metrics: dict[str, Any],
    ) -> dict[str, float]:
        deltas: dict[str, float] = {}
        for name in ["precision", "recall", "f1", "fpr", "latency_per_sample_ms"]:
            active_value = active_metrics.get(name)
            candidate_value = candidate_metrics.get(name)
            if isinstance(active_value, (int, float)) and isinstance(
                candidate_value, (int, float)
            ):
                deltas[name] = round(float(candidate_value - active_value), 6)
        return deltas

    def _archive_active_snapshot(self, prefix: str = "active") -> None:
        if not self.active_path.exists():
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        base = self.archive_dir / f"{prefix}_{stamp}_{uuid4().hex[:8]}"
        model_target = base.with_suffix(".joblib")
        metadata_target = base.with_suffix(".json")
        self._atomic_copy(self.active_path, model_target)
        self._write_json_atomic(metadata_target, self._read_json(self.metadata_path))

    @staticmethod
    def _atomic_copy(source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        shutil.copy2(source, temporary)
        os.replace(temporary, target)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"No se pudo leer {path}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"Metadatos inválidos en {path}")
        return payload

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(temporary, path)


def _iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed


def _metrics_from_metadata(source: dict[str, Any]) -> dict[str, Any]:
    metrics = source.get("metrics") or {}
    return {
        "precision": _number_or_none(metrics.get("precision")),
        "recall": _number_or_none(metrics.get("recall")),
        "f1": _number_or_none(metrics.get("f1")),
        "fpr": _number_or_none(metrics.get("fpr")),
        "pr_auc": _number_or_none(metrics.get("pr_auc")),
        "roc_auc": _number_or_none(metrics.get("roc_auc")),
    }


def _number_or_none(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _version_from_date(prefix: str, value: Any) -> str:
    parsed = str(value or datetime.now(timezone.utc).isoformat()).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(parsed)
    except ValueError:
        dt = datetime.now(timezone.utc)
    return f"{prefix}-{dt.strftime('%Y%m%d-%H%M%S')}"


def _candidate_warnings(test_report: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    recall_by_type = test_report.get("recall_by_type") if isinstance(test_report, dict) else {}
    if isinstance(recall_by_type, dict) and recall_by_type.get("microfuga") == 0:
        warnings.append("Microfuga recall en test = 0")
    incidents = test_report.get("incidents") if isinstance(test_report, dict) else None
    if isinstance(incidents, dict):
        precision = incidents.get("incident_precision")
        recall = incidents.get("incident_recall")
        false_per_day = incidents.get("operational_false_alerts_per_day")
        if isinstance(precision, (int, float)) and precision < 0.60:
            warnings.append("Precision por incidente menor a 0.60")
        if not isinstance(recall, (int, float)) or recall < 0 or recall > 1:
            warnings.append("Recall por incidente invalido")
        elif recall < 0.70:
            warnings.append("Recall por incidente menor a 0.70")
        if isinstance(false_per_day, (int, float)) and false_per_day > 1.0:
            warnings.append("Falsas alertas operativas por dia mayor a 1.0")
    return warnings




