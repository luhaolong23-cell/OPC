from __future__ import annotations

import json
from dataclasses import dataclass

from director.agent import DirectorAgent
from workspace.state import SessionMode, WechatSessionRecord, utcnow


@dataclass
class FakeLLMClient:
    payload: dict
    instructions: str | None = None
    input_text: str | None = None

    def generate_json(self, *, instructions: str, input_text: str) -> dict:
        self.instructions = instructions
        self.input_text = input_text
        return self.payload


def test_director_agent_uses_llm_client_and_returns_turn() -> None:
    llm = FakeLLMClient(
        payload={
            'reply': '请补充目标用户和接口范围。',
            'state_patch': {
                'requirement_draft': '开发一个 Todo API，支持增删改查。',
                'conversation_summary': '用户想开发 Todo API，仍需补充范围。',
                'ready_to_start': False,
            },
        }
    )
    agent = DirectorAgent(model='gpt-director', llm_client=llm)

    turn = agent.run('我想做一个 Todo API')

    assert turn.message == '请补充目标用户和接口范围。'
    assert turn.requirement_draft == '开发一个 Todo API，支持增删改查。'
    assert turn.conversation_summary == '用户想开发 Todo API，仍需补充范围。'
    assert turn.ready_to_start is False
    assert llm.input_text is not None and 'Todo API' in llm.input_text


def test_director_agent_can_mark_turn_ready_to_start() -> None:
    llm = FakeLLMClient(
        payload={
            'reply': '需求已经清晰，我先开始推进。',
            'state_patch': {
                'requirement_draft': '开发一个最小 Python 贪吃蛇游戏。',
                'conversation_summary': '用户要一个最小 Python 贪吃蛇游戏。',
                'ready_to_start': True,
            },
        }
    )
    agent = DirectorAgent(model='gpt-director', llm_client=llm)

    turn = agent.run('帮我开发一个贪吃蛇游戏')

    assert turn.ready_to_start is True
    assert turn.requirement_draft == '开发一个最小 Python 贪吃蛇游戏。'


def test_director_agent_includes_project_memory_but_not_pending_next_step_in_payload() -> None:
    llm = FakeLLMClient(
        payload={
            'reply': '请确认是否继续。',
            'state_patch': {
                'conversation_summary': '用户在确认项目方向。',
                'ready_to_start': False,
            },
        }
    )
    agent = DirectorAgent(model='gpt-director', llm_client=llm)
    session = WechatSessionRecord(
        id='session-1',
        wecom_user_id='alice',
        mode=SessionMode.CHAT,
        active_project_id=None,
        conversation_summary='用户在确认项目方向。',
        last_requirement_draft='开发一个 Python CLI 版贪吃蛇游戏。',
        pending_next_step='start_project',
        created_at=utcnow(),
        updated_at=utcnow(),
    )

    agent.run(
        '继续',
        session=session,
        project_memory='# Project Memory\n- 默认先做 CLI\n',
        project_context={'active_project': None},
    )

    assert llm.input_text is not None
    payload = json.loads(llm.input_text)
    assert payload['project_memory'].startswith('# Project Memory')
    assert payload['session']['last_requirement_draft'] == '开发一个 Python CLI 版贪吃蛇游戏。'
    assert 'pending_next_step' not in payload['session']
