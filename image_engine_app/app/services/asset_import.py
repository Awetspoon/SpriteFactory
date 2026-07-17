"""Application-level preparation for every newly imported asset."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from image_engine_app.app.services.asset_profile_service import AssetProfileService
from image_engine_app.engine.ingest.import_result import ImportResult
from image_engine_app.engine.ingest.local_ingest import ingest_local_sources
from image_engine_app.engine.models import AssetRecord, SourceType
from image_engine_app.engine.process.edit_baseline import capture_detected_settings


@dataclass(frozen=True)
class ImportAssetContext:
    """Overrides that describe where cached files originated."""

    source_type: SourceType
    source_uri: str
    classification_tags: tuple[str, ...] = ()
    display_name: str | None = None
    reused: bool = False


class AssetImportService:
    """Turns raw ingest entries into fully detected, workspace-ready assets."""

    def __init__(
        self,
        *,
        profiles: AssetProfileService,
    ) -> None:
        self._profiles = profiles

    def prepare_new_result(
        self,
        result: ImportResult,
        *,
        context: ImportAssetContext | None = None,
    ) -> ImportResult:
        """Hydrate every new entry once and preserve source context consistently."""

        for entry in result.entries:
            asset = entry.asset
            if context is not None:
                asset.source_type = context.source_type
                asset.source_uri = context.source_uri
                if context.display_name and len(result.entries) == 1:
                    asset.original_name = context.display_name.strip()
                entry.source = context.source_uri
                entry.reused = bool(context.reused)
                for tag in context.classification_tags:
                    normalized = str(tag).strip()
                    if normalized and normalized not in asset.classification_tags:
                        asset.classification_tags.append(normalized)

            if entry.local_path is not None:
                asset.cache_path = str(entry.local_path)
            elif asset.cache_path is None and asset.source_type in {SourceType.FILE, SourceType.FOLDER_ITEM}:
                asset.cache_path = asset.source_uri

            self._profiles.hydrate_imported_asset(asset)
            capture_detected_settings(asset)

            measured = tuple(getattr(asset, "dimensions_original", (0, 0)) or (0, 0))
            if len(measured) == 2 and int(measured[0] or 0) > 0 and int(measured[1] or 0) > 0:
                entry.dimensions = (int(measured[0]), int(measured[1]))

        return result

    def import_cached_files(
        self,
        paths: Iterable[str | Path],
        *,
        context: ImportAssetContext,
        dedupe_by_hash: bool = True,
    ) -> ImportResult:
        """Import already-local files, including downloaded and extracted web assets."""

        result = ingest_local_sources(
            paths,
            recursive=False,
            preserve_structure=False,
            flatten=True,
            dedupe_by_hash=dedupe_by_hash,
        )
        return self.prepare_new_result(result, context=context)
