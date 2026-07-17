"""Network diagnostics and user-facing error messages for Web Sources."""

from __future__ import annotations

import re
import socket
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener, urlopen


WINDOWS_BLOCKED_ACCESS_TEXT = (
    "Windows blocked network access (WinError 10013). "
    "Check firewall, VPN, proxy, or antivirus web shield settings."
)


def normalize_network_error_message(detail: object) -> str:
    raw = " ".join(str(detail or "").split())
    lowered = raw.casefold()
    if "winerror 10013" in lowered or "forbidden by its access permissions" in lowered:
        return WINDOWS_BLOCKED_ACCESS_TEXT
    if "timed out" in lowered or "timeout" in lowered or "winerror 10060" in lowered:
        return "Network timeout: the website did not respond in time. Try again or scan fewer pages."

    http_match = re.search(r"http error\s+(\d{3})(?::\s*([^>]+))?", raw, flags=re.IGNORECASE)
    if http_match:
        return friendly_http_error(
            int(http_match.group(1)),
            reason=" ".join(str(http_match.group(2) or "").split()),
        )
    return raw or "Unknown network error"


def friendly_http_error(code: int, *, reason: str = "") -> str:
    reason_text = f" ({reason})" if reason else ""
    if code == 401:
        return "HTTP 401 (Unauthorized): this page needs authentication or cookies before scanning."
    if code == 403:
        return (
            "HTTP 403 (Forbidden): the website blocked automated scanning. "
            "Try a connection check or a direct file URL."
        )
    if code == 404:
        return "HTTP 404 (Not Found): the page or file URL no longer exists."
    if code == 429:
        return "HTTP 429 (Rate limited): wait briefly, then scan fewer pages on this website."
    if code in {500, 502, 503, 504}:
        return (
            f"HTTP {code}{reason_text}: the website or server failed before Sprite Factory could scan it. "
            "Try again later, scan fewer pages, or use a direct file URL."
        )
    if 400 <= code < 500:
        return f"HTTP {code}{reason_text}: the website rejected this request."
    if 500 <= code < 600:
        return f"HTTP {code}{reason_text}: the website or server failed. Try again later."
    return f"HTTP {code}{reason_text}"


def friendly_scan_results_failures(failures: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for entry in failures:
        text = " ".join(str(entry).split())
        scheme_at = text.find("://")
        separator = text.find(": ", scheme_at + 3 if scheme_at >= 0 else 0)
        if separator < 0:
            normalized.append(normalize_network_error_message(text))
            continue
        page = text[:separator]
        detail = text[separator + 2 :]
        normalized.append(f"{page}: {normalize_network_error_message(detail)}")
    return tuple(normalized)


def diagnose_url(raw_url: str) -> str:
    normalized = _normalize_diagnostics_url(raw_url)
    parsed = urlparse(normalized)
    host = (parsed.hostname or "").strip()
    if not host:
        raise ValueError("Connection check failed because the URL host is missing.")
    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)

    try:
        socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except Exception as exc:
        return f"Connection check: DNS lookup failed for {host} ({normalize_network_error_message(exc)})"
    try:
        with socket.create_connection((host, int(port)), timeout=4.0):
            pass
    except Exception as exc:
        if _is_socket_access_denied(exc):
            return f"Connection check: {WINDOWS_BLOCKED_ACCESS_TEXT}"
        return (
            f"Connection check: could not connect to {host}:{port} "
            f"({normalize_network_error_message(exc)})"
        )

    request = Request(normalized, headers={"User-Agent": "SpriteFactory/1.2 (Connection Check)"})
    try:
        with urlopen(request, timeout=8.0) as response:
            status = getattr(response, "status", None)
            code = int(status) if isinstance(status, int) else 200
            return f"Connection check passed: DNS, connection, and HTTP {code} for {host}:{port}"
    except Exception as first_exc:
        if _is_socket_access_denied(first_exc):
            return f"Connection check: {WINDOWS_BLOCKED_ACCESS_TEXT}"
        try:
            direct_opener = build_opener(ProxyHandler({}))
            with direct_opener.open(request, timeout=8.0) as response:
                status = getattr(response, "status", None)
                code = int(status) if isinstance(status, int) else 200
                return (
                    f"Connection check passed without proxy: "
                    f"DNS, connection, and HTTP {code} for {host}:{port}"
                )
        except Exception as second_exc:
            if _is_socket_access_denied(second_exc):
                return f"Connection check: {WINDOWS_BLOCKED_ACCESS_TEXT}"
            detail = normalize_network_error_message(first_exc)
            return f"Connection check partial: DNS and connection passed, but the page request failed ({detail})"


def _normalize_diagnostics_url(raw_url: str) -> str:
    candidate = str(raw_url or "").strip()
    if not candidate:
        raise ValueError("Missing page URL for the connection check.")
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Invalid URL. Use http(s)://domain/path.")
    return candidate


def _is_socket_access_denied(exc: Exception) -> bool:
    reason = getattr(exc, "reason", exc)
    if getattr(reason, "winerror", None) == 10013:
        return True
    message = str(reason or exc).casefold()
    return "winerror 10013" in message or "forbidden by its access permissions" in message
