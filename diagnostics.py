"""Persistent, privacy-sanitized diagnostic logging. No Qt imports here."""

from __future__ import annotations

import logging
import os
import platform
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from gui.settings import sanitize_log

_HANDLER_MARKER = "_medical_redactor_diagnostic_handler"


class _SanitizingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return sanitize_log(super().format(record))


def get_log_path() -> Path:
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "logs" / "medical-redactor.log"
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        return base / "medical-redactor" / "logs" / "medical-redactor.log"
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Logs"
            / "medical-redactor"
            / "medical-redactor.log"
        )
    base = Path(
        os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))
    )
    return base / "medical-redactor" / "medical-redactor.log"


def display_log_path() -> str:
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        return r"%LOCALAPPDATA%\Programs\Medical Redactor\logs\medical-redactor.log"
    return str(get_log_path())


def configure_file_logging() -> Path | None:
    """Install one rotating root handler and never prevent app startup."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_MARKER, False):
            root.removeHandler(handler)
            handler.close()

    log_path = get_log_path()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_path,
            maxBytes=4 * 1024 * 1024,
            backupCount=2,
            encoding="utf-8",
        )
    except OSError:
        return None

    setattr(handler, _HANDLER_MARKER, True)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        _SanitizingFormatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"
        )
    )
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    logging.captureWarnings(True)

    logger = logging.getLogger(__name__)
    logger.info("Application startup")
    logger.info(
        "Runtime: platform=%s python=%s frozen=%s executable=%s",
        platform.platform(),
        platform.python_version(),
        getattr(sys, "frozen", False),
        sys.executable,
    )
    return log_path
