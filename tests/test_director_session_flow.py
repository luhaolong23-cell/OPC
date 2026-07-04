from __future__ import annotations

from director.agent import DirectorAction, DirectorDecision
from director.router import DirectorRouter
from director.wechat_message_service import WechatMessageService
from graph.runtime import WorkflowService
from workspace.manager import WorkspaceManager
from workspace.state import SessionMode


class FakeDirectorAgent:
    def __init__(self, decision: DirectorDecision) -> None:
        self.decision = decision

    def run(self, message: str, session=None) -> DirectorDecision:
        return self.decision


class FakePMAgent:
    def run(self, requirement: str, conversation: list[dict] | None = None) -> dict:
        return {
            "summary": f"spec for {requirement}",
            "open_questions": [],
            "constraints": [],
        }


class FakePlannerAgent:
    def run(self, requirement_spec: dict) -> dict:
        return {
            "summary": f"plan for {requirement_spec['summary']}",
            "tasks": [],
            "risks": [],
        }


def test_chat_reply_updates_session_requirement_draft_and_summary(tmp_path) -> None:
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / "projects",
    )
    manager.initialize()
    service = WechatMessageService(
        manager=manager,
        director_router=DirectorRouter(
            agent=FakeDirectorAgent(
                DirectorDecision(
                    action=DirectorAction.CHAT_REPLY,
                    message="请补充认证方式。",
                    requirement_draft="开发一个 Todo API，支持用户登录和任务管理。",
                    conversation_summary="用户要开发 Todo API，已确认需要登录。",
                )
            )
        ),
        workflow_service=WorkflowService(
            manager=manager,
            pm_agent=FakePMAgent(),
            planner_agent=FakePlannerAgent(),
        ),
    )

    response = service.handle_message(
        wecom_user_id="alice",
        message="我想做一个 Todo API",
        is_group_chat=False,
    )

    assert response.action == "chat_reply"
    session = manager.get_session("alice")
    assert session is not None
    assert session.mode is SessionMode.CHAT
    assert session.active_project_id is None
    assert session.last_requirement_draft == "开发一个 Todo API，支持用户登录和任务管理。"
    assert session.conversation_summary == "用户要开发 Todo API，已确认需要登录。"


def test_start_project_uses_requirement_draft_from_director_agent(tmp_path) -> None:
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / "projects",
    )
    manager.initialize()
    service = WechatMessageService(
        manager=manager,
        director_router=DirectorRouter(
            agent=FakeDirectorAgent(
                DirectorDecision(
                    action=DirectorAction.START_PROJECT,
                    message="需求已经足够清晰，开始进入开发流程。",
                    requirement_draft="开发一个 Todo API，支持增删改查和截止日期字段。",
                    conversation_summary="Todo API 需求已澄清完毕。",
                )
            )
        ),
        workflow_service=WorkflowService(
            manager=manager,
            pm_agent=FakePMAgent(),
            planner_agent=FakePlannerAgent(),
        ),
    )

    response = service.handle_message(
        wecom_user_id="alice",
        message="开始开发",
        is_group_chat=False,
    )

    assert response.action == "start_project"
    assert response.project is not None
    assert response.project.requirement == "开发一个 Todo API，支持增删改查和截止日期字段。"
    session = manager.get_session("alice")
    assert session is not None
    assert session.mode is SessionMode.PROJECT_ACTIVE
    assert session.active_project_id == response.project.id
