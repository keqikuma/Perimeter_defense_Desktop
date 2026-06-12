"""配置文件读写。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class AppConfig:
    host: str = "192.168.1.201"
    port: int = 9000
    connect_timeout_sec: float = 5.0
    response_timeout_sec: float = 15.0
    temperature_poll_interval_sec: float = 3.0
    status_poll_interval_sec: float = 5.0

    @classmethod
    def from_dict(cls, data: dict) -> AppConfig:
        conn = data.get("connection", {})
        timeouts = data.get("timeouts", {})
        polling = data.get("polling", {})
        return cls(
            host=str(conn.get("host", cls.host)),
            port=int(conn.get("port", cls.port)),
            connect_timeout_sec=float(
                timeouts.get("connect_sec", cls.connect_timeout_sec)
            ),
            response_timeout_sec=float(
                timeouts.get("response_sec", cls.response_timeout_sec)
            ),
            temperature_poll_interval_sec=float(
                polling.get("temperature_sec", cls.temperature_poll_interval_sec)
            ),
            status_poll_interval_sec=float(
                polling.get("status_sec", cls.status_poll_interval_sec)
            ),
        )

    def to_dict(self) -> dict:
        return {
            "connection": {"host": self.host, "port": self.port},
            "timeouts": {
                "connect_sec": self.connect_timeout_sec,
                "response_sec": self.response_timeout_sec,
            },
            "polling": {
                "temperature_sec": self.temperature_poll_interval_sec,
                "status_sec": self.status_poll_interval_sec,
            },
        }


def default_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config.yaml"


def load_config(path: Path | None = None) -> AppConfig:
    cfg_path = path or default_config_path()
    if not cfg_path.exists():
        config = AppConfig()
        save_config(config, cfg_path)
        return config

    with cfg_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return AppConfig.from_dict(data)


def save_config(config: AppConfig, path: Path | None = None) -> Path:
    cfg_path = path or default_config_path()
    with cfg_path.open("w", encoding="utf-8") as f:
        yaml.dump(
            config.to_dict(),
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )
    return cfg_path
