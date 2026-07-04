from __future__ import annotations

from dataclasses import dataclass
from os import getenv


@dataclass(slots=True, frozen=True)
class BridgeSettings:
    bot_id: str
    bot_secret: str
    host: str
    port: int
    opc_base_url: str
    opc_internal_token: str | None
    notify_token: str | None
    request_timeout_seconds: float
    reconnect_interval_ms: int = 1000
    max_reconnect_attempts: int = 10
    heartbeat_interval_ms: int = 30000
    ws_url: str | None = None

    @classmethod
    def from_env(cls) -> "BridgeSettings":
        return cls(
            bot_id=getenv("WECOM_BOT_ID", ""),
            bot_secret=getenv("WECOM_BOT_SECRET", ""),
            host=getenv("WECOM_BRIDGE_HOST", "127.0.0.1"),
            port=int(getenv("WECOM_BRIDGE_PORT", "9001")),
            opc_base_url=getenv("OPC_BASE_URL", "http://127.0.0.1:8000"),
            opc_internal_token=getenv("OPC_INTERNAL_TOKEN"),
            notify_token=getenv("WECOM_BRIDGE_NOTIFY_TOKEN"),
            request_timeout_seconds=float(getenv("WECOM_BRIDGE_REQUEST_TIMEOUT", "10")),
            reconnect_interval_ms=int(getenv("WECOM_BRIDGE_RECONNECT_INTERVAL", "1000")),
            max_reconnect_attempts=int(getenv("WECOM_BRIDGE_MAX_RECONNECT_ATTEMPTS", "10")),
            heartbeat_interval_ms=int(getenv("WECOM_BRIDGE_HEARTBEAT_INTERVAL", "30000")),
            ws_url=getenv("WECOM_BRIDGE_WS_URL"),
        )
