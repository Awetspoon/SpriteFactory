"""Preset and export prediction models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ._serialization import SerializableDataclass
from .asset_record import ChromaSubsampling, EditMode, ExportFormat, ExportProfile


@dataclass
class PresetModel(SerializableDataclass):
    """Preset bundle model from the v1.0.1 schema."""

    name: str
    description: str
    applies_to_formats: list[str] = field(default_factory=lambda: ["*"])
    applies_to_tags: list[str] = field(default_factory=lambda: ["*"])
    settings_delta: dict[str, Any] = field(default_factory=dict)
    uses_heavy_tools: bool = False
    requires_apply: bool = False
    mode_min: EditMode = EditMode.SIMPLE


@dataclass
class ExportComparisonEntry(SerializableDataclass):
    """Comparison row used in export size prediction displays."""

    format: str
    predicted_bytes: int


@dataclass
class ExportPrediction(SerializableDataclass):
    """Live export size prediction model."""

    predicted_bytes: int
    predicted_format: str
    confidence: float
    comparison: list[ExportComparisonEntry] = field(default_factory=list)


@dataclass
class ExportProfileModel(SerializableDataclass):
    """Named export profile preset for reusable output defaults."""

    id: str
    name: str
    description: str = ""
    export_profile: ExportProfile = ExportProfile.WEB
    format: ExportFormat = ExportFormat.AUTO
    quality: int = 90
    compression_level: int = 6
    chroma_subsampling: ChromaSubsampling = ChromaSubsampling.AUTO
    palette_limit: int | None = None
    ico_sizes: list[int] = field(default_factory=lambda: [16, 32, 48, 64, 128, 256])
    strip_metadata: bool = True
