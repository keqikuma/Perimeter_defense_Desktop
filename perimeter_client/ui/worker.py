"""后台线程执行网关通信，避免阻塞 UI。"""

from __future__ import annotations

from PyQt6.QtCore import QObject, Qt, pyqtSignal

from perimeter_client.client import GatewayClient, GatewayError
from perimeter_client.config import AppConfig
from perimeter_client.logging import get_logger

logger = get_logger("worker")


class TaskBridge(QObject):
    """主线程通过此对象向 Worker 线程投递任务。"""

    submit = pyqtSignal(str, str, int, object)


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

    @property
    def is_connected(self) -> bool:
        return self._client.connected

    def bind_bridge(self, bridge: TaskBridge) -> None:
        bridge.submit.connect(self._dispatch_task, Qt.ConnectionType.QueuedConnection)

    def _dispatch_task(
        self, task: str, host: str, port: int, args: object
    ) -> None:
        if host:
            self._host = host
        if port > 0:
            self._port = port

        logger.info("开始任务: %s host=%s port=%s", task, host or self._host, port or self._port)

        if task == "update_config":
            self._apply_config(args)
            self.finished.emit()
            return

        handlers = {
            "scan_ip": lambda: self.scan_ip(),
            "connect": lambda: self.connect_gateway(),
            "disconnect": lambda: self.disconnect_gateway(),
            "power_on": lambda: self.power_on(),
            "power_off": lambda: self.power_off(),
            "strike_on": lambda: self.strike_on(),
            "strike_off": lambda: self.strike_off(),
            "query_strike": lambda: self.query_strike_status(),
            "query_temperature": lambda: self.query_temperature(),
            "ac_on": lambda: self.ac_on(),
            "ac_off": lambda: self.ac_off(),
            "apply_ip": lambda: self._apply_ip(args),
        }
        handler = handlers.get(task)
        if handler is None:
            logger.error("未知任务: %s", task)
            self.failed.emit(f"未知任务: {task}")
            self.finished.emit()
            return
        handler()

    def _apply_config(self, args: object) -> None:
        if not isinstance(args, AppConfig):
            self.failed.emit("配置参数无效")
            return
        self._config = args
        self._client = GatewayClient(args)

    def _apply_ip(self, args: object) -> None:
        if not isinstance(args, tuple) or len(args) != 2:
            self.failed.emit("IP 参数无效")
            self.finished.emit()
            return
        ip, prefix_len = args
        self.apply_gateway_ip(str(ip), int(prefix_len))

    def scan_ip(self) -> None:
        try:
            ip, prefix = self._client.query_gateway_ip(self._host, self._port)
            self.ip_scanned.emit(ip, prefix)
        except GatewayError as exc:
            logger.error("任务失败: %s", exc)
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def connect_gateway(self) -> None:
        try:
            self._client.connect(self._host, self._port)
            self.connected.emit()
        except GatewayError as exc:
            logger.error("任务失败: %s", exc)
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
            logger.error("任务失败: %s", exc)
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def power_off(self) -> None:
        try:
            payload = self._client.power_off()
            self.command_done.emit("电源关闭", payload.hex().upper())
        except GatewayError as exc:
            logger.error("任务失败: %s", exc)
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def strike_on(self) -> None:
        try:
            self._client.signal_on()
            status = self._client.query_signal_status()
            self.strike_changed.emit(status)
        except GatewayError as exc:
            logger.error("任务失败: %s", exc)
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def strike_off(self) -> None:
        try:
            self._client.signal_off()
            status = self._client.query_signal_status()
            self.strike_changed.emit(status)
        except GatewayError as exc:
            logger.error("任务失败: %s", exc)
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def query_strike_status(self) -> None:
        try:
            status = self._client.query_signal_status()
            self.strike_changed.emit(status)
        except GatewayError as exc:
            logger.error("任务失败: %s", exc)
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def query_temperature(self) -> None:
        try:
            temp = self._client.query_temperature()
            self.temperature_updated.emit(temp)
        except GatewayError as exc:
            logger.error("任务失败: %s", exc)
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def ac_on(self) -> None:
        try:
            payload = self._client.ac_on()
            self.command_done.emit("空调开启", payload.hex().upper())
        except GatewayError as exc:
            logger.error("任务失败: %s", exc)
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def ac_off(self) -> None:
        try:
            payload = self._client.ac_off()
            self.command_done.emit("空调关闭", payload.hex().upper())
        except GatewayError as exc:
            logger.error("任务失败: %s", exc)
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def apply_gateway_ip(self, ip: str, prefix_len: int) -> None:
        try:
            new_ip, new_prefix = self._client.set_gateway_ip(ip, prefix_len)
            self.ip_applied.emit(new_ip, new_prefix)
        except GatewayError as exc:
            logger.error("任务失败: %s", exc)
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()
