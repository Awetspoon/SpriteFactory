"""Application logging configuration helpers."""

from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(log_dir: str | Path, *, level: int = logging.INFO) -> logging.Logger:
    """Configure app loggers and return the main app logger."""

    target_dir = Path(log_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    log_file = target_dir / "image_engine_app.log"

    logger = logging.getLogger("image_engine_app")
    logger.setLevel(level)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(level)
    logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    logger.addHandler(file_handler)

    # Dedicated debug trace for batch workflows (UI + runner) to diagnose mid-run failures.
    batch_logger = logging.getLogger("image_engine_app.batch")
    batch_logger.setLevel(logging.DEBUG)
    batch_logger.handlers.clear()
    batch_file_handler = logging.FileHandler(target_dir / "batch_debug.log", encoding="utf-8")
    batch_file_handler.setFormatter(formatter)
    batch_file_handler.setLevel(logging.DEBUG)
    batch_logger.addHandler(batch_file_handler)
    batch_logger.propagate = True

    logger.propagate = False
    logger.debug("Logging configured at %s", log_file)
    return logger
