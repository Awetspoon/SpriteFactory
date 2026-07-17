"""Interactive Final-preview scheduling tests."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import time
import unittest

from PIL import Image

try:
    from PySide6.QtWidgets import QApplication
except Exception:  # pragma: no cover - optional dependency in some environments
    QApplication = None  # type: ignore[assignment]

from image_engine_app.app.paths import ensure_app_paths
from image_engine_app.app.ui_controller import ImageEngineUIController
from image_engine_app.engine.models import AssetFormat, AssetRecord, Capabilities
from image_engine_app.engine.process.edit_baseline import capture_detected_settings
from image_engine_app.ui.main_window.main_window import ImageEngineMainWindow


def _animated_asset(root: Path) -> AssetRecord:
    source = root / "sprite.gif"
    frames = []
    for index in range(12):
        frame = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
        for x in range(8 + index, 25 + index):
            for y in range(12, 34):
                frame.putpixel((x % 48, y), (170, 90 + index, 210, 255))
        frames.append(frame)
    frames[0].save(
        source,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=40,
        loop=0,
        disposal=2,
    )
    asset = AssetRecord(
        id="responsive-gif",
        original_name=source.name,
        source_uri=str(source),
        cache_path=str(source),
        format=AssetFormat.GIF,
        capabilities=Capabilities(has_alpha=True, is_animated=True),
        dimensions_original=(48, 48),
        dimensions_current=(48, 48),
        dimensions_final=(48, 48),
    )
    capture_detected_settings(asset)
    return asset


def _wait_until(app: QApplication, predicate, *, timeout_seconds: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    app.processEvents()
    return bool(predicate())


@unittest.skipIf(QApplication is None, "PySide6 not installed")
class EditCoordinatorTests(unittest.TestCase):
    def test_rapid_gif_control_changes_render_once_without_blocking_the_ui_call(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QApplication([])

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            controller = ImageEngineUIController(app_paths=ensure_app_paths(base_dir=root / "app-data"))
            window = ImageEngineMainWindow(controller=controller)
            asset = _animated_asset(root)
            window.set_active_asset(asset)

            original_refresh = controller.refresh_asset_final
            render_stems: list[str] = []

            def counted_refresh(target: AssetRecord, *, output_stem: str = "final"):
                render_stems.append(output_stem)
                return original_refresh(target, output_stem=output_stem)

            controller.refresh_asset_final = counted_refresh  # type: ignore[method-assign]

            try:
                started = time.monotonic()
                for value in (0.2, 0.4, 0.6, 0.8):
                    window._on_edit_setting_requested(
                        "detail",
                        "sharpen_amount",
                        value,
                    )
                call_elapsed = time.monotonic() - started

                self.assertLess(call_elapsed, 0.5)
                self.assertIsNone(asset.derived_final_path)
                self.assertTrue(window._edit_coordinator.preview_refresh_busy)
                self.assertTrue(
                    _wait_until(
                        app,
                        lambda: not window._edit_coordinator.preview_refresh_busy,
                    )
                )

                self.assertEqual(1, len(render_stems))
                self.assertTrue(render_stems[0].startswith("preview-"))
                self.assertAlmostEqual(0.8, asset.edit_state.settings.detail.sharpen_amount)
                self.assertIsNotNone(asset.derived_final_path)
                final_path = Path(str(asset.derived_final_path))
                self.assertEqual("final.gif", final_path.name)
                self.assertTrue(final_path.exists())
                with Image.open(final_path) as rendered:
                    self.assertGreater(int(getattr(rendered, "n_frames", 1)), 1)
            finally:
                window._edit_coordinator.shutdown(wait=True)
                app.processEvents()
                window.close()

        if owns_app and app is not None:
            app.quit()


if __name__ == "__main__":
    unittest.main()
