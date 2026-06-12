"""自定义 UI 组件。"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QWidget


class StatusLight(QWidget):
    """圆形状态指示灯。"""

    OFF = "off"
    ON = "on"
    UNKNOWN = "unknown"

    _COLORS = {
        OFF: QColor("#E53935"),
        ON: QColor("#43A047"),
        UNKNOWN: QColor("#9E9E9E"),
    }

    def __init__(self, diameter: int = 28, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = self.UNKNOWN
        self._diameter = diameter
        self.setFixedSize(diameter + 8, diameter + 8)

    def set_state(self, state: str) -> None:
        if state not in self._COLORS:
            state = self.UNKNOWN
        self._state = state
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = self._COLORS[self._state]
        margin = 4
        size = self._diameter

        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(margin, margin, size, size)

        highlight = QColor(255, 255, 255, 90)
        painter.setBrush(highlight)
        painter.drawEllipse(margin + 4, margin + 4, size // 3, size // 3)
