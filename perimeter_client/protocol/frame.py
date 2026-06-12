"""北向 TCP HEX 帧编解码。"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

from perimeter_client.protocol.crc16 import crc16_modbus

STX = b"\xAA\x55"
PROTOCOL_VERSION = 0x01


class Status(IntEnum):
    OK = 0x00
    PARAM_ERROR = 0x01
    DEVICE_TIMEOUT = 0x02
    DEVICE_UNREACHABLE = 0x03
    RESPONSE_FORMAT_ERROR = 0x04
    NETWORK_CONFIG_FAILED = 0x05
    UNKNOWN_CMD = 0xFF


STATUS_NAMES: dict[int, str] = {
    Status.OK: "成功",
    Status.PARAM_ERROR: "参数错误",
    Status.DEVICE_TIMEOUT: "设备超时",
    Status.DEVICE_UNREACHABLE: "设备不可达",
    Status.RESPONSE_FORMAT_ERROR: "回包格式错误",
    Status.NETWORK_CONFIG_FAILED: "网络配置失败",
    Status.UNKNOWN_CMD: "未知命令",
}


class Command(IntEnum):
    POWER_ON = 0x01
    POWER_OFF = 0x02
    SIGNAL_ON = 0x03
    SIGNAL_OFF = 0x04
    QUERY_SIGNAL = 0x05
    TEMPERATURE = 0x11
    AC_ON = 0x12
    AC_OFF = 0x13
    SET_IP = 0x20
    QUERY_IP = 0x21


@dataclass(frozen=True)
class ResponseFrame:
    cmd: int
    status: int
    payload: bytes

    @property
    def status_name(self) -> str:
        return STATUS_NAMES.get(self.status, f"未知状态 0x{self.status:02X}")

    @property
    def ok(self) -> bool:
        return self.status == Status.OK


def build_request(cmd: int, payload: bytes = b"") -> bytes:
    body = bytes([PROTOCOL_VERSION, cmd]) + struct.pack(">H", len(payload)) + payload
    crc = crc16_modbus(body)
    return STX + body + struct.pack(">H", crc)


def request_frame_length(payload_len: int) -> int:
    return 6 + payload_len + 2


def response_frame_length(payload_len: int) -> int:
    return 7 + payload_len + 2


def parse_response(data: bytes) -> ResponseFrame:
    if len(data) < 9:
        raise ValueError("响应帧过短")
    if data[:2] != STX:
        raise ValueError("帧头无效")
    if data[2] != PROTOCOL_VERSION:
        raise ValueError("协议版本不匹配")

    cmd = data[3]
    status = data[4]
    payload_len = struct.unpack(">H", data[5:7])[0]
    expected_len = response_frame_length(payload_len)
    if len(data) < expected_len:
        raise ValueError("响应帧不完整")

    frame = data[:expected_len]
    payload = frame[7 : 7 + payload_len]
    crc_received = struct.unpack(">H", frame[-2:])[0]
    crc_body = frame[2:-2]
    if crc16_modbus(crc_body) != crc_received:
        raise ValueError("CRC 校验失败")

    return ResponseFrame(cmd=cmd, status=status, payload=payload)


class FrameBuffer:
    """TCP 粘包缓冲区。"""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, chunk: bytes) -> list[ResponseFrame]:
        self._buf.extend(chunk)
        frames: list[ResponseFrame] = []

        while True:
            start = self._buf.find(STX)
            if start < 0:
                self._buf.clear()
                break
            if start > 0:
                del self._buf[:start]

            if len(self._buf) < 7:
                break

            payload_len = struct.unpack(">H", self._buf[5:7])[0]
            total_len = response_frame_length(payload_len)
            if len(self._buf) < total_len:
                break

            try:
                frames.append(parse_response(bytes(self._buf[:total_len])))
                del self._buf[:total_len]
            except ValueError:
                del self._buf[:2]

        return frames
