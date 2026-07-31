from __future__ import annotations

import importlib
from pathlib import Path


def test_app_main_imports() -> None:
    importlib.import_module("app.main")


def test_tests_use_layered_ml_imports() -> None:
    root = Path(__file__).resolve().parents[2]
    forbidden = [
        "app.modules.ml_analysis.stream_buffer",
        "app.modules.ml_analysis.stream_types",
        "app.modules.ml_analysis.stream_validator",
        "app.modules.ml_analysis.window_manager",
        "app.modules.ml_analysis.temporal_state",
        "app.modules.ml_analysis.alert_policy",
        "app.modules.ml_analysis.data_io",
        "app.modules.ml_analysis.evaluate_test",
        "app.modules.ml_analysis.promote_model",
        "app.modules.ml_analysis.threshold_optimizer",
    ]
    offenders = []
    for path in root.rglob("test_*.py"):
        if path == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                offenders.append(f"{path}:{token}")
    assert offenders == []
