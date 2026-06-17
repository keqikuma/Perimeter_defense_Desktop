"""网关 TCP 长连接客户端。"""

from __future__ import annotations

import socket
import threading

from perimeter_client.config import AppConfig
from perimeter_client.logging import format_hex, get_logger
from perimeter_client.protocol.frame import (
    Command,
    FrameBuffer,
    ResponseFrame,
    Status,
    build_request,
)
from perimeter_client.protocol.names import cmd_name
from perimeter_client.protocol.payload import (
    decode_ip_payload,
    encode_ip_payload,
    parse_signal_status,
    parse_temperature,
)

logger = get_logger("tcp")


class GatewayError(Exception):
    def __init__(self, message: str, response: ResponseFrame | None = None) -> None:
        super().__init__(message)
        self.response = response
        self.status = response.status if response else None

    @classmethod
    def user_message(cls, response: ResponseFrame) -> str:
        if response.status == Status.PARAM_ERROR:
            return (
                "参数错误：IP 或掩码不合法"
                "（如 loopback、组播、掩码须 1~32）"
            )
        if response.status == Status.NETWORK_CONFIG_FAILED:
            return "网络配置失败：网关未能应用 IP，配置已回滚，IP 未改变"
        return response.status_name

    @staticmethod
    def is_uncertain_set_ip_failure(exc: "GatewayError") -> bool:
        """改 IP 后连接中断且未收到明确失败 STATUS，可能已成功。"""
        if exc.response is not None:
            return False
        message = str(exc)
        return any(
            keyword in message
            for keyword in ("连接已断开", "通信异常", "等待响应超时")
        )


class GatewayClient:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._sock: socket.socket | None = None
        self._buffer = FrameBuffer()
        self._lock = threading.Lock()
        self._peer = ""

    @property
    def connected(self) -> bool:
        return self._sock is not None

    def connect(self, host: str | None = None, port: int | None = None) -> None:
        self.disconnect()
        target_host = host or self._config.host
        target_port = port or self._config.port
        self._peer = f"{target_host}:{target_port}"

        logger.info("正在连接网关 %s", self._peer)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self._config.connect_timeout_sec)
        try:
            sock.connect((target_host, target_port))
        except OSError as exc:
            sock.close()
            logger.error("连接失败 %s: %s", self._peer, exc)
            raise GatewayError(f"连接失败: {exc}") from exc

        sock.settimeout(self._config.response_timeout_sec)
        self._sock = sock
        self._buffer = FrameBuffer()
        logger.info("网关连接成功 %s", self._peer)

    def disconnect(self) -> None:
        if self._sock is not None:
            logger.info("断开网关连接 %s", self._peer or "未知地址")
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._sock.close()
            except OSError:
                pass
        self._sock = None
        self._buffer = FrameBuffer()
        self._peer = ""

    def send_command(
        self,
        cmd: int,
        payload: bytes = b"",
        *,
        host: str | None = None,
        port: int | None = None,
        auto_disconnect: bool = False,
    ) -> ResponseFrame:
        with self._lock:
            created_here = False
            if not self.connected:
                self.connect(host, port)
                created_here = True

            try:
                return self._exchange(cmd, payload)
            finally:
                if auto_disconnect or created_here:
                    self.disconnect()

    def _exchange(self, cmd: int, payload: bytes) -> ResponseFrame:
        if self._sock is None:
            raise GatewayError("未连接网关")

        request = build_request(cmd, payload)
        logger.debug(
            ">>> CMD=0x%02X %s | %s",
            cmd,
            cmd_name(cmd),
            format_hex(request),
        )
        try:
            self._sock.sendall(request)
            frame = self._read_response(cmd)
            logger.debug(
                "<<< CMD=0x%02X %s STATUS=%s PAYLOAD=%s",
                frame.cmd,
                cmd_name(frame.cmd),
                frame.status_name,
                format_hex(frame.payload) if frame.payload else "(空)",
            )
            return frame
        except OSError as exc:
            self.disconnect()
            logger.error("通信异常 CMD=0x%02X %s: %s", cmd, cmd_name(cmd), exc)
            raise GatewayError(f"通信异常: {exc}") from exc

    def _read_response(self, expected_cmd: int) -> ResponseFrame:
        if self._sock is None:
            raise GatewayError("未连接网关")

        while True:
            try:
                chunk = self._sock.recv(4096)
            except socket.timeout as exc:
                logger.error(
                    "等待响应超时 CMD=0x%02X %s",
                    expected_cmd,
                    cmd_name(expected_cmd),
                )
                raise GatewayError("等待响应超时") from exc

            if not chunk:
                self.disconnect()
                logger.error(
                    "连接已断开 CMD=0x%02X %s",
                    expected_cmd,
                    cmd_name(expected_cmd),
                )
                raise GatewayError("连接已断开")

            logger.debug("收到原始数据 %d 字节 | %s", len(chunk), format_hex(chunk))
            for frame in self._buffer.feed(chunk):
                if frame.cmd != expected_cmd:
                    logger.warning(
                        "忽略非预期响应 CMD=0x%02X，期望 0x%02X",
                        frame.cmd,
                        expected_cmd,
                    )
                    continue
                if not frame.ok:
                    logger.error(
                        "指令失败 CMD=0x%02X %s STATUS=%s",
                        frame.cmd,
                        cmd_name(frame.cmd),
                        frame.status_name,
                    )
                    raise GatewayError(GatewayError.user_message(frame), frame)
                return frame

    def query_gateway_ip(self, host: str, port: int) -> tuple[str, int]:
        frame = self.send_command(
            Command.QUERY_IP,
            auto_disconnect=True,
            host=host,
            port=port,
        )
        ip, prefix = decode_ip_payload(frame.payload)
        logger.info("查询网关 IP 成功: %s/%d", ip, prefix)
        return ip, prefix

    def set_gateway_ip(self, ip: str, prefix_len: int) -> tuple[str, int]:
        payload = encode_ip_payload(ip, prefix_len)
        logger.info("设置网关 IP: %s/%d", ip, prefix_len)

        previous_timeout: float | None = None
        if self._sock is not None:
            previous_timeout = self._sock.gettimeout()
            self._sock.settimeout(self._config.ip_set_timeout_sec)

        try:
            frame = self._exchange(Command.SET_IP, payload)
        finally:
            if self._sock is not None and previous_timeout is not None:
                self._sock.settimeout(previous_timeout)

        new_ip, new_prefix = decode_ip_payload(frame.payload)
        logger.info("设置网关 IP 成功: %s/%d", new_ip, new_prefix)
        return new_ip, new_prefix

    def power_on(self) -> bytes:
        frame = self.send_command(Command.POWER_ON)
        logger.info("电源开启成功")
        return frame.payload

    def power_off(self) -> bytes:
        frame = self.send_command(Command.POWER_OFF)
        logger.info("电源关闭成功")
        return frame.payload

    def signal_on(self) -> None:
        self.send_command(Command.SIGNAL_ON)
        logger.info("打击信号打开成功")

    def signal_off(self) -> None:
        self.send_command(Command.SIGNAL_OFF)
        logger.info("打击信号关闭成功")

    def query_signal_status(self) -> bool:
        frame = self.send_command(Command.QUERY_SIGNAL)
        status = parse_signal_status(frame.payload)
        if status is None:
            logger.error("无法解析打击状态，PAYLOAD=%s", format_hex(frame.payload))
            raise GatewayError("无法解析打击状态", frame)
        logger.debug("打击状态: %s", "开启" if status else "关闭")
        return status

    def query_temperature(self) -> float:
        frame = self.send_command(Command.TEMPERATURE)
        temp = parse_temperature(frame.payload)
        if temp is None:
            logger.error("无法解析温度，PAYLOAD=%s", format_hex(frame.payload))
            raise GatewayError("无法解析温度数据", frame)
        logger.debug("设备仓温度: %.1f ℃", temp)
        return temp

    def ac_on(self) -> bytes:
        frame = self.send_command(Command.AC_ON)
        logger.info("空调开启成功")
        return frame.payload

    def ac_off(self) -> bytes:
        frame = self.send_command(Command.AC_OFF)
        logger.info("空调关闭成功")
        return frame.payload
