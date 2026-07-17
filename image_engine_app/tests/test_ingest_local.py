"""Tests for local file/folder ingestion core functions."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
import zipfile


from image_engine_app.engine.ingest.local_ingest import (  # noqa: E402
    ingest_local_sources,
    scan_local_files,
)
from image_engine_app.engine.models import AssetFormat, SourceType  # noqa: E402


def _write_file(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _png_bytes(payload: bytes = b"PNGDATA") -> bytes:
    return b"\x89PNG\r\n\x1a\n" + payload


def _jpg_bytes(payload: bytes = b"JPGDATA") -> bytes:
    return b"\xff\xd8\xff\xe0" + payload + b"\xff\xd9"


def _gif_bytes(payload: bytes = b"GIFDATA") -> bytes:
    return b"GIF89a" + payload


class LocalIngestTests(unittest.TestCase):
    def test_recursive_scan_preserve_structure_and_dedupe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "input_root"
            _write_file(root / "a.png", _png_bytes(b"alpha"))
            _write_file(root / "nested" / "b.JPG", _jpg_bytes(b"bravo"))
            _write_file(root / "nested" / "dup_copy.png", _png_bytes(b"alpha"))  # duplicate of a.png
            _write_file(root / "nested" / "deeper" / "c.gif", _gif_bytes(b"charlie"))
            _write_file(root / "notes.txt", b"unsupported")

            result = ingest_local_sources([root], recursive=True, preserve_structure=True)

            self.assertEqual(len(result.entries), 3)
            self.assertEqual(len(result.duplicates), 1)
            self.assertEqual(len(result.unsupported), 1)
            self.assertTrue(any(Path(path).name == "dup_copy.png" for path in result.duplicates))
            self.assertTrue(any(Path(path).name == "notes.txt" for path in result.unsupported))

            queue_paths = [entry.queue_path for entry in result.entries]
            self.assertIn("input_root/a.png", queue_paths)
            self.assertIn("input_root/nested/b.JPG", queue_paths)
            self.assertIn("input_root/nested/deeper/c.gif", queue_paths)
            self.assertTrue(all(entry.asset.source_type is SourceType.FOLDER_ITEM for entry in result.entries))

            formats = {entry.asset.format for entry in result.entries}
            self.assertEqual(formats, {AssetFormat.PNG, AssetFormat.JPG, AssetFormat.GIF})

    def test_flatten_option_and_non_recursive_folder_scan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "flat_test"
            _write_file(root / "top.png", _png_bytes(b"top"))
            _write_file(root / "nested" / "hidden.png", _png_bytes(b"nested"))

            scanned = scan_local_files([root], recursive=False)
            self.assertEqual(len(scanned), 1)
            self.assertEqual(scanned[0].relative_path.as_posix(), "top.png")

            result = ingest_local_sources([root], recursive=False, flatten=True)
            self.assertEqual(len(result.entries), 1)
            self.assertEqual(result.entries[0].queue_path, "top.png")

    def test_signature_mismatch_is_marked_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fake_png = root / "fake.png"
            _write_file(fake_png, _jpg_bytes(b"pretend-jpeg"))

            result = ingest_local_sources([fake_png], preserve_structure=False)

            self.assertEqual(len(result.entries), 0)
            self.assertEqual(result.duplicates, ())
            self.assertEqual(result.unsupported, (str(fake_png.resolve()),))

    def test_duplicate_detection_can_be_disabled_for_file_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            file_one = root / "one.png"
            file_two = root / "two.png"
            _write_file(file_one, _png_bytes(b"same-content"))
            _write_file(file_two, _png_bytes(b"same-content"))

            result = ingest_local_sources(
                [file_one, file_two],
                preserve_structure=False,
                dedupe_by_hash=False,
            )

            self.assertEqual(len(result.entries), 2)
            self.assertEqual(result.duplicates, ())
            self.assertEqual([entry.queue_path for entry in result.entries], ["one.png", "two.png"])
            self.assertTrue(all(entry.asset.source_type is SourceType.FILE for entry in result.entries))

    def test_zip_and_direct_files_share_one_result_and_preserve_archive_members(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            direct = root / "direct.png"
            archive = root / "bundle.zip"
            extract_root = root / "extract"
            _write_file(direct, _png_bytes(b"direct"))
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("nested/sprite.gif", _gif_bytes(b"animated"))
                bundle.writestr("notes.txt", b"ignored")

            result = ingest_local_sources(
                [direct, archive],
                preserve_structure=True,
                archive_extract_root=extract_root,
            )

            self.assertEqual(2, len(result.entries))
            by_name = {entry.asset.original_name: entry for entry in result.entries}
            self.assertIn("direct.png", by_name)
            self.assertIn("sprite.gif", by_name)
            archived = by_name["sprite.gif"]
            self.assertEqual(str(archive.resolve()), archived.asset.source_uri)
            self.assertTrue(Path(archived.asset.cache_path).exists())
            self.assertEqual("bundle/nested/sprite.gif", archived.queue_path)


if __name__ == "__main__":
    unittest.main()


