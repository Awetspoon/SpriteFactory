"""Application bootstrap for Sprite Factory v3 scaffold."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class V3AppConfig:
    """Minimal runtime configuration for v3 composition."""

    app_data_dir: Path


def build_config(*, app_data_dir: str | None = None) -> V3AppConfig:
    root = Path(app_data_dir).expanduser().resolve() if app_data_dir else (Path.cwd() / ".local" / "ui-check-v3")
    return V3AppConfig(app_data_dir=root)
