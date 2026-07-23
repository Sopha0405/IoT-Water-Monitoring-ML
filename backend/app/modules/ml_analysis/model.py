from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base
from app.modules.ml_analysis.schemas import ModelStatus

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).resolve().parents[3] / "models" / "ml_analysis"
ACTIVE_MODEL_PATH = MODEL_DIR / "active.joblib"
ARCHIVE_DIR = MODEL_DIR / "archive"
METADATA_PATH = MODEL_DIR / "metadata.json"


class MLAnalysis(Base):
    """Modelo ORM para registrar resultados de analisis ML."""

    __tablename__ = "ml_analysis"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    alert_id: Mapped[int | None] = mapped_column(ForeignKey("alerts.id"), index=True, nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    floor: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    observed_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    anomaly_score: Mapped[float] = mapped_column(Float, nullable=False)
    prediction: Mapped[str] = mapped_column(String(120), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    processed_at: Mapped[object] = mapped_column(DateTime(timezone=False), server_default=func.now(), nullable=False)


class ModelManager:
    """Administra version activa, promocion y rollback del modelo."""

    def __init__(self, model_dir: Path = MODEL_DIR) -> None:
        """Prepara rutas de modelos y metadatos."""
        self.model_dir = model_dir
        self.active_path = model_dir / "active.joblib"
        self.archive_dir = model_dir / "archive"
        self.metadata_path = model_dir / "metadata.json"
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def set_active(self, new_model: str | Path, metrics_new: dict[str, float], metrics_current: dict[str, float]) -> bool:
        """Promueve un modelo si mejora F1 al menos 0.02 y mantiene FPR <= 0.05."""
        f1_new = float(metrics_new.get("f1", 0.0))
        f1_current = float(metrics_current.get("f1", 0.0))
        fpr_new = float(metrics_new.get("fpr", 1.0))
        if not (f1_new >= f1_current + 0.02 and fpr_new <= 0.05):
            logger.info("Modelo rechazado: f1_new=%s f1_current=%s fpr_new=%s", f1_new, f1_current, fpr_new)
            return False

        if self.active_path.exists():
            archive_path = self.archive_dir / f"model_{datetime.utcnow():%Y%m%d%H%M%S}_{uuid4().hex[:8]}.joblib"
            shutil.copy2(self.active_path, archive_path)
        shutil.copy2(new_model, self.active_path)
        metadata = {
            "active_version": uuid4().hex,
            "metrics": metrics_new,
            "trained_at": datetime.utcnow().isoformat(),
            "model_path": str(self.active_path),
        }
        self._write_metadata(metadata)
        self._cleanup_archive()
        return True

    def rollback(self) -> bool:
        """Restaura la version archivada mas reciente si existe."""
        archived = sorted(self.archive_dir.glob("*.joblib"), key=lambda path: path.stat().st_mtime, reverse=True)
        if not archived:
            return False
        if self.active_path.exists():
            shutil.copy2(self.active_path, self.archive_dir / f"rollback_from_{datetime.utcnow():%Y%m%d%H%M%S}.joblib")
        shutil.copy2(archived[0], self.active_path)
        metadata = self._read_metadata()
        metadata.update(
            {
                "active_version": f"rollback-{archived[0].stem}",
                "trained_at": datetime.utcnow().isoformat(),
                "model_path": str(self.active_path),
            }
        )
        self._write_metadata(metadata)
        return True

    def get_status(self) -> ModelStatus:
        """Retorna version activa, metricas y fecha de entrenamiento."""
        metadata = self._read_metadata()
        trained_at = metadata.get("trained_at")
        return ModelStatus(
            active_version=metadata.get("active_version"),
            metrics=metadata.get("metrics", {}),
            trained_at=datetime.fromisoformat(trained_at) if trained_at else None,
            model_path=metadata.get("model_path") if self.active_path.exists() else None,
        )

    def _read_metadata(self) -> dict:
        """Lee metadatos del modelo activo."""
        if not self.metadata_path.exists():
            return {"active_version": None, "metrics": {}, "trained_at": None, "model_path": None}
        return json.loads(self.metadata_path.read_text(encoding="utf-8"))

    def _write_metadata(self, metadata: dict) -> None:
        """Guarda metadatos del modelo activo."""
        self.metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    def _cleanup_archive(self) -> None:
        """Elimina archivos de rollback con mas de 30 dias."""
        cutoff = datetime.utcnow() - timedelta(days=30)
        for path in self.archive_dir.glob("*.joblib"):
            if datetime.utcfromtimestamp(path.stat().st_mtime) < cutoff:
                path.unlink(missing_ok=True)
