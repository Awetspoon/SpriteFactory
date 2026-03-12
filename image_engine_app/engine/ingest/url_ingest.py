"""URL ingestion core functions with cache download and validation (Prompt 4)."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import imghdr
from pathlib import Path
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener, urlopen


class UrlIngestError(Exception):
    """Base exception for URL ingest failures."""


class DownloadCancelledError(UrlIngestError):
    """Raised when a download is cancelled by user request."""


class UrlValidationError(UrlIngestError):
    """Raised when a URL fails validation rules."""


class MimeValidationError(UrlIngestError):
    """Raised when a response MIME type is unsupported or mismatched."""


class SignatureValidationError(UrlIngestError):
    """Raised when file signature validation fails."""


class FileSizeGuardError(UrlIngestError):
    """Raised when a download exceeds the configured byte limit."""


class ResolutionGuardError(UrlIngestError):
    """Raised when detected dimensions exceed configured resolution limits."""


@dataclass
class DownloadGuards:
    """Safety guards for URL downloads."""

    max_bytes: int | None = 100 * 1024 * 1024
    max_width: int | None = None
    max_height: int | None = None
    max_pixels: int | None = None


@dataclass
class DownloadedUrlAsset:
    """Metadata for a cached download result."""

    url: str
    cache_path: Path
    mime_type: str | None
    detected_format: str
    bytes_downloaded: int
    dimensions: tuple[int, int] | None


@dataclass
class StreamPreviewAsset:
    """Metadata from a bounded stream preview request."""

    url: str
    mime_type: str | None
    detected_format: str
    bytes_sampled: int
    dimensions: tuple[int, int] | None
    truncated: bool


SUPPORTED_MIME_TO_FORMATS: dict[str, set[str]] = {
    "image/jpeg": {"jpeg"},
    "image/jpg": {"jpeg"},
    "image/png": {"png"},
    "image/webp": {"webp"},
    "image/gif": {"gif"},
    "image/bmp": {"bmp"},
    "image/x-icon": {"ico"},
    "image/vnd.microsoft.icon": {"ico"},
    "image/tiff": {"tiff"},
}

FORMAT_TO_EXTENSION: dict[str, str] = {
    "jpeg": ".jpg",
    "png": ".png",
    "webp": ".webp",
    "gif": ".gif",
    "bmp": ".bmp",
    "ico": ".ico",
    "tiff": ".tiff",
}

USER_AGENT = "ImageEngine/0.1 (Prompt4 URL Ingest)"


def validate_url(url: str) -> str:
    """Validate and normalize a URL for ingestion."""

    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in {"http", "https"}:
        raise UrlValidationError("Only http/https URLs are supported")
    if not parsed.netloc:
        raise UrlValidationError("URL must include a host")
    return url.strip()


def _is_socket_access_denied(exc: Exception) -> bool:
    reason = getattr(exc, "reason", exc)
    win_error = getattr(reason, "winerror", None)
    if win_error == 10013:
        return True

    message = str(reason or exc).lower()
    return "winerror 10013" in message or "forbidden by its access permissions" in message


def _open_with_socket_fallback(
    request: Request,
    *,
    timeout: float,
    opener: Callable[..., object] | None,
) -> object:
    open_fn = opener or urlopen
    try:
        return open_fn(request, timeout=timeout)
    except Exception as exc:
        if opener is not None or not _is_socket_access_denied(exc):
            raise

        direct_opener = build_opener(ProxyHandler({}))
        return direct_opener.open(request, timeout=timeout)


def stream_preview_mode_stub(
    url: str,
    *,
    max_preview_bytes: int = 65536,
    timeout: float = 10.0,
    opener: Callable[..., object] | None = None,
    request_headers: dict[str, str] | None = None,
) -> StreamPreviewAsset:
    """Fetch a bounded byte sample and return best-effort preview metadata."""

    if max_preview_bytes <= 0:
        raise ValueError("max_preview_bytes must be > 0")

    normalized_url = validate_url(url)
    range_end = max_preview_bytes - 1
    headers = {
        "User-Agent": USER_AGENT,
        "Range": f"bytes=0-{range_end}",
    }
    if request_headers:
        for key, value in request_headers.items():
            if key and value:
                headers[str(key)] = str(value)

    request = Request(normalized_url, headers=headers)

    try:
        response_obj = _open_with_socket_fallback(
            request,
            timeout=timeout,
            opener=opener,
        )
        with response_obj as response:
            mime_type = _read_header(response, "Content-Type")
            sampled = response.read(max_preview_bytes + 1)
    except HTTPError as exc:
        raise UrlIngestError(f"HTTP error {exc.code}") from exc
    except URLError as exc:
        raise UrlIngestError("Preview request failed") from exc
    except TimeoutError as exc:
        raise UrlIngestError("Preview request timed out") from exc

    if not sampled:
        raise SignatureValidationError("Could not detect supported image signature")

    truncated = len(sampled) > max_preview_bytes
    header_bytes = sampled[:max_preview_bytes]
    detected_format = detect_signature_format(header_bytes)
    if not detected_format:
        raise SignatureValidationError("Could not detect supported image signature")

    _validate_mime_against_signature(mime_type, detected_format)
    dimensions = parse_image_dimensions(header_bytes, detected_format)

    return StreamPreviewAsset(
        url=normalized_url,
        mime_type=mime_type,
        detected_format=detected_format,
        bytes_sampled=len(header_bytes),
        dimensions=dimensions,
        truncated=truncated,
    )


def detect_signature_format(header_bytes: bytes) -> str | None:
    """Detect image format from magic bytes / signature."""

    if header_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header_bytes.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if header_bytes.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if header_bytes.startswith(b"BM"):
        return "bmp"
    if len(header_bytes) >= 12 and header_bytes[:4] == b"RIFF" and header_bytes[8:12] == b"WEBP":
        return "webp"
    if header_bytes.startswith(b"\x00\x00\x01\x00"):
        return "ico"
    if header_bytes.startswith((b"II*\x00", b"MM\x00*")):
        return "tiff"

    # imghdr is deprecated but still available in Python 3.11 and useful as a fallback here.
    fallback = imghdr.what(None, header_bytes)
    return fallback


def parse_image_dimensions(data: bytes, detected_format: str) -> tuple[int, int] | None:
    """Best-effort dimension parsing for guard checks."""

    if detected_format == "png" and len(data) >= 24:
        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
        return (width, height)

    if detected_format == "gif" and len(data) >= 10:
        width = int.from_bytes(data[6:8], "little")
        height = int.from_bytes(data[8:10], "little")
        return (width, height)

    if detected_format == "bmp" and len(data) >= 26:
        width = int.from_bytes(data[18:22], "little", signed=True)
        height = int.from_bytes(data[22:26], "little", signed=True)
        return (abs(width), abs(height))

    if detected_format == "jpeg":
        return _parse_jpeg_dimensions(data)

    if detected_format == "webp":
        return _parse_webp_dimensions(data)

    if detected_format == "ico":
        return _parse_ico_dimensions(data)

    if detected_format == "tiff":
        return _parse_tiff_dimensions(data)

    return None


def _parse_jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 4 or not data.startswith(b"\xff\xd8"):
        return None

    i = 2
    data_len = len(data)
    while i + 1 < data_len:
        if data[i] != 0xFF:
            i += 1
            continue

        while i < data_len and data[i] == 0xFF:
            i += 1
        if i >= data_len:
            break

        marker = data[i]
        i += 1

        if marker in {0xD8, 0xD9}:
            continue
        if marker == 0xDA:
            break
        if i + 1 >= data_len:
            break

        segment_len = int.from_bytes(data[i : i + 2], "big")
        if segment_len < 2 or i + segment_len > data_len:
            break

        sof_markers = {
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        }
        if marker in sof_markers and segment_len >= 7:
            base = i + 2
            if base + 5 <= data_len:
                height = int.from_bytes(data[base + 1 : base + 3], "big")
                width = int.from_bytes(data[base + 3 : base + 5], "big")
                return (width, height)

        i += segment_len

    return None


def _parse_webp_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 20:
        return None
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None

    offset = 12
    data_len = len(data)
    while offset + 8 <= data_len:
        chunk_type = data[offset : offset + 4]
        chunk_size = int.from_bytes(data[offset + 4 : offset + 8], "little")
        payload_start = offset + 8
        payload_end = payload_start + chunk_size
        if payload_end > data_len:
            break
        payload = data[payload_start:payload_end]

        if chunk_type == b"VP8X" and len(payload) >= 10:
            width = int.from_bytes(payload[4:7], "little") + 1
            height = int.from_bytes(payload[7:10], "little") + 1
            return (width, height)

        if chunk_type == b"VP8 " and len(payload) >= 10:
            if payload[3:6] == b"\x9d\x01\x2a":
                width = int.from_bytes(payload[6:8], "little") & 0x3FFF
                height = int.from_bytes(payload[8:10], "little") & 0x3FFF
                return (width, height)

        if chunk_type == b"VP8L" and len(payload) >= 5:
            if payload[0] == 0x2F:
                b1, b2, b3, b4 = payload[1:5]
                width = 1 + ((b1 | ((b2 & 0x3F) << 8)) & 0x3FFF)
                height = 1 + (((b2 >> 6) | (b3 << 2) | ((b4 & 0x0F) << 10)) & 0x3FFF)
                return (width, height)

        # Chunks are padded to even sizes.
        offset = payload_end + (chunk_size % 2)

    return None


def _parse_ico_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 22:
        return None

    reserved = int.from_bytes(data[0:2], "little")
    icon_type = int.from_bytes(data[2:4], "little")
    count = int.from_bytes(data[4:6], "little")
    if reserved != 0 or icon_type not in {1, 2} or count < 1:
        return None

    width_byte = data[6]
    height_byte = data[7]
    width = 256 if width_byte == 0 else int(width_byte)
    height = 256 if height_byte == 0 else int(height_byte)
    return (width, height)


def _parse_tiff_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 8:
        return None

    byte_order = data[0:2]
    if byte_order == b"II":
        endian = "little"
    elif byte_order == b"MM":
        endian = "big"
    else:
        return None

    magic = int.from_bytes(data[2:4], endian)
    if magic != 42:
        return None

    ifd_offset = int.from_bytes(data[4:8], endian)
    if ifd_offset + 2 > len(data):
        return None

    entry_count = int.from_bytes(data[ifd_offset : ifd_offset + 2], endian)
    entry_base = ifd_offset + 2
    width: int | None = None
    height: int | None = None

    for idx in range(entry_count):
        offset = entry_base + idx * 12
        if offset + 12 > len(data):
            break
        tag = int.from_bytes(data[offset : offset + 2], endian)
        if tag not in {256, 257}:
            continue
        type_id = int.from_bytes(data[offset + 2 : offset + 4], endian)
        count = int.from_bytes(data[offset + 4 : offset + 8], endian)
        raw_value = data[offset + 8 : offset + 12]
        value = _parse_tiff_scalar_value(
            type_id=type_id,
            count=count,
            raw_value=raw_value,
            data=data,
            endian=endian,
        )
        if value is None:
            continue
        if tag == 256:
            width = value
        else:
            height = value
        if width is not None and height is not None:
            return (width, height)

    return None


def _parse_tiff_scalar_value(
    *,
    type_id: int,
    count: int,
    raw_value: bytes,
    data: bytes,
    endian: str,
) -> int | None:
    if count <= 0:
        return None

    if type_id == 3:  # SHORT
        if count == 1:
            return int.from_bytes(raw_value[0:2], endian)
        value_offset = int.from_bytes(raw_value, endian)
        value_size = count * 2
        if value_offset + value_size > len(data):
            return None
        return int.from_bytes(data[value_offset : value_offset + 2], endian)

    if type_id == 4:  # LONG
        if count == 1:
            return int.from_bytes(raw_value, endian)
        value_offset = int.from_bytes(raw_value, endian)
        value_size = count * 4
        if value_offset + value_size > len(data):
            return None
        return int.from_bytes(data[value_offset : value_offset + 4], endian)

    return None


def _validate_mime_against_signature(mime_type: str | None, detected_format: str) -> None:
    if not mime_type:
        return

    normalized = mime_type.split(";")[0].strip().lower()
    allowed_formats = SUPPORTED_MIME_TO_FORMATS.get(normalized)
    if allowed_formats is not None:
        if detected_format not in allowed_formats:
            raise MimeValidationError(
                f"MIME/signature mismatch: mime={mime_type!r}, signature={detected_format!r}"
            )
        return

    # Some hosts return generic/non-image MIME while still serving valid bytes.
    if normalized in {"application/octet-stream", "binary/octet-stream", "application/download"}:
        return

    # Unknown image/* subtypes are accepted when signature detection already succeeded.
    if normalized.startswith("image/"):
        return


def _check_resolution_guards(
    dimensions: tuple[int, int] | None,
    guards: DownloadGuards,
) -> None:
    if dimensions is None:
        return
    width, height = dimensions
    if guards.max_width is not None and width > guards.max_width:
        raise ResolutionGuardError(f"Width {width} exceeds max_width={guards.max_width}")
    if guards.max_height is not None and height > guards.max_height:
        raise ResolutionGuardError(f"Height {height} exceeds max_height={guards.max_height}")
    if guards.max_pixels is not None and (width * height) > guards.max_pixels:
        raise ResolutionGuardError(
            f"Pixel count {width * height} exceeds max_pixels={guards.max_pixels}"
        )


def download_url_to_cache(
    url: str,
    cache_dir: str | Path,
    *,
    guards: DownloadGuards | None = None,
    retries: int = 2,
    backoff_seconds: float = 0.25,
    timeout: float = 15.0,
    chunk_size: int = 64 * 1024,
    sleep_func: Callable[[float], None] = time.sleep,
    opener: Callable[..., object] | None = None,
    request_headers: dict[str, str] | None = None,
    cancel_requested: Callable[[], bool] | None = None,
) -> DownloadedUrlAsset:
    """
    Download a URL to a cache directory with guard checks and retry/backoff.

    Retries apply to transient network errors and HTTP 5xx responses.
    """

    normalized_url = validate_url(url)
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    active_guards = guards or DownloadGuards()
    url_hash = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        if cancel_requested and cancel_requested():
            raise DownloadCancelledError("Download cancelled by user")
        try:
            return _download_once(
                normalized_url,
                cache_path,
                url_hash=url_hash,
                guards=active_guards,
                timeout=timeout,
                chunk_size=chunk_size,
                opener=opener,
                request_headers=request_headers,
                cancel_requested=cancel_requested,
            )
        except HTTPError as exc:
            last_error = exc
            if exc.code < 500:
                raise UrlIngestError(f"HTTP error {exc.code}") from exc
        except (URLError, TimeoutError) as exc:
            last_error = exc
        except UrlIngestError:
            raise

        if attempt >= retries:
            break
        sleep_func(backoff_seconds * (2**attempt))

    raise UrlIngestError("URL download failed after retries") from last_error


def _download_once(
    url: str,
    cache_dir: Path,
    *,
    url_hash: str,
    guards: DownloadGuards,
    timeout: float,
    chunk_size: int,
    opener: Callable[..., object] | None,
    request_headers: dict[str, str] | None,
    cancel_requested: Callable[[], bool] | None,
) -> DownloadedUrlAsset:
    headers = {"User-Agent": USER_AGENT}
    if request_headers:
        for key, value in request_headers.items():
            if key and value:
                headers[str(key)] = str(value)
    request = Request(url, headers=headers)
    response_obj = _open_with_socket_fallback(request, timeout=timeout, opener=opener)

    with response_obj as response:
        mime_type = _read_header(response, "Content-Type")
        header_probe = bytearray()
        total_bytes = 0
        dimensions: tuple[int, int] | None = None
        detected_format: str | None = None
        temp_path = cache_dir / f"{url_hash}.part"

        try:
            with temp_path.open("wb") as handle:
                while True:
                    if cancel_requested and cancel_requested():
                        raise DownloadCancelledError("Download cancelled by user")
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if guards.max_bytes is not None and total_bytes > guards.max_bytes:
                        raise FileSizeGuardError(
                            f"Download exceeded max_bytes={guards.max_bytes}"
                        )

                    if len(header_probe) < 4096:
                        needed = 4096 - len(header_probe)
                        header_probe.extend(chunk[:needed])

                        if detected_format is None and len(header_probe) >= 12:
                            detected_format = detect_signature_format(bytes(header_probe))
                            if detected_format:
                                _validate_mime_against_signature(mime_type, detected_format)

                        if detected_format and dimensions is None:
                            dimensions = parse_image_dimensions(bytes(header_probe), detected_format)
                            _check_resolution_guards(dimensions, guards)

                    handle.write(chunk)

            if detected_format is None:
                detected_format = detect_signature_format(bytes(header_probe))
            if not detected_format:
                raise SignatureValidationError("Could not detect supported image signature")

            _validate_mime_against_signature(mime_type, detected_format)
            if dimensions is None:
                dimensions = parse_image_dimensions(bytes(header_probe), detected_format)
            _check_resolution_guards(dimensions, guards)

            final_path = cache_dir / f"{url_hash}{FORMAT_TO_EXTENSION.get(detected_format, '.bin')}"
            if final_path.exists():
                final_path.unlink()
            temp_path.replace(final_path)
            return DownloadedUrlAsset(
                url=url,
                cache_path=final_path,
                mime_type=mime_type,
                detected_format=detected_format,
                bytes_downloaded=total_bytes,
                dimensions=dimensions,
            )
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise


def _read_header(response: object, header_name: str) -> str | None:
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    if hasattr(headers, "get"):
        return headers.get(header_name)
    return None


def _cli(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Download an image URL into cache")
    parser.add_argument("url", help="http/https image URL")
    parser.add_argument("cache_dir", help="Cache directory path")
    parser.add_argument("--max-bytes", type=int, default=10 * 1024 * 1024)
    parser.add_argument("--max-pixels", type=int, default=None)
    args = parser.parse_args(argv)

    asset = download_url_to_cache(
        args.url,
        args.cache_dir,
        guards=DownloadGuards(max_bytes=args.max_bytes, max_pixels=args.max_pixels),
    )
    print(f"Cached: {asset.cache_path}")
    print(f"Format: {asset.detected_format}")
    print(f"Bytes: {asset.bytes_downloaded}")
    if asset.dimensions:
        print(f"Dimensions: {asset.dimensions[0]}x{asset.dimensions[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())







