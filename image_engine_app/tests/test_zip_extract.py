"""Safety and path-preservation tests for shared ZIP extraction."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import zipfile

from image_engine_app.engine.ingest.zip_extract import ZipExtractError, extract_images_only


class ZipExtractTests(unittest.TestCase):
    def test_extract_preserves_safe_member_paths_and_ignores_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "bundle.zip"
            output = root / "output"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("nested/sprite.png", b"image")
                archive.writestr("../escape.png", b"escape")
                archive.writestr("notes.txt", b"ignored")

            extracted = extract_images_only(str(archive_path), str(output), allowed_exts={".png"})

            self.assertEqual([str((output / "nested" / "sprite.png").resolve())], extracted)
            self.assertFalse((root / "escape.png").exists())

    def test_extract_rejects_member_above_size_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "large.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("large.png", b"12345")

            with self.assertRaises(ZipExtractError):
                extract_images_only(
                    str(archive_path),
                    str(root / "output"),
                    allowed_exts={".png"},
                    max_member_bytes=4,
                )


if __name__ == "__main__":
    unittest.main()
