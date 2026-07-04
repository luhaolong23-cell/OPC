from __future__ import annotations

import pytest

from director.agent import DirectorAction
from director.router import ActiveProjectError, DirectorRouter, UnsupportedConversationError
from workspace.state import SessionMode, WechatSessionRecord, utcnow


def test_router_returns_chat_reply_for_regular_message() -> None:
    router = DirectorRouter()

    decision = router.route_message("你好，帮我梳理一下需求")

    assert decision.action is DirectorAction.CHAT_REPLY


def test_router_requires_explicit_phrase_to_start_project() -> None:
    router = DirectorRouter()

    decision = router.route_message("开始开发这个项目")

    assert decision.action is DirectorAction.START_PROJECT


def test_router_returns_project_query_when_active_project_exists() -> None:
    router = DirectorRouter()
    session = WechatSessionRecord(
        id="session-1",
        wecom_user_id="alice",
        mode=SessionMode.PROJECT_ACTIVE,
        active_project_id="project-1",
        conversation_summary="",
        last_requirement_draft=None,
        created_at=utcnow(),
        updated_at=utcnow(),
    )

    decision = router.route_message("现在进度怎样？", session=session)

    assert decision.action is DirectorAction.PROJECT_QUERY
    assert decision.project_id == "project-1"


def test_router_rejects_second_start_when_project_is_active() -> None:
    router = DirectorRouter()
    session = WechatSessionRecord(
        id="session-1",
        wecom_user_id="alice",
        mode=SessionMode.PROJECT_ACTIVE,
        active_project_id="project-1",
        conversation_summary="",
        last_requirement_draft=None,
        created_at=utcnow(),
        updated_at=utcnow(),
    )

    with pytest.raises(ActiveProjectError):
        router.route_message("开始开发一个新项目", session=session)


def test_router_rejects_group_chat_messages() -> None:
    router = DirectorRouter()

    with pytest.raises(UnsupportedConversationError):
        router.route_message("开始开发", is_group_chat=True)
