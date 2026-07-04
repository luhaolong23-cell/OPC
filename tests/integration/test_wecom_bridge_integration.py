from __future__ import annotations

import asyncio

import httpx
from fastapi.testclient import TestClient

from notifications.publisher import HttpNotificationPublisher
from tests.factories.app import build_main_test_client, build_test_settings, create_workspace_manager
from tests.factories.workflow import build_feedback_payload
from tests.fakes.workflow import FakeBridgeClient, FakeCoderAgent, FakeDebuggerAgent, FakeNotifier, FakePMAgent, FakePlannerAgent, FakeReviewerAgent, FakeSandbox
from wecom_bot_bridge.app import create_app as create_bridge_app
from wecom_bot_bridge.config import BridgeSettings
from wecom_bot_bridge.models import TextMessageEvent
from wecom_bot_bridge.opc_client import OpcHttpClient


def test_bridge_forwards_start_project_to_main_service_with_internal_token(tmp_path) -> None:
    manager = create_workspace_manager(tmp_path)
    main_settings = build_test_settings(
        tmp_path,
        database_url=manager.database_url,
        workspace_root=manager.workspace_root,
        opc_internal_token="opc-token",
    )
    main_client, _manager = build_main_test_client(
        tmp_path,
        settings=main_settings,
        workspace_manager=manager,
        pm_agent=FakePMAgent(),
        planner_agent=FakePlannerAgent(),
    )
    async_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main_client.app),
        base_url="http://main.test",
    )
    notifier = FakeNotifier()
    bridge_app = create_bridge_app(
        settings=BridgeSettings(
            bot_id="bot-id",
            bot_secret="bot-secret",
            host="127.0.0.1",
            port=9001,
            opc_base_url="http://main.test",
            opc_internal_token="opc-token",
            notify_token="notify-token",
            request_timeout_seconds=5.0,
        ),
        opc_client=OpcHttpClient(
            base_url="http://main.test",
            token="opc-token",
            timeout_seconds=5.0,
            client=async_client,
        ),
        notifier=notifier,
        bridge_client=FakeBridgeClient(),
    )

    asyncio.run(
        bridge_app.state.bridge_service.handle_text_message(
            TextMessageEvent(
                message_id="msg_1",
                wecom_user_id="alice",
                message="开始开发这个项目",
                is_group_chat=False,
                raw_frame={},
            )
        )
    )
    asyncio.run(async_client.aclose())

    projects = manager.list_projects()

    assert len(projects) == 1
    assert projects[0].status.value == "wait_human_requirement"
    assert notifier.sent_messages == [("alice", "已收到开始开发请求，我会创建项目并进入开发流程。")]


def test_main_service_completion_notification_reaches_bridge_internal_notify(tmp_path) -> None:
    manager = create_workspace_manager(tmp_path)
    bridge_notifier = FakeNotifier()
    bridge_app = create_bridge_app(
        settings=BridgeSettings(
            bot_id="bot-id",
            bot_secret="bot-secret",
            host="127.0.0.1",
            port=9001,
            opc_base_url="http://main.test",
            opc_internal_token="opc-token",
            notify_token="notify-token",
            request_timeout_seconds=5.0,
        ),
        opc_client=object(),
        notifier=bridge_notifier,
        bridge_client=FakeBridgeClient(),
    )
    bridge_client = TestClient(bridge_app)
    counter = {"value": 0}

    def next_event_id() -> str:
        counter["value"] += 1
        return f"evt-{counter['value']}"

    publisher = HttpNotificationPublisher(
        notify_url="http://testserver/internal/notify",
        token="notify-token",
        timeout_seconds=5.0,
        client=bridge_client,
        event_id_factory=next_event_id,
    )
    main_client, manager = build_main_test_client(
        tmp_path,
        workspace_manager=manager,
        pm_agent=FakePMAgent(),
        planner_agent=FakePlannerAgent(),
        coder_agent=FakeCoderAgent(modified_files={"app.py": "def main():\n    return 'ok'\n"}, summary="implemented"),
        debugger_agent=FakeDebuggerAgent(patches={"app.py": "def main():\n    return 'ok'\n"}, diagnosis="no-op"),
        reviewer_agent=FakeReviewerAgent(),
        sandbox=FakeSandbox(
            results=[
                {"status": "passed", "failure_type": None, "summary": "ok", "raw_logs": ""},
            ]
        ),
        notification_publisher=publisher,
    )
    project = manager.create_project(title="Todo API", requirement="Build a todo api.")
    manager.bind_active_project("alice", project.id)

    payload = main_client.post(f"/projects/{project.id}/run").json()
    for _ in range(4):
        payload = main_client.post(
            f"/projects/{project.id}/feedback",
            json=build_feedback_payload(payload),
        ).json()

    assert ("alice", "项目已完成，请查看结果。") in bridge_notifier.sent_messages
