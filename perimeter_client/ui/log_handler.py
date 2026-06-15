"""将日志输出到 Qt 界面。"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, pyqtSignal


class LogEmitter(QObject):
    message = pyqtSignal(str)


class QtLogHandler(logging.Handler):
    def __init__(self, emitter: LogEmitter, level: int = logging.INFO) -> None:
        super().__init__(level)
        self._emitter = emitter
        self.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._emitter.message.emit(self.format(record))
        except RuntimeError:
            pass
