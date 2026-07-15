"""Application controller bridging the Qt shell to engine services."""

from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from uuid import uuid4

from image_engine_app.app.paths import AppPaths
from image_engine_app.engine.process.preset_compat import (
    PresetCatalogEntry,
    preset_matches_asset,
)
from image_engine_app.engine.presets import build_builtin_presets
from image_engine_app.app.services import (
    AssetProfileService,
    PresetLibrary,
    build_batch_auto_preset_rules,
    export_asset,
    format_asset_export_prediction,
    predict_asset_export,
)
from image_engine_app.app.services.web_sources_service import WebSourcesService
from image_engine_app.app.settings_store import default_web_sources_registry
from image_engine_app.app.web_sources_models import (
    Confidence,
    DownloadReport,
    ImportTarget,
    ScanResults,
    SmartOptions,
    WebIndexLink,
    WebItem,
)
from image_engine_app.engine.batch.batch_runner import BatchRunner, BatchRunnerConfig, BatchWorkItem, BatchRunReport
from image_engine_app.engine.export.exporters import ExportResult
from image_engine_app.engine.export.size_predictor import ExportPredictorResult
from image_engine_app.engine.ingest.local_ingest import LocalIngestResult, build_local_ingest_queue
from image_engine_app.engine.ingest.url_ingest import (
    DownloadGuards,
    DownloadCancelledError,
    MimeValidationError,
    SignatureValidationError,
    UrlIngestError,
    download_url_to_cache,
    stream_preview_mode,
)
from image_engine_app.engine.ingest.web_sources_rules import (
    ALLOWED_IMAGE_EXTS_DEFAULT,
    normalize_ext,
)
from image_engine_app.engine.ingest.webpage_scan import (
    WebpageScanFilters,
    WebpageScanResult,
    scan_webpage_for_images,
)
from image_engine_app.engine.models import (
    AssetRecord,
    EditMode,
    EditState,
    HeavyJobSpec,
    HeavyTool,
    PresetModel,
    QueueItem,
    QueueItemStatus,
    SourceType,
    normalize_edit_mode,
)
from image_engine_app.engine.process.edit_baseline import (
    CapturedControlSettings,
    capture_control_settings,
    capture_detected_settings,
    clear_generated_outputs,
    edit_state_from_detected_settings,
    implied_heavy_jobs,
    restore_detected_settings,
)
from image_engine_app.engine.process.heavy_queue import HeavyQueueEngine
from image_engine_app.engine.process.heavy_runtime import execute_heavy_job
from image_engine_app.engine.process.light_steps import LightProcessError
from image_engine_app.engine.process.preview_support import render_light_pipeline_preview, select_export_source_path
from image_engine_app.engine.process.presets_apply import (
    PresetApplyError,
    apply_preset_to_edit_state,
)


@dataclass(frozen=True)
class PresetApplySummary:
    """UI-friendly preset application summary."""

    preset_name: str
    requires_apply: bool
    queued_heavy_jobs: int


@dataclass(frozen=True)
class LocalImportSummary:
    """Result of importing local files/folders into AssetRecord instances."""

    assets: list[AssetRecord]
    duplicates: list[Path]
    unsupported: list[Path]
    raw_result: LocalIngestResult


@dataclass(frozen=True)
class UrlImportSummary:
    """Result of URL download/import into a cached AssetRecord."""

    asset: AssetRecord
    cache_path: Path
    detected_format: str
    bytes_downloaded: int
    dimensions: tuple[int, int] | None
    preview_detected_format: str | None = None
    preview_dimensions: tuple[int, int] | None = None
    preview_bytes_sampled: int | None = None
    preview_truncated: bool | None = None


class ImageEngineUIController:
    """Orchestrate main-window workflows through focused application services."""

    AUTO_DETECTED_PRESET_MIN_CONFIDENCE = 0.6

    def __init__(
        self,
        *,
        app_paths: AppPaths | None = None,
        heavy_queue_factory=None,
    ) -> None:
        self.app_paths = app_paths
        self._heavy_queue_factory = heavy_queue_factory or (lambda: HeavyQueueEngine())

        self._preset_library = PresetLibrary(
            system_presets=build_builtin_presets(),
            app_paths=self.app_paths,
        )
        self._asset_profiles = AssetProfileService()
        self._web_sources_service = WebSourcesService(
            app_paths=self.app_paths,
            scan_webpage_images=self.scan_webpage_images,
            import_url_source=self.import_url_source,
            build_web_asset_from_file=self._build_web_asset_from_file,
        )


    def available_preset_names(self) -> list[str]:
        return self._preset_library.available_names()

    def get_preset(self, name: str) -> PresetModel:
        return self._preset_library.get(name)

    def list_presets(self) -> list[PresetModel]:
        return self._preset_library.list_all()

    def available_preset_entries(
        self,
        asset: AssetRecord | None = None,
        *,
        compatible_only: bool = False,
    ) -> list[PresetCatalogEntry]:
        return self._preset_library.available_entries(asset, compatible_only=compatible_only)

    def describe_preset_scope(self, preset_name: str) -> str:
        return self._preset_library.describe_preset_scope(preset_name)

    def describe_asset_scope(self, asset: AssetRecord | None) -> str:
        return self._preset_library.describe_asset_scope(asset)

    def is_user_preset(self, name: str) -> bool:
        return self._preset_library.is_user_preset(name)

    def upsert_user_preset(self, preset: PresetModel) -> None:
        self._preset_library.upsert_user_preset(preset)

    def delete_user_preset(self, name: str) -> bool:
        return self._preset_library.delete_user_preset(name)

    @staticmethod
    def capture_preset_controls(asset: AssetRecord) -> CapturedControlSettings:
        """Capture only the active asset controls changed after detection."""

        return capture_control_settings(asset)

    @staticmethod
    def _determine_mode_for_preset(edit_state: EditState, preset: PresetModel) -> None:
        mode_rank = {
            EditMode.ADVANCED: 0,
            EditMode.EXPERT: 1,
        }
        current_mode = normalize_edit_mode(edit_state.mode)
        preset_mode = normalize_edit_mode(preset.mode_min)
        if mode_rank[current_mode] < mode_rank[preset_mode]:
            edit_state.mode = preset_mode

    def apply_named_preset(self, asset: AssetRecord, preset_name: str) -> PresetApplySummary:
        """Apply a named preset to the active asset and queue any implied heavy jobs."""

        preset = self.get_preset(preset_name)
        compatible, reason = preset_matches_asset(preset, asset)
        if not compatible:
            raise PresetApplyError(reason)
        baseline_state = edit_state_from_detected_settings(asset)
        self._determine_mode_for_preset(baseline_state, preset)
        updated_state = apply_preset_to_edit_state(preset, baseline_state)

        asset.edit_state = updated_state
        clear_generated_outputs(asset)

        if preset.uses_heavy_tools:
            self._queue_implied_heavy_jobs(asset, preset)

        return PresetApplySummary(
            preset_name=preset.name,
            requires_apply=(preset.requires_apply or preset.uses_heavy_tools),
            queued_heavy_jobs=len(asset.edit_state.queued_heavy_jobs),
        )

    @staticmethod
    def restore_asset_detected_settings(asset: AssetRecord) -> None:
        """Restore the controls detected for this asset at import time."""

        restore_detected_settings(asset)

    def apply_light_pipeline(self, asset: AssetRecord) -> bool:
        """Apply the non-AI light pipeline and write derived Current/Final outputs.

        Returns True if a derived file was written, False if the asset has no local source
        or Pillow is unavailable.
        """
        cache_root = (self.app_paths.cache if self.app_paths is not None else Path(".") / "_derived_cache")
        return render_light_pipeline_preview(asset, derived_cache_dir=cache_root, final_only=False)

    def import_local_sources(
        self,
        sources: list[str | Path],
        *,
        recursive: bool = True,
        preserve_structure: bool = True,
        flatten: bool = False,
        dedupe_by_hash: bool = True,
    ) -> LocalImportSummary:
        """Import local file/folder sources and return generated assets."""

        result = build_local_ingest_queue(
            sources,
            recursive=recursive,
            preserve_structure=preserve_structure,
            flatten=flatten,
            dedupe_by_hash=dedupe_by_hash,
        )
        assets = [entry.asset for entry in result.queue]
        self._hydrate_local_assets(assets)
        return LocalImportSummary(
            assets=assets,
            duplicates=list(result.duplicates),
            unsupported=list(result.unsupported),
            raw_result=result,
        )
    def import_url_source(
        self,
        url: str,
        *,
        cache_key_url: str | None = None,
        guards: DownloadGuards | None = None,
        opener=None,
        display_name: str | None = None,
        source_type: SourceType | None = None,
        classification_tags: list[str] | None = None,
        cache_subdir: str | None = None,
        stream_preview: bool = True,
        preview_max_bytes: int = 96 * 1024,
        request_headers: dict[str, str] | None = None,
        allow_webpage_fallback: bool = True,
        cancel_requested=None,
    ) -> UrlImportSummary:
        """Download/cache a URL and convert it into an AssetRecord.

        - display_name: overrides the AssetRecord.original_name (human label)
        - source_type: allows WEBPAGE_ITEM vs URL
        - classification_tags: appended onto asset.classification_tags
        - cache_subdir: optional subfolder under app cache (used for webpage grouping)
        - cache_key_url: optional stable cache key when the real download URL differs
          from the logical source URL (for example, file-page -> raw image resolution)
        - stream_preview: when True, performs a bounded metadata probe before full download
        - request_headers: optional additional request headers (e.g. Referer)
        - allow_webpage_fallback: if direct URL fails and looks like webpage URL, auto-pick first image
        """

        base_cache = self.app_paths.cache if self.app_paths is not None else Path(".") / "cache"
        cache_dir = base_cache

        if cache_subdir:
            # sanitize subdir into safe path segments
            safe_parts: list[str] = []
            for part in re.split(r"[\\/]+", str(cache_subdir)):
                part = part.strip()
                if not part:
                    continue
                safe = "".join(ch if (ch.isalnum() or ch in {"-", "_"}) else "_" for ch in part)
                safe = safe.strip("_")
                if not safe:
                    continue
                safe_parts.append(safe)
            if safe_parts:
                cache_dir = base_cache.joinpath(*safe_parts)

        effective_url = url.strip()
        stable_cache_key = (cache_key_url or url).strip() or url.strip()
        preview = None
        if stream_preview:
            # Best-effort preflight. Keep full download as source of truth to avoid
            # regressions on servers that reject ranged reads.
            try:
                preview = stream_preview_mode(
                    effective_url,
                    max_preview_bytes=preview_max_bytes,
                    opener=opener,
                    request_headers=request_headers,
                )
            except UrlIngestError:
                preview = None

        def _is_cancel_requested() -> bool:
            if cancel_requested is None:
                return False
            try:
                return bool(cancel_requested())
            except Exception:
                return False

        if _is_cancel_requested():
            raise DownloadCancelledError("Download cancelled by user")

        try:
            downloaded = download_url_to_cache(
                effective_url,
                cache_dir,
                cache_key_url=stable_cache_key,
                guards=guards,
                opener=opener,
                request_headers=request_headers,
                cancel_requested=cancel_requested,
            )
        except UrlIngestError as primary_exc:
            if _is_cancel_requested() or isinstance(primary_exc, DownloadCancelledError):
                raise DownloadCancelledError("Download cancelled by user") from primary_exc

            # If a URL turns out to be a webpage/file-view page instead of raw media,
            # auto-resolve the first real image so fandom/wiki style routes still import cleanly.
            fallback_url: str | None = None
            looks_like_page_route = any(
                marker in effective_url.lower()
                for marker in ("/wiki/file:", "/wiki/file%3a", "/wiki/", "fandom.com/wiki/")
            )
            html_like_failure = isinstance(primary_exc, (SignatureValidationError, MimeValidationError))
            should_try_fallback = (
                allow_webpage_fallback
                and (
                    normalize_ext(effective_url) not in ALLOWED_IMAGE_EXTS_DEFAULT
                    or looks_like_page_route
                    or html_like_failure
                )
            )
            if should_try_fallback:
                fallback_url = self._resolve_first_image_url_from_webpage(effective_url, opener=opener)

            if not fallback_url or fallback_url == effective_url:
                raise primary_exc

            effective_url = fallback_url
            preview = None
            if stream_preview:
                try:
                    preview = stream_preview_mode(
                        effective_url,
                        max_preview_bytes=preview_max_bytes,
                        opener=opener,
                        request_headers=request_headers,
                    )
                except UrlIngestError:
                    preview = None

            if _is_cancel_requested():
                raise DownloadCancelledError("Download cancelled by user")

            downloaded = download_url_to_cache(
                effective_url,
                cache_dir,
                cache_key_url=stable_cache_key,
                guards=guards,
                opener=opener,
                request_headers=request_headers,
                cancel_requested=cancel_requested,
            )

        if display_name and display_name.strip():
            file_name = self._resolve_web_item_name(display_name.strip(), effective_url)
        else:
            file_name = self._resolve_web_item_name(None, effective_url) or downloaded.cache_path.name

        asset = AssetRecord(
            source_type=(source_type or SourceType.URL),
            source_uri=effective_url,
            cache_path=str(downloaded.cache_path),
            original_name=file_name,
            format=self._asset_profiles.asset_format_from_detected(downloaded.detected_format),
        )

        if effective_url != url.strip() and "url_fallback:webpage_first_image" not in asset.classification_tags:
            asset.classification_tags.append("url_fallback:webpage_first_image")

        if classification_tags:
            for tag in classification_tags:
                if tag and tag not in asset.classification_tags:
                    asset.classification_tags.append(str(tag))

        dimensions = downloaded.dimensions or (preview.dimensions if preview is not None else None)
        if dimensions is not None:
            asset.dimensions_original = dimensions
            asset.dimensions_current = dimensions
            asset.dimensions_final = dimensions

        self._hydrate_imported_asset(asset)

        resolved_dimensions = (
            asset.dimensions_original if getattr(asset, "dimensions_original", (0, 0)) != (0, 0) else dimensions
        )

        return UrlImportSummary(
            asset=asset,
            cache_path=downloaded.cache_path,
            detected_format=downloaded.detected_format,
            bytes_downloaded=downloaded.bytes_downloaded,
            dimensions=resolved_dimensions,
            preview_detected_format=(preview.detected_format if preview is not None else None),
            preview_dimensions=(preview.dimensions if preview is not None else None),
            preview_bytes_sampled=(preview.bytes_sampled if preview is not None else None),
            preview_truncated=(preview.truncated if preview is not None else None),
        )
    def scan_webpage_images(
        self,
        page_url: str,
        *,
        max_depth: int = 0,
        filters: WebpageScanFilters | None = None,
        opener=None,
        same_domain_only: bool = True,
        max_pages: int = 50,
        max_images: int | None = None,
        dedupe_images: bool = True,
        cancel_requested=None,
    ) -> WebpageScanResult:
        """Scan a webpage for image URLs using the ingest logic."""

        return scan_webpage_for_images(
            page_url,
            filters=filters,
            opener=opener,
            max_depth=max_depth,
            same_domain_only=same_domain_only,
            max_pages=max_pages,
            max_images=max_images,
            dedupe_images=dedupe_images,
            cancel_requested=cancel_requested,
        )
    def _resolve_first_image_url_from_webpage(self, page_url: str, *, opener=None) -> str | None:
        """Best-effort: return first image URL found on a webpage."""

        try:
            scan = self.scan_webpage_images(
                page_url,
                max_depth=0,
                same_domain_only=False,
                max_pages=1,
                dedupe_images=True,
                filters=WebpageScanFilters(
                    allowed_extensions=set(ALLOWED_IMAGE_EXTS_DEFAULT),
                    dedupe=True,
                    include_srcset=True,
                    include_anchor_image_links=True,
                ),
                opener=opener,
            )
        except Exception:
            return None

        first_any: str | None = None
        for hit in scan.images:
            candidate = str(getattr(hit, "url", "") or "").strip()
            if not candidate:
                continue
            if first_any is None:
                first_any = candidate
            if normalize_ext(candidate) in ALLOWED_IMAGE_EXTS_DEFAULT:
                return candidate
        return first_any
    def load_web_sources_registry(self, registry: list[dict] | None = None) -> list[dict]:
        """Return validated website/area registry entries for the Web Sources panel."""

        if registry is None:
            registry = []
        return self._web_sources_service.load_registry(registry)

    def discover_web_source_index_links(
        self,
        index_url: str,
        *,
        opener=None,
        same_domain_only: bool = True,
        cancel_requested=None,
    ) -> tuple[WebIndexLink, ...]:
        """Discover linked sprite/category pages from a Web Sources index page."""

        return self._web_sources_service.discover_index_links(
            index_url,
            opener=opener,
            same_domain_only=same_domain_only,
            cancel_requested=cancel_requested,
        )

    def scan_web_source_pages(
        self,
        page_urls: list[str],
        *,
        allowed_exts: set[str] | None = None,
        show_likely: bool = False,
        opener=None,
        cancel_requested=None,
    ) -> ScanResults:
        """Scan multiple selected Web Sources pages and merge their results."""

        return self._web_sources_service.scan_pages(
            page_urls,
            allowed_exts=allowed_exts,
            show_likely=show_likely,
            opener=opener,
            cancel_requested=cancel_requested,
        )

    def download_web_sources_items(
        self,
        items: list[WebItem],
        target: ImportTarget,
        *,
        smart: SmartOptions,
        guards: DownloadGuards | None = None,
        opener=None,
        progress_callback=None,
        cancel_requested=None,
    ) -> DownloadReport:
        """Download selected Web Sources items and return counters plus imported assets."""

        return self._web_sources_service.download_items(
            items,
            target,
            smart=smart,
            guards=guards,
            opener=opener,
            progress_callback=progress_callback,
            cancel_requested=cancel_requested,
        )

    @staticmethod
    def _resolve_web_item_name(candidate_name: str | None, url: str) -> str:
        return WebSourcesService.resolve_web_item_name(candidate_name, url)

    def _build_web_asset_from_file(
        self,
        *,
        file_path: Path,
        source_uri: str,
        target: ImportTarget,
        confidence: Confidence,
        source_page: str | None,
        display_name: str | None = None,
    ) -> AssetRecord:
        asset = AssetRecord(
            source_type=SourceType.WEBPAGE_ITEM,
            source_uri=source_uri,
            cache_path=str(file_path),
            original_name=(display_name.strip() if (display_name and display_name.strip()) else file_path.name),
            format=self._asset_profiles.asset_format_from_extension(file_path.suffix),
        )

        asset.classification_tags.append(f"web_target:{target.value}")
        asset.classification_tags.append(f"web_confidence:{confidence.value}")
        if source_page:
            asset.classification_tags.append(f"web_source:{source_page}")

        self._hydrate_imported_asset(asset)
        return asset

    def run_batch(
        self,
        assets: list[AssetRecord],
        *,
        preview_skip_mode: bool = True,
        auto_export: bool = False,
        auto_preset: bool = True,
        export_name_template: str | None = None,
        avoid_overwrite: bool = True,
        export_dir: str | Path | None = None,
        event_callback=None,
        cancel_requested=None,
    ) -> BatchRunReport:
        """Run the engine batch runner over a list of assets."""

        auto_preset_rules = build_batch_auto_preset_rules(self._preset_library, enabled=auto_preset)
        resolved_export_dir: str | Path | None = None
        if auto_export:
            if export_dir is not None:
                resolved_export_dir = export_dir
            elif self.app_paths is not None:
                resolved_export_dir = self.app_paths.exports

        config = BatchRunnerConfig(
            preview_skip_mode=preview_skip_mode,
            auto_export=auto_export,
            export_dir=resolved_export_dir,
            derived_cache_dir=((self.app_paths.cache / "batch_runs") if self.app_paths is not None else None),
            auto_preset_rules=auto_preset_rules,
            export_name_template=(export_name_template or "{stem}"),
            overwrite_existing_exports=(not avoid_overwrite),
            heavy_progress_steps=2,
            heavy_step_delay_seconds=0.0,
        )
        runner = BatchRunner(config, heavy_queue_factory=self._heavy_queue_factory)
        work_items = [
            BatchWorkItem(
                asset=asset,
                queue_item=QueueItem(
                    id=f"batch-{idx+1:03d}",
                    asset_id=asset.id,
                    status=QueueItemStatus.PENDING,
                    progress=0.0,
                ),
            )
            for idx, asset in enumerate(assets)
        ]
        return runner.run(
            work_items,
            event_callback=event_callback,
            cancel_requested=cancel_requested,
        )

    def queue_heavy_job(
        self,
        asset: AssetRecord,
        *,
        tool: HeavyTool,
        params: dict | None = None,
        job_id: str | None = None,
    ) -> HeavyJobSpec:
        """Queue/replace a heavy job on the asset using engine queue semantics."""

        engine = self._heavy_queue_factory()
        for existing in asset.edit_state.queued_heavy_jobs:
            engine.enqueue_or_replace(existing)

        queued = engine.enqueue_or_replace(
            HeavyJobSpec(
                id=job_id or str(uuid4()),
                tool=tool,
                params=dict(params or {}),
            )
        )
        asset.edit_state.queued_heavy_jobs = engine.list_jobs()
        return queued

    def apply_heavy_queue(self, asset: AssetRecord) -> list[HeavyJobSpec]:
        """Run queued heavy jobs and persist updated statuses back to the asset."""

        if not asset.edit_state.queued_heavy_jobs:
            return []

        engine = self._heavy_queue_factory()
        for job in asset.edit_state.queued_heavy_jobs:
            engine.enqueue_or_replace(job)

        derived_cache_dir = self.app_paths.cache if self.app_paths is not None else Path(".") / "_derived_cache"
        completed = engine.run_all(
            progress_steps=4,
            step_delay_seconds=0.0,
            task_runner=lambda job: execute_heavy_job(
                asset,
                job,
                derived_cache_dir=derived_cache_dir,
            ),
        )
        asset.edit_state.queued_heavy_jobs = engine.list_jobs()
        return completed

    def predict_export(self, asset: AssetRecord) -> ExportPredictorResult:
        """Compute live export size prediction for the active asset."""
        return predict_asset_export(asset)

    def format_prediction_text(self, asset: AssetRecord) -> str:
        """Return the UI label text for the current live export prediction."""
        return format_asset_export_prediction(asset)

    def export_active_asset(
        self,
        asset: AssetRecord,
        *,
        export_dir: str | Path | None = None,
    ) -> ExportResult:
        """Export the active asset into the configured exports directory."""
        return export_asset(asset, app_paths=self.app_paths, export_dir=export_dir)

    def _select_export_source_path(self, asset: AssetRecord) -> str | None:
        """Choose the best source path for export.

        Default: prefer derived_final_path, then derived_current_path, then cache_path, then local source_uri.
        If exporting GIF from an animated source, prefer the original cache_path/source_uri so frames can be preserved.
        """
        return select_export_source_path(asset)

    def _hydrate_imported_asset(self, asset: AssetRecord) -> None:
        self._asset_profiles.hydrate_imported_asset(
            asset,
            apply_baseline_preset=self._apply_detected_baseline_preset,
        )
        capture_detected_settings(asset)

    def _apply_detected_baseline_preset(self, asset: AssetRecord) -> None:
        recs = getattr(asset, "recommendations", None)
        suggestions = list(getattr(recs, "suggested_presets", []) or [])
        if not suggestions:
            return

        suggestion = next(
            (
                item
                for item in suggestions
                if self._preset_library.has_preset(item.preset_name)
                and float(getattr(item, "confidence", 0.0)) >= self.AUTO_DETECTED_PRESET_MIN_CONFIDENCE
                and preset_matches_asset(self.get_preset(item.preset_name), asset)[0]
            ),
            None,
        )
        if suggestion is None:
            return

        preset = self.get_preset(suggestion.preset_name)
        self._determine_mode_for_preset(asset.edit_state, preset)
        asset.edit_state = apply_preset_to_edit_state(preset, asset.edit_state)

        # Detection should not enqueue heavy work before the user explicitly applies.
        asset.edit_state.queued_heavy_jobs.clear()

    def _hydrate_local_assets(self, assets: list[AssetRecord]) -> None:
        self._asset_profiles.hydrate_local_assets(assets, hydrate_asset=self._hydrate_imported_asset)

    def _queue_implied_heavy_jobs(self, asset: AssetRecord, preset: PresetModel) -> None:
        for job in implied_heavy_jobs(preset, asset.edit_state):
            self.queue_heavy_job(
                asset,
                tool=job.tool,
                params=job.params,
                job_id=job.id,
            )



