"""Engine-owned value types shared by Web Sources rules and application requests."""

from __future__ import annotations

from enum import Enum


class Confidence(str, Enum):
    DIRECT = "direct"
    LIKELY = "likely"
    UNKNOWN = "unknown"


class ImportTarget(str, Enum):
    NORMAL = "normal"
    SHINY = "shiny"
    ANIMATED = "animated"
    ITEMS = "items"
