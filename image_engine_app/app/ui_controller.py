"""Application controller bridging the Qt shell to engine services."""

from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from uuid import uuid4

from image_engine_app.app.paths import AppPaths
from image_engine_app.engine.process.preset_compat import PresetCatalogEntry
from image_engine_app.engine.presets import build_builtin_presets
from image_engine_app.app.services import (
    AssetEditResult,
    AssetEditService,
    AssetImportService,
    ImportAssetContext,
    AssetProfileService,
    BatchPreparationResult,
    BatchWorkflowService,
    PresetLibrary,
    PresetWorkflowService,
    WebSourcesWorkflowService,
    export_asset,
    format_asset_export_prediction,
    predict_asset_export,
)
from image_engine_app.app.services.web_sources_downloader import WebSourcesDownloader
from image_engine_app.app.services.web_sources_scanner import WebSourcesScanner
from image_engine_app.app.web_sources_models import (
    Confidence,
    ImportTarget,
    SmartOptions,
    WebDiagnosticsRequest,
    WebDiscoveryOutcome,
    WebDownloadRequest,
    WebLinkDiscoveryRequest,
    WebRemoveSavedPageRequest,
    WebRemoveSavedWebsiteRequest,
    WebSavePagesRequest,
    WebScanOutcome,
    WebScanPlan,
    WebScanRequest,
    WebSourcesMutation,
    WebSourcesState,
)
from image_engine_app.engine.batch.batch_runner import BatchRunReport
from image_engine_app.engine.export.exporters import ExportResult
from image_engine_app.engine.export.size_predictor import ExportPredictorResult
from image_engine_app.engine.ingest.import_result import ImportResult
from image_engine_app.engine.ingest.local_ingest import ingest_local_sources
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
    BatchEditSource,
    HeavyJobSpec,
    HeavyTool,
    PresetModel,
    SourceType,
)
from image_engine_app.engine.process.edit_baseline import (
    CapturedControlSettings,
    capture_control_settings,
)
from image_engine_app.engine.process.heavy_queue import HeavyQueueEngine
from image_engine_app.engine.process.heavy_runtime import execute_heavy_job


@dataclass(frozen=True)
class PresetApplySummary:
    """UI-friendly preset application summary."""

    preset_name: str
    requires_apply: bool
    queued_heavy_jobs: int
    preview_rendered: bool = False
    preview_error: str | None = None


class ImageEngineUIController:
    """Orchestrate main-window workflows through focused application services."""

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
        self._asset_edits = AssetEditService(
            derived_cache_dir=(self.app_paths.cache if self.app_paths is not None else None),
        )
        self._preset_workflow = PresetWorkflowService(
            library=self._preset_library,
            asset_edits=self._asset_edits,
        )
        self._batch_workflow = BatchWorkflowService(
            app_paths=self.app_paths,
            preset_library=self._preset_library,
            preset_workflow=self._preset_workflow,
            heavy_queue_factory=self._heavy_queue_factory,
        )
        self._asset_profiles = AssetProfileService()
        self._asset_imports = AssetImportService(profiles=self._asset_profiles)
        self._web_sources_downloader = WebSourcesDownloader(
            app_paths=self.app_paths,
            scan_webpage_images=self.scan_webpage_images,
            import_url_source=self.import_url_source,
            import_cached_files=self._import_cached_web_files,
        )
        self._web_sources_scanner = WebSourcesScanner(
            scan_webpage_images=self.scan_webpage_images,
            canonicalize_download_url=self._web_sources_downloader.canonicalize_download_url,
            resolve_web_item_name=self._web_sources_downloader.resolve_web_item_name,
            extract_archive_urls=self._web_sources_downloader.extract_archive_urls,
        )
        self._web_sources_workflow = WebSourcesWorkflowService(
            app_paths=self.app_paths,
            scanner=self._web_sources_scanner,
            downloader=self._web_sources_downloader,
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

    def apply_named_preset(
        self,
        asset: AssetRecord,
        preset_name: str,
        *,
        refresh_final: bool = True,
        queue_heavy_jobs: bool = True,
    ) -> PresetApplySummary:
        """Apply a named preset to the active asset and queue any implied heavy jobs."""

        result = self._preset_workflow.apply_named(
            asset,
            preset_name,
            refresh_final=refresh_final,
            queue_heavy_jobs=queue_heavy_jobs,
        )

        return PresetApplySummary(
            preset_name=result.preset_name,
            requires_apply=result.requires_apply,
            queued_heavy_jobs=result.queued_heavy_jobs,
            preview_rendered=result.edit_result.preview_rendered,
            preview_error=result.edit_result.preview_error,
        )

    def restore_asset_detected_settings(
        self,
        asset: AssetRecord,
        *,
        refresh_final: bool = True,
    ) -> AssetEditResult:
        """Restore the controls detected for this asset at import time."""

        return self._asset_edits.reset_to_detected(asset, refresh_final=refresh_final)

    def update_asset_setting(
        self,
        asset: AssetRecord,
        group_name: str,
        field_name: str,
        value: object,
        *,
        refresh_final: bool = True,
    ) -> AssetEditResult:
        """Apply one control value through the shared edit/preview workflow."""

        return self._asset_edits.update_setting(
            asset,
            group_name,
            field_name,
            value,
            refresh_final=refresh_final,
        )

    def reset_asset_settings(
        self,
        asset: AssetRecord,
        field_paths: list[tuple[str, str]] | tuple[tuple[str, str], ...],
        *,
        refresh_final: bool = True,
    ) -> AssetEditResult:
        """Restore only the requested controls to this asset's detected baseline."""

        return self._asset_edits.reset_settings_to_detected(
            asset,
            field_paths,
            refresh_final=refresh_final,
        )

    def apply_asset_output_size(
        self,
        asset: AssetRecord,
        choice_key: str,
        *,
        refresh_final: bool = True,
    ) -> AssetEditResult:
        """Apply an output-size convenience choice through the real pixel controls."""

        return self._asset_edits.apply_output_size(
            asset,
            choice_key,
            refresh_final=refresh_final,
        )

    def set_asset_export_profile(self, asset: AssetRecord, profile_value: str) -> AssetEditResult:
        """Apply export profile defaults without rebuilding Final."""

        return self._asset_edits.set_export_profile(asset, profile_value)

    def refresh_asset_final(
        self,
        asset: AssetRecord,
        *,
        output_stem: str = "final",
    ) -> AssetEditResult:
        """Explicitly rebuild Final from the asset's current EditState."""

        return self._asset_edits.refresh_final(asset, output_stem=output_stem)

    def ensure_asset_final(self, asset: AssetRecord) -> AssetEditResult:
        """Create the initial Final preview when an asset first becomes active."""

        return self._asset_edits.ensure_final(asset)

    def refresh_final_preview(self, asset: AssetRecord) -> bool:
        """Compatibility wrapper for callers that only need render success."""

        return self.refresh_asset_final(asset).preview_rendered

    def import_local_sources(
        self,
        sources: list[str | Path],
        *,
        recursive: bool = True,
        preserve_structure: bool = True,
        flatten: bool = False,
        dedupe_by_hash: bool = True,
    ) -> ImportResult:
        """Import local files, folders, and ZIPs through one preparation path."""

        extract_root = (
            self.app_paths.cache / "_local_zip_import"
            if self.app_paths is not None
            else Path(".") / ".cache" / "_local_zip_import"
        )
        result = ingest_local_sources(
            sources,
            recursive=recursive,
            preserve_structure=preserve_structure,
            flatten=flatten,
            dedupe_by_hash=dedupe_by_hash,
            archive_extract_root=extract_root,
        )
        return self._asset_imports.prepare_new_result(result)

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
    ) -> ImportResult:
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

        tags = [str(tag) for tag in (classification_tags or []) if str(tag).strip()]
        if effective_url != url.strip():
            tags.append("url_fallback:webpage_first_image")

        result = self._asset_imports.import_cached_files(
            [downloaded.cache_path],
            context=ImportAssetContext(
                source_type=(source_type or SourceType.URL),
                source_uri=effective_url,
                classification_tags=tuple(tags),
                display_name=file_name,
            ),
        )
        entry = result.primary_entry
        if entry is None:
            failure = result.failed[0] if result.failed else "downloaded file was not a supported image"
            raise UrlIngestError(failure)

        entry.detected_format = downloaded.detected_format
        entry.bytes_received = downloaded.bytes_downloaded
        entry.preview_detected_format = preview.detected_format if preview is not None else None
        entry.preview_dimensions = preview.dimensions if preview is not None else None
        entry.preview_bytes_sampled = preview.bytes_sampled if preview is not None else None
        entry.preview_truncated = preview.truncated if preview is not None else None

        asset = entry.asset
        measured = tuple(getattr(asset, "dimensions_original", (0, 0)) or (0, 0))
        probed = downloaded.dimensions or (preview.dimensions if preview is not None else None)
        if measured == (0, 0) and probed is not None:
            resolved = (int(probed[0]), int(probed[1]))
            asset.dimensions_original = resolved
            asset.dimensions_current = resolved
            asset.dimensions_final = resolved
            entry.dimensions = resolved
        elif measured != (0, 0):
            entry.dimensions = (int(measured[0]), int(measured[1]))
        return result

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
    def web_sources_state(self) -> WebSourcesState:
        return self._web_sources_workflow.state()

    def replace_web_sources_registry(self, payload: object) -> WebSourcesMutation:
        return self._web_sources_workflow.replace_registry(payload)

    def save_web_sources_pages(self, request: WebSavePagesRequest) -> WebSourcesMutation:
        return self._web_sources_workflow.save_pages(request)

    def remove_web_sources_page(self, request: WebRemoveSavedPageRequest) -> WebSourcesMutation:
        return self._web_sources_workflow.remove_saved_page(request)

    def remove_web_sources_website(self, request: WebRemoveSavedWebsiteRequest) -> WebSourcesMutation:
        return self._web_sources_workflow.remove_saved_website(request)

    def update_web_sources_preferences(self, options: SmartOptions) -> WebSourcesState:
        return self._web_sources_workflow.update_preferences(options)

    def plan_web_sources_scan(self, request: WebScanRequest) -> WebScanPlan:
        return self._web_sources_workflow.plan_scan(request)

    def run_web_sources_scan(
        self,
        plan: WebScanPlan,
        *,
        opener=None,
        progress_callback=None,
        cancel_requested=None,
    ) -> WebScanOutcome:
        return self._web_sources_workflow.run_scan(
            plan,
            opener=opener,
            progress_callback=progress_callback,
            cancel_requested=cancel_requested,
        )

    def discover_web_sources_links(
        self,
        request: WebLinkDiscoveryRequest,
        *,
        opener=None,
        cancel_requested=None,
    ) -> WebDiscoveryOutcome:
        return self._web_sources_workflow.discover_links(
            request,
            opener=opener,
            cancel_requested=cancel_requested,
        )

    def clear_web_sources_links(self) -> WebSourcesMutation:
        return self._web_sources_workflow.clear_linked_pages()

    def clear_web_sources_found_files(self) -> WebSourcesMutation:
        return self._web_sources_workflow.clear_found_files()

    def download_web_sources(
        self,
        request: WebDownloadRequest,
        *,
        guards: DownloadGuards | None = None,
        opener=None,
        progress_callback=None,
        cancel_requested=None,
    ) -> ImportResult:
        return self._web_sources_workflow.download(
            request,
            guards=guards,
            opener=opener,
            progress_callback=progress_callback,
            cancel_requested=cancel_requested,
        )

    def diagnose_web_source(self, request: WebDiagnosticsRequest) -> str:
        return self._web_sources_workflow.diagnose(request)

    @staticmethod
    def format_web_sources_download_status(report: object) -> str:
        return WebSourcesWorkflowService.format_download_status(report)

    @staticmethod
    def friendly_web_sources_error(error: object) -> str:
        return WebSourcesWorkflowService.friendly_error(error)

    @staticmethod
    def _resolve_web_item_name(candidate_name: str | None, url: str) -> str:
        return WebSourcesDownloader.resolve_web_item_name(candidate_name, url)

    def _import_cached_web_files(
        self,
        *,
        file_paths: list[Path],
        source_uri: str,
        target: ImportTarget,
        confidence: Confidence,
        source_page: str | None,
        display_name: str | None = None,
        reused: bool = False,
    ) -> ImportResult:
        tags = [
            f"web_target:{target.value}",
            f"web_confidence:{confidence.value}",
        ]
        if source_page:
            tags.append(f"web_source:{source_page}")

        return self._asset_imports.import_cached_files(
            file_paths,
            context=ImportAssetContext(
                source_type=SourceType.WEBPAGE_ITEM,
                source_uri=source_uri,
                classification_tags=tuple(tags),
                display_name=display_name,
                reused=reused,
            ),
        )

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
        """Run an isolated Batch workflow without mutating workspace assets."""

        return self._batch_workflow.run(
            assets,
            preview_skip_mode=preview_skip_mode,
            auto_export=auto_export,
            auto_preset=auto_preset,
            export_name_template=export_name_template,
            avoid_overwrite=avoid_overwrite,
            export_dir=export_dir,
            event_callback=event_callback,
            cancel_requested=cancel_requested,
        )

    def prepare_batch_assets(
        self,
        *,
        selected_assets: list[AssetRecord],
        active_asset: AssetRecord | None,
        edit_source: BatchEditSource,
        selected_preset_name: str,
        background_override: str | None,
    ) -> BatchPreparationResult:
        """Prepare isolated Batch copies using one explicit edit-source rule."""

        return self._batch_workflow.prepare_assets(
            selected_assets=selected_assets,
            active_asset=active_asset,
            edit_source=edit_source,
            selected_preset_name=selected_preset_name,
            background_override=background_override,
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


