from __future__ import annotations

import pytest

from director.agent import DirectorSystemCommand, DirectorTurn
from director.router import DirectorRouter, UnsupportedConversationError
from workspace.state import SessionMode, WechatSessionRecord, utcnow


class FakeAgent:
    def __init__(self, turn: DirectorTurn) -> None:
        self.turn = turn

    def run(self, message: str, session=None, project_memory=None, project_context=None) -> DirectorTurn:
        return self.turn


def test_router_returns_default_chat_turn_for_regular_message() -> None:
    router = DirectorRouter()

    turn = router.route_message('你好，帮我梳理一下需求')

    assert turn.message == '我先继续和你澄清需求，不会自动进入开发流程。'
    assert turn.system_command is None


def test_router_uses_agent_turn_for_regular_message() -> None:
    router = DirectorRouter(
        agent=FakeAgent(
            DirectorTurn(
                message='需求已经够清晰了，我建议直接做 Python CLI 最小版。',
                requirement_draft='开发一个 Python CLI 版贪吃蛇。',
                conversation_summary='用户要一个最小贪吃蛇游戏。',
                ready_to_start=True,
            )
        )
    )

    turn = router.route_message('帮我开发一个贪吃蛇游戏')

    assert turn.ready_to_start is True
    assert turn.requirement_draft == '开发一个 Python CLI 版贪吃蛇。'


def test_router_rejects_group_chat_messages() -> None:
    router = DirectorRouter()

    with pytest.raises(UnsupportedConversationError):
        router.route_message('开始开发', is_group_chat=True)


def test_router_explicit_new_session_bypasses_agent() -> None:
    router = DirectorRouter(agent=FakeAgent(DirectorTurn(message='should not happen')))

    turn = router.route_message('新会话')

    assert turn.system_command is DirectorSystemCommand.RESET_SESSION
    assert '新会话' in turn.message


def test_router_explicit_project_switch_extracts_target_without_agent() -> None:
    router = DirectorRouter(agent=FakeAgent(DirectorTurn(message='should not happen')))

    turn = router.route_message('切换项目 2')

    assert turn.system_command is DirectorSystemCommand.SWITCH_PROJECT
    assert turn.target == '2'


def test_router_explicit_status_uses_project_context_without_agent() -> None:
    router = DirectorRouter(agent=FakeAgent(DirectorTurn(message='should not happen')))
    session = WechatSessionRecord(
        id='session-1',
        wecom_user_id='alice',
        mode=SessionMode.PROJECT_ACTIVE,
        active_project_id='project-1',
        conversation_summary='',
        last_requirement_draft=None,
        pending_next_step=None,
        created_at=utcnow(),
        updated_at=utcnow(),
    )

    turn = router.route_message(
        '状态',
        session=session,
        project_context={
            'active_project': {
                'id': 'project-1',
                'title': 'Snake Game',
                'status': 'wait_human_plan',
                'current_checkpoint_id': 'cp-1',
            },
            'checkpoint': {
                'id': 'cp-1',
                'type': 'plan_review',
                'status': 'pending',
                'available_actions': ['approve', 'revise'],
            },
        },
    )

    assert turn.system_command is DirectorSystemCommand.STATUS
    assert turn.target == 'project-1'
    assert 'Snake Game' in turn.message
    assert 'wait_human_plan' in turn.message
    assert 'plan_review' in turn.message
