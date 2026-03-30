"""Asset-centric data models from the Image Engine v1.0.1 schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from ._serialization import SerializableDataclass
from .session_state import HistoryState


class SourceType(str, Enum):
    FILE = "file"
    FOLDER_ITEM = "folder_item"
    URL = "url"
    WEBPAGE_ITEM = "webpage_item"


class AssetFormat(str, Enum):
    JPG = "jpg"
    PNG = "png"
    WEBP = "webp"
    TIFF = "tiff"
    BMP = "bmp"
    ICO = "ico"
    GIF = "gif"
    UNKNOWN = "unknown"


class EditMode(str, Enum):
    SIMPLE = "simple"
    ADVANCED = "advanced"
    EXPERT = "expert"


class ApplyTarget(str, Enum):
    CURRENT = "current"
    FINAL = "final"
    BOTH = "both"


class ScaleMethod(str, Enum):
    NEAREST = "nearest"
    BILINEAR = "bilinear"
    BICUBIC = "bicubic"
    LANCZOS = "lanczos"


class BackgroundRemovalMode(str, Enum):
    OFF = "off"
    WHITE = "white"
    BLACK = "black"


def normalize_background_removal_mode(
    raw_value: object,
    *,
    remove_white_bg: bool = False,
) -> BackgroundRemovalMode:
    """Normalize legacy/background-cutout values to a stable mode enum."""

    if isinstance(raw_value, BackgroundRemovalMode):
        return raw_value

    normalized = str(raw_value or "").strip().lower()
    aliases = {
        "": BackgroundRemovalMode.OFF,
        "off": BackgroundRemovalMode.OFF,
        "keep": BackgroundRemovalMode.OFF,
        "none": BackgroundRemovalMode.OFF,
        "white": BackgroundRemovalMode.WHITE,
        "remove_white": BackgroundRemovalMode.WHITE,
        "remove_white_bg": BackgroundRemovalMode.WHITE,
        "black": BackgroundRemovalMode.BLACK,
        "remove_black": BackgroundRemovalMode.BLACK,
        "remove_black_bg": BackgroundRemovalMode.BLACK,
    }
    if normalized in aliases:
        return aliases[normalized]
    return BackgroundRemovalMode.WHITE if bool(remove_white_bg) else BackgroundRemovalMode.OFF


class ExportProfile(str, Enum):
    WEB = "web"
    APP_ASSET = "app_asset"
    PRINT = "print"


class ExportFormat(str, Enum):
    AUTO = "auto"
    JPG = "jpg"
    PNG = "png"
    WEBP = "webp"
    GIF = "gif"
    ICO = "ico"
    TIFF = "tiff"
    BMP = "bmp"


class ChromaSubsampling(str, Enum):
    AUTO = "auto"
    CS_444 = "444"
    CS_422 = "422"
    CS_420 = "420"


class HeavyTool(str, Enum):
    AI_UPSCALE = "ai_upscale"
    AI_DEBLUR = "ai_deblur"
    BG_REMOVE = "bg_remove"
    AI_EXTEND = "ai_extend"


class HeavyJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLED = "cancelled"
    DONE = "done"
    ERROR = "error"


@dataclass
class Capabilities(SerializableDataclass):
    has_alpha: bool = False
    is_animated: bool = False
    is_sheet: bool = False
    is_ico_bundle: bool = False


@dataclass
class AnalysisSummary(SerializableDataclass):
    blur_score: float = 0.0
    noise_score: float = 0.0
    compression_score: float = 0.0
    edge_integrity_score: float = 0.0
    resolution_need_score: float = 0.0
    gif_palette_stress: float | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class PresetSuggestion(SerializableDataclass):
    preset_name: str
    confidence: float
    reason: str


@dataclass
class RecommendationsSummary(SerializableDataclass):
    suggested_presets: list[PresetSuggestion] = field(default_factory=list)
    suggested_export_profile: str | None = None
    suggested_export_format: str | None = None


@dataclass
class PixelSettings(SerializableDataclass):
    resize_percent: float = 100.0
    width: int | None = None
    height: int | None = None
    dpi: int = 72
    scale_method: ScaleMethod = ScaleMethod.LANCZOS
    pixel_snap: bool = False


@dataclass
class ColorSettings(SerializableDataclass):
    brightness: float = 0.0
    contrast: float = 0.0
    saturation: float = 0.0
    temperature: float = 0.0
    gamma: float = 1.0
    curves: dict[str, Any] | None = None


@dataclass
class DetailSettings(SerializableDataclass):
    sharpen_amount: float = 0.0
    sharpen_radius: float = 0.0
    sharpen_threshold: float = 0.0
    clarity: float = 0.0
    texture: float = 0.0


@dataclass
class CleanupSettings(SerializableDataclass):
    denoise: float = 0.0
    artifact_removal: float = 0.0
    halo_cleanup: float = 0.0
    banding_removal: float = 0.0


@dataclass
class EdgeSettings(SerializableDataclass):
    antialias: float = 0.0
    edge_refine: float = 0.0
    grow_shrink_px: float = 0.0
    feather_px: float = 0.0


@dataclass
class AlphaSettings(SerializableDataclass):
    background_removal_mode: str = BackgroundRemovalMode.OFF.value
    remove_white_bg: bool = False
    alpha_smooth: float = 0.0
    matte_fix: float = 0.0
    alpha_threshold: int = 0


@dataclass
class AISettings(SerializableDataclass):
    upscale_factor: float = 1.0
    deblur_strength: float = 0.0
    detail_reconstruct: float = 0.0
    bg_remove_strength: float = 0.0


@dataclass
class GifSettings(SerializableDataclass):
    frame_delay_ms: int = 100
    loop: bool = True
    palette_size: int = 256
    dither_strength: float = 0.0
    frame_optimize: bool = True


@dataclass
class ExportSettings(SerializableDataclass):
    export_profile: ExportProfile = ExportProfile.WEB
    format: ExportFormat = ExportFormat.AUTO
    quality: int = 90
    compression_level: int = 6
    chroma_subsampling: ChromaSubsampling = ChromaSubsampling.AUTO
    palette_limit: int | None = None
    ico_sizes: list[int] = field(default_factory=lambda: [16, 32, 48, 64, 128, 256])
    strip_metadata: bool = True


@dataclass
class SettingsState(SerializableDataclass):
    pixel: PixelSettings = field(default_factory=PixelSettings)
    color: ColorSettings = field(default_factory=ColorSettings)
    detail: DetailSettings = field(default_factory=DetailSettings)
    cleanup: CleanupSettings = field(default_factory=CleanupSettings)
    edges: EdgeSettings = field(default_factory=EdgeSettings)
    alpha: AlphaSettings = field(default_factory=AlphaSettings)
    ai: AISettings = field(default_factory=AISettings)
    gif: GifSettings = field(default_factory=GifSettings)
    export: ExportSettings = field(default_factory=ExportSettings)


@dataclass
class HeavyJobSpec(SerializableDataclass):
    id: str = field(default_factory=lambda: str(uuid4()))
    tool: HeavyTool = HeavyTool.AI_UPSCALE
    params: dict[str, Any] = field(default_factory=dict)
    status: HeavyJobStatus = HeavyJobStatus.QUEUED
    progress: float = 0.0
    started_at: datetime | None = None
    ended_at: datetime | None = None
    error_message: str | None = None


@dataclass
class EditState(SerializableDataclass):
    mode: EditMode = EditMode.SIMPLE
    sync_current_final: bool = True
    apply_target: ApplyTarget = ApplyTarget.BOTH
    auto_apply_light: bool = True
    queued_heavy_jobs: list[HeavyJobSpec] = field(default_factory=list)
    settings: SettingsState = field(default_factory=SettingsState)


@dataclass
class AssetRecord(SerializableDataclass):
    """Primary asset model from the v1.0.1 schema."""

    id: str = field(default_factory=lambda: str(uuid4()))
    source_type: SourceType = SourceType.FILE
    source_uri: str = ""
    cache_path: str | None = None
    derived_current_path: str | None = None
    derived_final_path: str | None = None
    original_name: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    format: AssetFormat = AssetFormat.UNKNOWN
    capabilities: Capabilities = field(default_factory=Capabilities)
    dimensions_original: tuple[int, int] = (0, 0)
    dimensions_current: tuple[int, int] = (0, 0)
    dimensions_final: tuple[int, int] = (0, 0)
    classification_tags: list[str] = field(default_factory=list)
    analysis: AnalysisSummary = field(default_factory=AnalysisSummary)
    recommendations: RecommendationsSummary = field(default_factory=RecommendationsSummary)
    edit_state: EditState = field(default_factory=EditState)
    history: HistoryState = field(default_factory=HistoryState)



