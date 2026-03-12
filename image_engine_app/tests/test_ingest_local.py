"""Tests for local file/folder ingestion core functions."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ingest.local_ingest import (  # noqa: E402
    build_local_ingest_queue,
    scan_local_files,
)
from engine.models import AssetFormat, SourceType  # noqa: E402


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

            result = build_local_ingest_queue([root], recursive=True, preserve_structure=True)

            self.assertEqual(len(result.queue), 3)
            self.assertEqual(len(result.duplicates), 1)
            self.assertEqual(len(result.unsupported), 1)
            self.assertTrue(any(path.name == "dup_copy.png" for path in result.duplicates))
            self.assertTrue(any(path.name == "notes.txt" for path in result.unsupported))

            queue_paths = [entry.queue_path for entry in result.queue]
            self.assertIn("input_root/a.png", queue_paths)
            self.assertIn("input_root/nested/b.JPG", queue_paths)
            self.assertIn("input_root/nested/deeper/c.gif", queue_paths)
            self.assertTrue(all(entry.asset.source_type is SourceType.FOLDER_ITEM for entry in result.queue))

            formats = {entry.asset.format for entry in result.queue}
            self.assertEqual(formats, {AssetFormat.PNG, AssetFormat.JPG, AssetFormat.GIF})

    def test_flatten_option_and_non_recursive_folder_scan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "flat_test"
            _write_file(root / "top.png", _png_bytes(b"top"))
            _write_file(root / "nested" / "hidden.png", _png_bytes(b"nested"))

            scanned = scan_local_files([root], recursive=False)
            self.assertEqual(len(scanned), 1)
            self.assertEqual(scanned[0].relative_path.as_posix(), "top.png")

            result = build_local_ingest_queue([root], recursive=False, flatten=True)
            self.assertEqual(len(result.queue), 1)
            self.assertEqual(result.queue[0].queue_path, "top.png")

    def test_signature_mismatch_is_marked_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fake_png = root / "fake.png"
            _write_file(fake_png, _jpg_bytes(b"pretend-jpeg"))

            result = build_local_ingest_queue([fake_png], preserve_structure=False)

            self.assertEqual(len(result.queue), 0)
            self.assertEqual(result.duplicates, [])
            self.assertEqual(result.unsupported, [fake_png.resolve()])

    def test_duplicate_detection_can_be_disabled_for_file_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            file_one = root / "one.png"
            file_two = root / "two.png"
            _write_file(file_one, _png_bytes(b"same-content"))
            _write_file(file_two, _png_bytes(b"same-content"))

            result = build_local_ingest_queue(
                [file_one, file_two],
                preserve_structure=False,
                dedupe_by_hash=False,
            )

            self.assertEqual(len(result.queue), 2)
            self.assertEqual(result.duplicates, [])
            self.assertEqual([entry.queue_path for entry in result.queue], ["one.png", "two.png"])
            self.assertTrue(all(entry.asset.source_type is SourceType.FILE for entry in result.queue))


if __name__ == "__main__":
    unittest.main()
