from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from fastapi.testclient import TestClient

from wecom_bot_bridge.app import create_app
from wecom_bot_bridge.opc_client import OpcUserVisibleError
from wecom_bot_bridge.config import BridgeSettings
from wecom_bot_bridge.models import TextMessageEvent


@dataclass
class FakeOpcClient:
    event_response: dict | None = None
    should_fail: bool = False
    forwarded: list[TextMessageEvent] = field(default_factory=list)
    runs: list[str] = field(default_factory=list)

    async def forward_text_event(self, event: TextMessageEvent) -> dict:
        self.forwarded.append(event)
        if self.should_fail:
            raise RuntimeError("opc unavailable")
        return self.event_response or {"action": "chat_reply", "reply": "默认回复", "project_id": None}

    async def start_project_run(self, project_id: str) -> None:
        self.runs.append(project_id)


@dataclass
class FakeNotifier:
    sent_messages: list[tuple[str, str]] = field(default_factory=list)
    fail_times: int = 0

    async def send_text(self, wecom_user_id: str, content: str) -> None:
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("send failed")
        self.sent_messages.append((wecom_user_id, content))


class FakeBridgeClient:
    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None


def _make_settings() -> BridgeSettings:
    return BridgeSettings(
        bot_id="bot-id",
        bot_secret="bot-secret",
        host="127.0.0.1",
        port=9001,
        opc_base_url="http://opc",
        opc_internal_token="opc-token",
        notify_token="notify-token",
        request_timeout_seconds=5.0,
    )


def test_internal_notify_requires_bearer_token() -> None:
    client = TestClient(
        create_app(
            settings=_make_settings(),
            opc_client=FakeOpcClient(),
            notifier=FakeNotifier(),
            bridge_client=FakeBridgeClient(),
        )
    )

    response = client.post(
        "/internal/notify",
        json={
            "event_id": "evt_1",
            "event_type": "project_completed",
            "project_id": "proj_123",
            "wecom_user_id": "alice",
            "message": "完成",
            "status": "done",
            "checkpoint_type": None,
        },
    )

    assert response.status_code == 401


def test_internal_notify_is_idempotent_by_event_id() -> None:
    notifier = FakeNotifier()
    client = TestClient(
        create_app(
            settings=_make_settings(),
            opc_client=FakeOpcClient(),
            notifier=notifier,
            bridge_client=FakeBridgeClient(),
        )
    )
    payload = {
        "event_id": "evt_1",
        "event_type": "project_completed",
        "project_id": "proj_123",
        "wecom_user_id": "alice",
        "message": "完成",
        "status": "done",
        "checkpoint_type": None,
    }
    headers = {"Authorization": "Bearer notify-token"}

    first = client.post("/internal/notify", json=payload, headers=headers)
    second = client.post("/internal/notify", json=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == {"accepted": True}
    assert second.json() == {"accepted": True}
    assert notifier.sent_messages == [("alice", "完成")]


def test_internal_notify_returns_accepted_false_and_allows_retry_when_send_fails() -> None:
    notifier = FakeNotifier(fail_times=1)
    client = TestClient(
        create_app(
            settings=_make_settings(),
            opc_client=FakeOpcClient(),
            notifier=notifier,
            bridge_client=FakeBridgeClient(),
        )
    )
    payload = {
        "event_id": "evt_retry",
        "event_type": "checkpoint_ready",
        "project_id": "proj_123",
        "wecom_user_id": "alice",
        "message": "请审批",
        "status": "wait_human_requirement",
        "checkpoint_type": "requirement_review",
    }
    headers = {"Authorization": "Bearer notify-token"}

    first = client.post("/internal/notify", json=payload, headers=headers)
    second = client.post("/internal/notify", json=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == {"accepted": False}
    assert second.json() == {"accepted": True}
    assert notifier.sent_messages == [("alice", "请审批")]


def test_bridge_forwards_text_and_starts_project_run() -> None:
    opc_client = FakeOpcClient(
        event_response={
            "action": "start_project",
            "reply": "已收到，开始开发。",
            "project_id": "proj_123",
        }
    )
    notifier = FakeNotifier()
    app = create_app(
        settings=_make_settings(),
        opc_client=opc_client,
        notifier=notifier,
        bridge_client=FakeBridgeClient(),
    )

    asyncio.run(
        app.state.bridge_service.handle_text_message(
            TextMessageEvent(
                message_id="msg_1",
                wecom_user_id="alice",
                message="开始开发",
                is_group_chat=False,
                raw_frame={},
            )
        )
    )

    assert [event.message for event in opc_client.forwarded] == ["开始开发"]
    assert opc_client.runs == ["proj_123"]
    assert notifier.sent_messages == [("alice", "已收到，开始开发。")]


def test_bridge_sends_fallback_reply_when_opc_request_fails() -> None:
    opc_client = FakeOpcClient(should_fail=True)
    notifier = FakeNotifier()
    app = create_app(
        settings=_make_settings(),
        opc_client=opc_client,
        notifier=notifier,
        bridge_client=FakeBridgeClient(),
    )

    asyncio.run(
        app.state.bridge_service.handle_text_message(
            TextMessageEvent(
                message_id="msg_1",
                wecom_user_id="alice",
                message="状态",
                is_group_chat=False,
                raw_frame={},
            )
        )
    )

    assert notifier.sent_messages == [("alice", "系统繁忙，请稍后重试。")]


def test_bridge_surfaces_user_visible_opc_error_detail() -> None:
    @dataclass
    class ConflictOpcClient(FakeOpcClient):
        async def forward_text_event(self, event: TextMessageEvent) -> dict:
            raise OpcUserVisibleError("你已有进行中的项目，请先发送 状态 或 批准。")

    notifier = FakeNotifier()
    app = create_app(
        settings=_make_settings(),
        opc_client=ConflictOpcClient(),
        notifier=notifier,
        bridge_client=FakeBridgeClient(),
    )

    asyncio.run(
        app.state.bridge_service.handle_text_message(
            TextMessageEvent(
                message_id="msg_2",
                wecom_user_id="alice",
                message="开始开发",
                is_group_chat=False,
                raw_frame={},
            )
        )
    )

    assert notifier.sent_messages == [("alice", "你已有进行中的项目，请先发送 状态 或 批准。")]
