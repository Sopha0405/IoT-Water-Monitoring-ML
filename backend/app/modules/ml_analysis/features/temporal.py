from __future__ import annotations

import numpy as np


def hour_cycle(hour_decimal: float) -> tuple[float, float]:
    return (
        float(np.sin(2 * np.pi * hour_decimal / 24.0)),
        float(np.cos(2 * np.pi * hour_decimal / 24.0)),
    )


def month_cycle(month: int) -> tuple[float, float]:
    month_index = month - 1
    return (
        float(np.sin(2 * np.pi * month_index / 12.0)),
        float(np.cos(2 * np.pi * month_index / 12.0)),
    )


def is_working_hours(weekday: int, hour: int) -> float:
    return 1.0 if weekday < 5 and 7 <= hour < 19 else 0.0


def deviation_vs_expected(mean_flow: float, expected_flow: float) -> float:
    return float(mean_flow - expected_flow)

