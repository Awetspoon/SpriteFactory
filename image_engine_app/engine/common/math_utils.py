"""Numeric helpers shared across engine modules."""

from __future__ import annotations


def clamp01(value: float) -> float:
    """Clamp a float into the inclusive [0, 1] range."""

    return max(0.0, min(1.0, value))
