"""Preview panel behavior tests."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
except Exception:  # pragma: no cover - optional dependency in some environments
    Qt = None  # type: ignore[assignment]
    QApplication = None  # type: ignore[assignment]

from PIL import Image  # noqa: E402

from ui.common.state_bindings import EngineUIState  # noqa: E402
from ui.main_window.preview_panel import PreviewPanel  # noqa: E402


@unittest.skipIf(QApplication is None, "PySide6 not installed")
class PreviewPanelTests(unittest.TestCase):
    def _setup_panel(self) -> tuple[QApplication, bool, PreviewPanel]:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QApplication([])
        panel = PreviewPanel()
        return app, owns_app, panel

    def test_zoom_persists_when_same_source_file_is_updated(self) -> None:
        app, owns_app, panel = self._setup_panel()
        pane = panel._panes["final"]

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "sprite.png"
            Image.new("RGBA", (16, 16), (10, 80, 200, 255)).save(image_path, format="PNG")

            panel._set_pane_source(pane, image_path)
            self.assertIsNotNone(pane.qimage)

            panel._set_pane_zoom(pane, 2.5, manual=True)
            self.assertFalse(pane.auto_follow_zoom)

            # Rewrite same path with a different image so the file signature changes.
            Image.new("RGBA", (24, 20), (220, 40, 40, 255)).save(image_path, format="PNG")
            panel._set_pane_source(pane, image_path)

            self.assertAlmostEqual(pane.zoom_factor, 2.5, places=3)
            self.assertFalse(pane.auto_follow_zoom)

        panel.close()
        if owns_app and app is not None:
            app.quit()

    def test_reset_view_request_reenables_auto_follow(self) -> None:
        app, owns_app, panel = self._setup_panel()
        pane = panel._panes["final"]

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "sprite.png"
            Image.new("RGBA", (24, 24), (10, 80, 200, 255)).save(image_path, format="PNG")
            panel._set_pane_source(pane, image_path)

            panel._set_pane_zoom(pane, 3.0, manual=True)
            self.assertFalse(pane.auto_follow_zoom)

            ui_state = EngineUIState()
            panel.bind_state(ui_state)
            ui_state.request_reset_view()

            self.assertTrue(pane.auto_follow_zoom)
            self.assertAlmostEqual(pane.zoom_factor, 1.0, places=3)

        panel.close()
        if owns_app and app is not None:
            app.quit()

    def test_zoom_transform_is_crisp_when_magnified(self) -> None:
        app, owns_app, panel = self._setup_panel()

        self.assertEqual(
            panel._transform_mode_for_scale(pixel_snap=False, zoom_snap_enabled=True, effective_scale=2.0),
            Qt.TransformationMode.FastTransformation,
        )
        self.assertEqual(
            panel._transform_mode_for_scale(pixel_snap=False, zoom_snap_enabled=False, effective_scale=2.0),
            Qt.TransformationMode.SmoothTransformation,
        )
        self.assertEqual(
            panel._transform_mode_for_scale(pixel_snap=False, zoom_snap_enabled=True, effective_scale=0.5),
            Qt.TransformationMode.SmoothTransformation,
        )
        self.assertEqual(
            panel._transform_mode_for_scale(pixel_snap=True, zoom_snap_enabled=False, effective_scale=0.5),
            Qt.TransformationMode.FastTransformation,
        )

        panel._on_zoom_snap_toggled(False)
        self.assertEqual(panel._zoom_snap_button.text(), "Crisp Zoom: Off")
        panel._on_zoom_snap_toggled(True)
        self.assertEqual(panel._zoom_snap_button.text(), "Crisp Zoom: On")

        panel.close()
        if owns_app and app is not None:
            app.quit()

    def test_preview_panes_use_zero_gap_with_divider_lines(self) -> None:
        app, owns_app, panel = self._setup_panel()

        self.assertIsNotNone(panel._pane_grid)
        self.assertEqual(panel._pane_grid.horizontalSpacing(), 0)
        self.assertIn("border-right", panel._pane_containers["before"].styleSheet())

        panel.close()
        if owns_app and app is not None:
            app.quit()

    def test_zoom_factor_clamped_to_expected_range(self) -> None:
        app, owns_app, panel = self._setup_panel()
        pane = panel._panes["final"]

        panel._set_pane_zoom(pane, 999.0, manual=True)
        self.assertAlmostEqual(pane.zoom_factor, 16.0, places=3)

        panel._set_pane_zoom(pane, 0.01, manual=True)
        self.assertAlmostEqual(pane.zoom_factor, 0.25, places=3)

        panel.close()
        if owns_app and app is not None:
            app.quit()


    def test_manual_zoom_persists_when_source_path_changes(self) -> None:
        app, owns_app, panel = self._setup_panel()
        pane = panel._panes["final"]

        with tempfile.TemporaryDirectory() as temp_dir:
            first_path = Path(temp_dir) / "first.png"
            second_path = Path(temp_dir) / "second.png"
            Image.new("RGBA", (20, 20), (30, 120, 220, 255)).save(first_path, format="PNG")
            Image.new("RGBA", (24, 24), (220, 80, 30, 255)).save(second_path, format="PNG")

            panel._set_pane_source(pane, first_path)
            panel._set_pane_zoom(pane, 3.0, manual=True)
            self.assertFalse(pane.auto_follow_zoom)

            # Switching to a different source should keep manual zoom state.
            panel._set_pane_source(pane, second_path)
            self.assertAlmostEqual(pane.zoom_factor, 3.0, places=3)
            self.assertFalse(pane.auto_follow_zoom)

        panel.close()
        if owns_app and app is not None:
            app.quit()

    def test_animated_gif_source_advances_frames_in_preview(self) -> None:
        app, owns_app, panel = self._setup_panel()
        pane = panel._panes["before"]

        with tempfile.TemporaryDirectory() as temp_dir:
            gif_path = Path(temp_dir) / "anim.gif"
            frames = [
                Image.new("RGBA", (12, 12), (255, 0, 0, 255)),
                Image.new("RGBA", (12, 12), (0, 255, 0, 255)),
            ]
            frames[0].save(
                gif_path,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                duration=[90, 110],
                loop=0,
            )

            panel._set_pane_source(pane, gif_path)
            self.assertGreater(len(pane.animation_frames), 1)
            self.assertFalse(pane.qimage is None)

            first_color = pane.qimage.pixelColor(0, 0).rgba()
            first_idx = int(pane.animation_frame_index)
            panel._advance_animation_frame(pane)

            self.assertNotEqual(int(pane.animation_frame_index), first_idx)
            self.assertFalse(pane.qimage is None)
            second_color = pane.qimage.pixelColor(0, 0).rgba()
            self.assertNotEqual(first_color, second_color)

        panel.close()
        if owns_app and app is not None:
            app.quit()

    def test_auto_follow_does_not_upscale_tiny_sprites(self) -> None:
        app, owns_app, panel = self._setup_panel()
        pane = panel._panes["before"]

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "tiny.png"
            Image.new("RGBA", (16, 16), (120, 220, 80, 255)).save(image_path, format="PNG")

            panel.resize(1200, 800)
            panel.show()
            app.processEvents()

            panel._set_pane_source(pane, image_path)
            panel._render_pane("before", pane, rescale_only=False)

            # Auto-follow should keep tiny sprites at real size (no automatic enlargement).
            self.assertEqual(pane.canvas.width(), 16)
            self.assertEqual(pane.canvas.height(), 16)

        panel.close()
        if owns_app and app is not None:
            app.quit()
if __name__ == "__main__":
    unittest.main()








