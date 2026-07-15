"""Application logging configuration helpers."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import tempfile


def _close_handlers(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass


def _file_handler(
    path: Path,
    *,
    level: int,
    formatter: logging.Formatter,
) -> logging.FileHandler | None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(path, encoding="utf-8")
    except OSError:
        return None
    handler.setFormatter(formatter)
    handler.setLevel(level)
    return handler


def _fallback_log_dir() -> Path:
    return Path(tempfile.gettempdir()) / "SpriteFactory" / "logs"


def configure_logging(log_dir: str | Path, *, level: int = logging.INFO) -> logging.Logger:
    """Configure app loggers and return the main app logger."""

    target_dir = Path(log_dir)
    log_file = target_dir / "image_engine_app.log"

    logger = logging.getLogger("image_engine_app")
    logger.setLevel(level)
    _close_handlers(logger)

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(level)
    logger.addHandler(stream_handler)

    active_log_dir = target_dir
    file_handler = _file_handler(log_file, level=level, formatter=formatter)
    if file_handler is None:
        active_log_dir = _fallback_log_dir()
        log_file = active_log_dir / f"image_engine_app_{os.getpid()}.log"
        file_handler = _file_handler(log_file, level=level, formatter=formatter)
    if file_handler is not None:
        logger.addHandler(file_handler)

    # Dedicated debug trace for batch workflows (UI + runner) to diagnose mid-run failures.
    batch_logger = logging.getLogger("image_engine_app.batch")
    batch_logger.setLevel(logging.DEBUG)
    _close_handlers(batch_logger)
    batch_file_handler = _file_handler(
        active_log_dir / "batch_debug.log",
        level=logging.DEBUG,
        formatter=formatter,
    )
    if batch_file_handler is not None:
        batch_logger.addHandler(batch_file_handler)
    batch_logger.propagate = True

    logger.propagate = False
    if file_handler is None:
        logger.warning("File logging unavailable; continuing with console logging")
    elif active_log_dir != target_dir:
        logger.warning("Primary log unavailable; using fallback log: %s", log_file)
    else:
        logger.debug("Logging configured at %s", log_file)
    return logger
