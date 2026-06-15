#!/usr/bin/env python3
"""周界拦截上位机入口。"""

import sys

from PyQt6.QtWidgets import QApplication

from perimeter_client.config import load_config
from perimeter_client.logging import get_logger, setup_logging
from perimeter_client.ui import MainWindow


def main() -> int:
    config = load_config()
    log_path = setup_logging(config)
    logger = get_logger("app")
    logger.info("周界拦截上位机启动")
    logger.info("日志文件: %s", log_path)

    app = QApplication(sys.argv)
    app.setApplicationName("周界拦截上位机")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
