#!/usr/bin/env python3
"""周界拦截上位机入口。"""

import sys

from PyQt6.QtWidgets import QApplication

from perimeter_client.ui import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("周界拦截上位机")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
