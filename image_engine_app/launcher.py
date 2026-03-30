"""Repository-aware launcher for Sprite Factory."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys

from image_engine_app.app.paths import resolve_app_data_root

RUNTIME_LAYOUT_VERSION = "2026-03-12-web-sources-v2"
LEGACY_REPO_RUNTIME_DIR_NAME = "_runtime_data"
LEGACY_RUNTIME_ENV_VAR = "SPRITEFACTORY_RUNTIME_DIR"


def _repo_root() -> Path:
    package_root = Path(__file__).resolve().parent
    candidate = package_root.parent
    if (candidate / "image_engine_app").is_dir() and (candidate / "main.py").exists():
        return candidate
    return Path.cwd()


def _legacy_repo_runtime_dir() -> Path:
    return _repo_root() / LEGACY_REPO_RUNTIME_DIR_NAME


def _default_runtime_dir() -> Path:
    return resolve_app_data_root()


def _extract_cli_app_data_dir(args: list[str]) -> Path | None:
    for index, arg in enumerate(args):
        if arg == "--app-data-dir":
            if index + 1 >= len(args):
                return None
            return Path(args[index + 1]).expanduser().resolve()
        if arg.startswith("--app-data-dir="):
            return Path(arg.split("=", 1)[1]).expanduser().resolve()
    return None


def _resolve_runtime_dir(args: list[str]) -> tuple[Path, bool]:
    cli_value = _extract_cli_app_data_dir(args)
    if cli_value is not None:
        return cli_value, False

    legacy_env = os.environ.get(LEGACY_RUNTIME_ENV_VAR)
    if legacy_env:
        return Path(legacy_env).expanduser().resolve(), True

    return _default_runtime_dir().resolve(), False


def _is_help_request(args: list[str]) -> bool:
    return any(arg in {"-h", "--help"} for arg in args)


def _migrate_legacy_repo_runtime_dir(destination_dir: Path) -> None:
    legacy_dir = _legacy_repo_runtime_dir()
    if (not legacy_dir.exists()) or legacy_dir.resolve() == destination_dir.resolve():
        return
    if destination_dir.exists():
        return

    destination_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(legacy_dir), str(destination_dir))
    except OSError:
        return


def _clear_legacy_autosaves(runtime_dir: Path) -> None:
    sessions_dir = runtime_dir / "sessions"
    if not sessions_dir.exists():
        return
    for path in sessions_dir.glob("autosave_*.json"):
        try:
            path.unlink()
        except OSError:
            continue


def _migrate_runtime_layout(runtime_dir: Path) -> None:
    stamp_path = runtime_dir / ".runtime_layout_version"
    current_version = stamp_path.read_text(encoding="utf-8").strip() if stamp_path.exists() else ""
    if current_version == RUNTIME_LAYOUT_VERSION:
        return

    for target in (
        runtime_dir / "cache" / "web_sources",
        runtime_dir / "cache" / "webpage_scan",
    ):
        if not target.exists():
            continue
        if target.is_dir():
            for child in sorted(target.rglob("*"), key=lambda p: len(p.parts), reverse=True):
                try:
                    if child.is_file() or child.is_symlink():
                        child.unlink()
                    else:
                        child.rmdir()
                except OSError:
                    continue
            try:
                target.rmdir()
            except OSError:
                pass
        else:
            try:
                target.unlink()
            except OSError:
                pass

    stamp_path.write_text(RUNTIME_LAYOUT_VERSION, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if _is_help_request(args):
        from image_engine_app.app.main import main as app_main

        return int(app_main(args))

    runtime_dir, inject_override = _resolve_runtime_dir(args)
    _migrate_legacy_repo_runtime_dir(runtime_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    _migrate_runtime_layout(runtime_dir)
    _clear_legacy_autosaves(runtime_dir)

    if inject_override:
        args = ["--app-data-dir", str(runtime_dir), *args]

    from image_engine_app.app.main import main as app_main

    return int(app_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
