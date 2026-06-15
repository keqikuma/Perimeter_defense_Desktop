"""日志初始化与格式化。"""

from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from perimeter_client.config import AppConfig
from perimeter_client.paths import app_base_dir

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_initialized = False
_log_file: Path | None = None


def log_file_path() -> Path | None:
    return _log_file


def format_hex(data: bytes) -> str:
    return " ".join(f"{byte:02X}" for byte in data)


def setup_logging(config: AppConfig) -> Path:
    global _initialized, _log_file

    log_dir = app_base_dir() / config.log_directory
    log_dir.mkdir(parents=True, exist_ok=True)
    _log_file = log_dir / "perimeter_client.log"

    root = logging.getLogger("perimeter_client")
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    file_handler = TimedRotatingFileHandler(
        _log_file,
        when="midnight",
        interval=1,
        backupCount=config.log_backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(getattr(logging, config.log_level.upper(), logging.DEBUG))
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    root.addHandler(file_handler)

    logging.getLogger().setLevel(logging.WARNING)
    _initialized = True
    return _log_file


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"perimeter_client.{name}")
