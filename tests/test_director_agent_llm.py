from __future__ import annotations

from dataclasses import dataclass

import pytest

from director.agent import DirectorAction, DirectorAgent
from director.router import ActiveProjectError, DirectorRouter
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


def test_director_agent_uses_llm_client_and_returns_structured_decision() -> None:
    llm = FakeLLMClient(
        payload={
            "action": "chat_reply",
            "reply": "请补充目标用户和接口范围。",
            "requirement_draft": "开发一个 Todo API，支持增删改查。",
            "conversation_summary": "用户想开发 Todo API，仍需补充范围。",
        }
    )
    agent = DirectorAgent(model="gpt-director", llm_client=llm)

    decision = agent.run("我想做一个 Todo API")

    assert decision.action is DirectorAction.CHAT_REPLY
    assert decision.message == "请补充目标用户和接口范围。"
    assert decision.requirement_draft == "开发一个 Todo API，支持增删改查。"
    assert decision.conversation_summary == "用户想开发 Todo API，仍需补充范围。"
    assert llm.input_text is not None and "Todo API" in llm.input_text


def test_router_rejects_second_start_when_llm_agent_requests_start_for_active_project() -> None:
    agent = DirectorAgent(
        model="gpt-director",
        llm_client=FakeLLMClient(
            payload={
                "action": "start_project",
                "reply": "可以开始。",
                "requirement_draft": "开发一个博客系统。",
                "conversation_summary": "用户要开始新项目。",
            }
        ),
    )
    router = DirectorRouter(agent=agent)
    session = WechatSessionRecord(
        id="session-1",
        wecom_user_id="alice",
        mode=SessionMode.PROJECT_ACTIVE,
        active_project_id="project-1",
        conversation_summary="",
        last_requirement_draft="开发一个旧项目。",
        created_at=utcnow(),
        updated_at=utcnow(),
    )

    with pytest.raises(ActiveProjectError):
        router.route_message("开始开发一个新项目", session=session)
