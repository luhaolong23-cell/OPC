from __future__ import annotations

from typing import Any, Awaitable, Callable, Protocol

from wecom_bot_bridge.config import BridgeSettings
from wecom_bot_bridge.models import TextMessageEvent


class BridgeRuntimeClient(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...


class WecomSdkBridgeClient:
    def __init__(
        self,
        *,
        settings: BridgeSettings,
        on_text_message: Callable[[TextMessageEvent], Awaitable[None]],
    ) -> None:
        from aibot import WSClient, WSClientOptions

        self._on_text_message = on_text_message
        self._ws_client = WSClient(
            WSClientOptions(
                bot_id=settings.bot_id,
                secret=settings.bot_secret,
                reconnect_interval=settings.reconnect_interval_ms,
                max_reconnect_attempts=settings.max_reconnect_attempts,
                heartbeat_interval=settings.heartbeat_interval_ms,
                request_timeout=int(settings.request_timeout_seconds * 1000),
                ws_url=settings.ws_url or "",
            )
        )

        @self._ws_client.on("message.text")
        async def _handle_text(frame: dict[str, Any]) -> None:
            await self._on_text_message(self._to_text_message_event(frame))

    @property
    def ws_client(self):
        return self._ws_client

    async def start(self) -> None:
        await self._ws_client.connect()

    async def stop(self) -> None:
        self._ws_client.disconnect()

    @staticmethod
    def _to_text_message_event(frame: dict[str, Any]) -> TextMessageEvent:
        body = frame.get("body", {})
        headers = frame.get("headers", {})
        text = body.get("text", {}).get("content", "")
        from_user = body.get("from", {}) if isinstance(body.get("from"), dict) else {}
        wecom_user_id = (
            body.get("chatid")
            or body.get("from_userid")
            or body.get("userid")
            or body.get("sender", {}).get("userid")
            or from_user.get("userid")
        )
        if not text or not wecom_user_id:
            raise ValueError("missing text content or wecom user id in websocket frame")
        return TextMessageEvent(
            message_id=headers.get("req_id") or body.get("msgid") or "unknown",
            wecom_user_id=wecom_user_id,
            message=text,
            is_group_chat=bool(body.get("chattype") == "group" or body.get("chat_type") == "group" or body.get("is_group_chat") is True),
            raw_frame=frame,
        )
