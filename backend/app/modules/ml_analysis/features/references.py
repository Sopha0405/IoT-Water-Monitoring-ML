from __future__ import annotations

from typing import Any


def expected_hourly_flow(reference: dict[str, Any], hour: int) -> float:
    hourly = reference.get("hourly_mean_lpm")
    if not isinstance(hourly, dict):
        return 0.0
    return float(hourly.get(str(hour), 0.0))


def validate_reference(reference: dict[str, Any] | None) -> dict[str, Any]:
    return reference or {}

