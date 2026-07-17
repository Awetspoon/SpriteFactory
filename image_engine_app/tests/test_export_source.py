"""Tests for selecting an available export source without losing GIF frames."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from image_engine_app.engine.models import AssetRecord, Capabilities, ExportFormat
from image_engine_app.engine.process.export_source import (
    resolve_export_source,
    select_export_source_path,
)


class ExportSourceTests(unittest.TestCase):
    def test_stale_derived_path_falls_back_to_existing_cache_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.png"
            source.write_bytes(b"source")
            asset = AssetRecord(
                id="source-static",
                source_uri=str(source),
                cache_path=str(source),
                derived_final_path=str(Path(temp_dir) / "missing-final.png"),
            )

            selected = select_export_source_path(asset)

            self.assertEqual(str(source), selected)
            self.assertFalse(resolve_export_source(asset).uses_derived_preview)

    def test_animated_auto_export_prefers_source_container_over_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.gif"
            preview = Path(temp_dir) / "final.gif"
            source.write_bytes(b"source")
            preview.write_bytes(b"preview")
            asset = AssetRecord(
                id="source-animation",
                source_uri=str(source),
                cache_path=str(source),
                derived_final_path=str(preview),
                capabilities=Capabilities(has_alpha=True, is_animated=True),
            )
            asset.edit_state.settings.export.format = ExportFormat.AUTO

            selected = select_export_source_path(asset)

            self.assertEqual(str(source), selected)

    def test_raw_source_with_visible_edits_carries_processing_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.png"
            source.write_bytes(b"source")
            asset = AssetRecord(
                id="source-edited",
                source_uri=str(source),
                cache_path=str(source),
            )
            asset.edit_state.settings.color.brightness = 0.1

            resolution = resolve_export_source(asset)

            self.assertEqual(str(source), resolution.source_path)
            self.assertIsNotNone(resolution.processing_settings)


if __name__ == "__main__":
    unittest.main()
