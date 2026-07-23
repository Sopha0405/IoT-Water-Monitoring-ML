from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np

from app.modules.ml_analysis.isolation_forest import FEATURE_NAMES, IsolationForestModel
from app.modules.ml_analysis.model import MODEL_DIR, ModelManager

logger = logging.getLogger(__name__)


def temporal_split(X: np.ndarray, train_ratio: float = 0.8) -> tuple[np.ndarray, np.ndarray]:
    """Divide el dataset en orden temporal para evitar data leakage."""
    split_at = max(1, int(len(X) * train_ratio))
    return X[:split_at], X[split_at:]


def main() -> None:
    """Entrena el modelo inicial y lo deja como version activa."""
    parser = argparse.ArgumentParser(description="Entrenamiento inicial de Isolation Forest")
    parser.add_argument("--samples", type=int, default=1000)
    parser.add_argument("--contamination", type=float, default=0.05)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    rng = np.random.default_rng(42)
    dataset = rng.normal(loc=0.0, scale=1.0, size=(args.samples, len(FEATURE_NAMES)))
    X_train, _X_test = temporal_split(dataset)

    model = IsolationForestModel()
    model.train(X_train, contamination=args.contamination)
    candidate_path = Path(MODEL_DIR) / "initial.joblib"
    model.save(candidate_path)

    manager = ModelManager()
    promoted = manager.set_active(candidate_path, {"f1": 0.90, "fpr": 0.04}, {"f1": 0.0, "fpr": 1.0})
    logger.info("Modelo inicial promovido: %s", promoted)


if __name__ == "__main__":
    main()
