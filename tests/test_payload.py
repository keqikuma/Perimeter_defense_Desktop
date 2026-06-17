"""IP PAYLOAD 与 GatewayError 单元测试。"""

import unittest

from perimeter_client.client.gateway_client import GatewayError
from perimeter_client.protocol.frame import ResponseFrame, Status
from perimeter_client.protocol.payload import (
    decode_ip_payload,
    encode_ip_payload,
    validate_gateway_ip,
)


class PayloadTests(unittest.TestCase):
    def test_encode_decode_roundtrip(self) -> None:
        payload = encode_ip_payload("192.168.1.201", 24)
        self.assertEqual(payload.hex().upper(), "C0A801C918")
        ip, prefix = decode_ip_payload(payload)
        self.assertEqual(ip, "192.168.1.201")
        self.assertEqual(prefix, 24)

    def test_validate_gateway_ip_rejects_loopback(self) -> None:
        with self.assertRaises(ValueError):
            validate_gateway_ip("127.0.0.1", 24)

    def test_validate_gateway_ip_rejects_prefix_zero(self) -> None:
        with self.assertRaises(ValueError):
            validate_gateway_ip("192.168.1.10", 0)

    def test_validate_gateway_ip_rejects_multicast(self) -> None:
        with self.assertRaises(ValueError):
            validate_gateway_ip("224.0.0.1", 24)


class GatewayErrorTests(unittest.TestCase):
    def test_user_message_param_error(self) -> None:
        response = ResponseFrame(cmd=0x20, status=Status.PARAM_ERROR, payload=b"")
        message = GatewayError.user_message(response)
        self.assertIn("参数错误", message)

    def test_user_message_network_failed(self) -> None:
        response = ResponseFrame(cmd=0x20, status=Status.NETWORK_CONFIG_FAILED, payload=b"")
        message = GatewayError.user_message(response)
        self.assertIn("配置已回滚", message)

    def test_uncertain_set_ip_failure(self) -> None:
        exc = GatewayError("连接已断开")
        self.assertTrue(GatewayError.is_uncertain_set_ip_failure(exc))
        failed = GatewayError(
            "网络配置失败",
            ResponseFrame(cmd=0x20, status=Status.NETWORK_CONFIG_FAILED, payload=b""),
        )
        self.assertFalse(GatewayError.is_uncertain_set_ip_failure(failed))


if __name__ == "__main__":
    unittest.main()
