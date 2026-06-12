"""后台线程执行网关通信，避免阻塞 UI。"""

from __future__ import annotations

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from perimeter_client.client import GatewayClient, GatewayError
from perimeter_client.config import AppConfig


class GatewayWorker(QObject):
    finished = pyqtSignal()
    failed = pyqtSignal(str)
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    ip_scanned = pyqtSignal(str, int)
    ip_applied = pyqtSignal(str, int)
    strike_changed = pyqtSignal(bool)
    temperature_updated = pyqtSignal(float)
    command_done = pyqtSignal(str, str)

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self._config = config
        self._client = GatewayClient(config)
        self._host = config.host
        self._port = config.port

    def update_target(self, host: str, port: int) -> None:
        self._host = host
        self._port = port

    def update_config(self, config: AppConfig) -> None:
        self._config = config
        self._client = GatewayClient(config)

    @property
    def is_connected(self) -> bool:
        return self._client.connected

    def scan_ip(self) -> None:
        try:
            ip, prefix = self._client.query_gateway_ip(self._host, self._port)
            self.ip_scanned.emit(ip, prefix)
        except GatewayError as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def connect_gateway(self) -> None:
        try:
            self._client.connect(self._host, self._port)
            self.connected.emit()
        except GatewayError as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def disconnect_gateway(self) -> None:
        self._client.disconnect()
        self.disconnected.emit()
        self.finished.emit()

    def power_on(self) -> None:
        try:
            payload = self._client.power_on()
            self.command_done.emit("电源开启", payload.hex().upper())
        except GatewayError as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def power_off(self) -> None:
        try:
            payload = self._client.power_off()
            self.command_done.emit("电源关闭", payload.hex().upper())
        except GatewayError as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def strike_on(self) -> None:
        try:
            self._client.signal_on()
            status = self._client.query_signal_status()
            self.strike_changed.emit(status)
        except GatewayError as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def strike_off(self) -> None:
        try:
            self._client.signal_off()
            status = self._client.query_signal_status()
            self.strike_changed.emit(status)
        except GatewayError as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def query_strike_status(self) -> None:
        try:
            status = self._client.query_signal_status()
            self.strike_changed.emit(status)
        except GatewayError as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def query_temperature(self) -> None:
        try:
            temp = self._client.query_temperature()
            self.temperature_updated.emit(temp)
        except GatewayError as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def ac_on(self) -> None:
        try:
            payload = self._client.ac_on()
            self.command_done.emit("空调开启", payload.hex().upper())
        except GatewayError as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def ac_off(self) -> None:
        try:
            payload = self._client.ac_off()
            self.command_done.emit("空调关闭", payload.hex().upper())
        except GatewayError as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def apply_gateway_ip(self, ip: str, prefix_len: int) -> None:
        try:
            new_ip, new_prefix = self._client.set_gateway_ip(ip, prefix_len)
            self.ip_applied.emit(new_ip, new_prefix)
        except GatewayError as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


def run_in_thread(worker: GatewayWorker, slot) -> QThread:
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(slot)
    thread.finished.connect(worker.deleteLater)
    thread.start()
    return thread
