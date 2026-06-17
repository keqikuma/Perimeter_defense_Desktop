"""南向回包与 IP PAYLOAD 解析。"""

from __future__ import annotations

import ipaddress
import struct


def parse_signal_status(payload: bytes) -> bool | None:
    """解析 0x05 查询结果，True=打击开启，False=打击关闭。"""
    if len(payload) < 4:
        return None
    if payload[0:3] != b"\xFE\x01\x01":
        return None
    flag = payload[3]
    if flag == 0xFF:
        return True
    if flag in (0x00, 0x80):
        return False
    return None


def parse_temperature(payload: bytes) -> float | None:
    """解析 0x11 温度回包，返回摄氏度。"""
    if len(payload) < 5:
        return None
    if payload[0] != 0x01 or payload[1] != 0x03 or payload[2] != 0x02:
        return None
    raw = struct.unpack(">H", payload[3:5])[0]
    return raw - 40


def validate_gateway_ip(ip: str, prefix_len: int) -> None:
    """本地校验网关 IP 参数，与网关 validateBoardIP 规则一致。"""
    addr = ipaddress.IPv4Address(ip)
    if int(addr) == 0:
        raise ValueError("IP 地址不可用（0.0.0.0）")
    if addr.is_loopback:
        raise ValueError("不可使用 loopback 地址（127.x.x.x）")
    if addr.is_multicast:
        raise ValueError("不可使用组播地址（224~239.x.x.x）")
    if not 1 <= prefix_len <= 32:
        raise ValueError("掩码长度须为 1~32")


def encode_ip_payload(ip: str, prefix_len: int) -> bytes:
    validate_gateway_ip(ip, prefix_len)
    addr = ipaddress.IPv4Address(ip)
    return addr.packed + bytes([prefix_len])


def decode_ip_payload(payload: bytes) -> tuple[str, int]:
    if len(payload) != 5:
        raise ValueError("IP PAYLOAD 须为 5 字节")
    ip = str(ipaddress.IPv4Address(payload[:4]))
    prefix_len = payload[4]
    return ip, prefix_len
