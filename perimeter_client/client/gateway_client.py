"""网关 TCP 长连接客户端。"""

from __future__ import annotations

import socket
import threading

from perimeter_client.config import AppConfig
from perimeter_client.protocol.frame import Command, FrameBuffer, ResponseFrame, build_request
from perimeter_client.protocol.payload import (
    decode_ip_payload,
    encode_ip_payload,
    parse_signal_status,
    parse_temperature,
)


class GatewayError(Exception):
    def __init__(self, message: str, response: ResponseFrame | None = None) -> None:
        super().__init__(message)
        self.response = response


class GatewayClient:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._sock: socket.socket | None = None
        self._buffer = FrameBuffer()
        self._lock = threading.Lock()

    @property
    def connected(self) -> bool:
        return self._sock is not None

    def connect(self, host: str | None = None, port: int | None = None) -> None:
        self.disconnect()
        target_host = host or self._config.host
        target_port = port or self._config.port

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self._config.connect_timeout_sec)
        try:
            sock.connect((target_host, target_port))
        except OSError as exc:
            sock.close()
            raise GatewayError(f"连接失败: {exc}") from exc

        sock.settimeout(self._config.response_timeout_sec)
        self._sock = sock
        self._buffer = FrameBuffer()

    def disconnect(self) -> None:
        if self._sock is not None:
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
        try:
            self._sock.sendall(request)
            return self._read_response(cmd)
        except OSError as exc:
            self.disconnect()
            raise GatewayError(f"通信异常: {exc}") from exc

    def _read_response(self, expected_cmd: int) -> ResponseFrame:
        if self._sock is None:
            raise GatewayError("未连接网关")

        while True:
            try:
                chunk = self._sock.recv(4096)
            except socket.timeout as exc:
                raise GatewayError("等待响应超时") from exc

            if not chunk:
                self.disconnect()
                raise GatewayError("连接已断开")

            for frame in self._buffer.feed(chunk):
                if frame.cmd != expected_cmd:
                    continue
                if not frame.ok:
                    raise GatewayError(frame.status_name, frame)
                return frame

    def query_gateway_ip(self, host: str, port: int) -> tuple[str, int]:
        frame = self.send_command(
            Command.QUERY_IP,
            auto_disconnect=True,
            host=host,
            port=port,
        )
        return decode_ip_payload(frame.payload)

    def set_gateway_ip(self, ip: str, prefix_len: int) -> tuple[str, int]:
        payload = encode_ip_payload(ip, prefix_len)
        frame = self.send_command(Command.SET_IP, payload)
        return decode_ip_payload(frame.payload)

    def power_on(self) -> bytes:
        frame = self.send_command(Command.POWER_ON)
        return frame.payload

    def power_off(self) -> bytes:
        frame = self.send_command(Command.POWER_OFF)
        return frame.payload

    def signal_on(self) -> None:
        self.send_command(Command.SIGNAL_ON)

    def signal_off(self) -> None:
        self.send_command(Command.SIGNAL_OFF)

    def query_signal_status(self) -> bool:
        frame = self.send_command(Command.QUERY_SIGNAL)
        status = parse_signal_status(frame.payload)
        if status is None:
            raise GatewayError("无法解析打击状态", frame)
        return status

    def query_temperature(self) -> float:
        frame = self.send_command(Command.TEMPERATURE)
        temp = parse_temperature(frame.payload)
        if temp is None:
            raise GatewayError("无法解析温度数据", frame)
        return temp

    def ac_on(self) -> bytes:
        frame = self.send_command(Command.AC_ON)
        return frame.payload

    def ac_off(self) -> bytes:
        frame = self.send_command(Command.AC_OFF)
        return frame.payload
