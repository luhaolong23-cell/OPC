from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status

from wecom_bot_bridge.client import BridgeRuntimeClient, WecomSdkBridgeClient
from wecom_bot_bridge.config import BridgeSettings
from wecom_bot_bridge.dedup import TtlDeduplicator
from wecom_bot_bridge.models import InternalNotifyRequest, InternalNotifyResponse, TextMessageEvent
from wecom_bot_bridge.notifier import TextNotifier, WecomTextNotifier
from wecom_bot_bridge.opc_client import OpcHttpClient, OpcUserVisibleError

FALLBACK_REPLY = "系统繁忙，请稍后重试。"
LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class BridgeService:
    opc_client: Any
    notifier: TextNotifier
    message_deduplicator: TtlDeduplicator

    async def handle_text_message(self, event: TextMessageEvent) -> None:
        if self.message_deduplicator.seen(event.message_id):
            return
        self.message_deduplicator.mark(event.message_id)

        try:
            response = await self.opc_client.forward_text_event(event)
        except OpcUserVisibleError as exc:
            await self.notifier.send_text(event.wecom_user_id, str(exc))
            return
        except Exception:
            await self.notifier.send_text(event.wecom_user_id, FALLBACK_REPLY)
            return

        reply = response.get("reply")
        if reply:
            await self.notifier.send_text(event.wecom_user_id, reply)

        if response.get("action") == "start_project" and response.get("project_id"):
            await self.opc_client.start_project_run(response["project_id"])



def create_app(
    *,
    settings: BridgeSettings | None = None,
    opc_client: Any | None = None,
    notifier: TextNotifier | None = None,
    bridge_client: BridgeRuntimeClient | None = None,
    message_deduplicator: TtlDeduplicator | None = None,
    notify_deduplicator: TtlDeduplicator | None = None,
) -> FastAPI:
    settings = settings or BridgeSettings.from_env()
    message_deduplicator = message_deduplicator or TtlDeduplicator()
    notify_deduplicator = notify_deduplicator or TtlDeduplicator()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime = app.state.bridge_client
        await runtime.start()
        try:
            yield
        finally:
            await runtime.stop()

    app = FastAPI(title="WeCom Bot Bridge", lifespan=lifespan)
    app.state.settings = settings
    app.state.opc_client = opc_client or OpcHttpClient(
        base_url=settings.opc_base_url,
        token=settings.opc_internal_token,
        timeout_seconds=settings.request_timeout_seconds,
    )

    async def _dispatch_text(event: TextMessageEvent) -> None:
        await app.state.bridge_service.handle_text_message(event)

    if bridge_client is None:
        bridge_client = WecomSdkBridgeClient(settings=settings, on_text_message=_dispatch_text)

    app.state.bridge_client = bridge_client
    app.state.notifier = notifier or WecomTextNotifier(getattr(bridge_client, "ws_client"))
    app.state.bridge_service = BridgeService(
        opc_client=app.state.opc_client,
        notifier=app.state.notifier,
        message_deduplicator=message_deduplicator,
    )
    app.state.notify_deduplicator = notify_deduplicator

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/internal/notify", response_model=InternalNotifyResponse)
    async def internal_notify(payload: InternalNotifyRequest, request: Request) -> InternalNotifyResponse:
        _require_notify_token(request)
        deduplicator: TtlDeduplicator = request.app.state.notify_deduplicator
        if deduplicator.seen(payload.event_id):
            return InternalNotifyResponse(accepted=True)
        try:
            await request.app.state.notifier.send_text(payload.wecom_user_id, payload.message)
        except Exception:
            LOGGER.exception(
                "failed to deliver bridge notification",
                extra={"event_id": payload.event_id, "wecom_user_id": payload.wecom_user_id},
            )
            return InternalNotifyResponse(accepted=False)
        deduplicator.mark(payload.event_id)
        return InternalNotifyResponse(accepted=True)

    return app



def _require_notify_token(request: Request) -> None:
    token = request.app.state.settings.notify_token
    if not token:
        return
    authorization = request.headers.get("authorization")
    if authorization != f"Bearer {token}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token")
