from __future__ import annotations

from dataclasses import dataclass

from director.agent import DirectorTurn
from director.router import DirectorRouter
from director.wechat_message_service import WechatMessageService
from graph.runtime import WorkflowService
from workspace.manager import WorkspaceManager
from workspace.state import SessionMode, TaskStatus


class FakeDirectorAgent:
    def __init__(self, turn: DirectorTurn) -> None:
        self.turn = turn

    def run(self, message: str, session=None, project_memory=None, project_context=None) -> DirectorTurn:
        return self.turn


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


class RequirementTurnPMAgent:
    def run(self, requirement: str, conversation: list[dict] | None = None) -> dict:
        return {
            "summary": f"spec for {requirement}",
            "open_questions": ["目标用户是谁？"],
            "constraints": [],
            "recommended_direction": {"choice": "Python CLI", "justification": "最小可运行"},
        }

    def decide_requirement_turn(self, *, requirement_spec: dict[str, object], current_question: str | None, user_reply: str) -> dict[str, object]:
        return {
            "recommendation": "默认面向普通单人玩家，先做 Python CLI 最小版。",
            "reply": None,
            "requirement_update": None,
            "ready_to_advance": False,
        }


class RequirementApprovalPMAgent(RequirementTurnPMAgent):
    def __init__(self) -> None:
        self.turn_calls = 0

    def decide_requirement_turn(self, *, requirement_spec: dict[str, object], current_question: str | None, user_reply: str) -> dict[str, object]:
        self.turn_calls += 1
        return {
            "recommendation": None,
            "reply": None,
            "requirement_update": None,
            "ready_to_advance": True,
        }


class PlanTurnPlannerAgent:
    def __init__(self) -> None:
        self.turn_calls = 0

    def run(self, requirement_spec: dict) -> dict:
        return {
            "summary": f"plan for {requirement_spec['summary']}",
            "tasks": ["create app", "add tests"],
            "risks": [],
        }

    def decide_plan_turn(self, *, plan: dict[str, object], user_reply: str) -> dict[str, object]:
        self.turn_calls += 1
        return {
            "recommendation": None,
            "reply": None,
            "plan_update": None,
            "ready_to_advance": True,
        }


class FakeCoderAgent:
    def run(self, plan: dict, current_files: dict, task_description: str) -> dict:
        return {
            "modified_files": {"app.py": "print('ok')\n"},
            "summary": "implemented",
        }


class FakeDebuggerAgent:
    def run(self, code_files: dict, test_results: dict, error_log: str | None = None) -> dict:
        return {"patches": {}, "diagnosis": "no-op"}


class FakeReviewerAgent:
    def run(self, plan: dict, code_files: dict, test_results: dict) -> dict:
        return {"approved": True, "issues": [], "risk_level": "low", "summary": "passed"}


@dataclass
class FakeSandbox:
    results: list[dict]

    def run_tests(self, code_files: dict) -> dict:
        return self.results.pop(0)


def test_state_driven_director_turn_updates_chat_session_without_action(tmp_path) -> None:
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / "projects",
    )
    manager.initialize()
    service = WechatMessageService(
        manager=manager,
        director_router=DirectorRouter(
            agent=FakeDirectorAgent(
                DirectorTurn(
                    message="先补充一下目标用户。",
                    requirement_draft="开发一个 Todo API，支持用户登录和任务管理。",
                    conversation_summary="用户要开发 Todo API，已确认需要登录。",
                    ready_to_start=False,
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

    session = manager.get_session("alice")
    assert response.action == "chat_reply"
    assert response.reply == "先补充一下目标用户。"
    assert session is not None
    assert session.mode is SessionMode.CHAT
    assert session.active_project_id is None
    assert session.last_requirement_draft == "开发一个 Todo API，支持用户登录和任务管理。"
    assert session.conversation_summary == "用户要开发 Todo API，已确认需要登录。"


def test_state_driven_director_turn_starts_project_when_ready(tmp_path) -> None:
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / "projects",
    )
    manager.initialize()
    service = WechatMessageService(
        manager=manager,
        director_router=DirectorRouter(
            agent=FakeDirectorAgent(
                DirectorTurn(
                    message="需求已经足够清晰，我先开始推进。",
                    requirement_draft="开发一个 Todo API，支持增删改查和截止日期字段。",
                    conversation_summary="Todo API 需求已澄清完毕。",
                    ready_to_start=True,
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

    session = manager.get_session("alice")
    assert response.action == "start_project"
    assert response.project is not None
    assert response.project.requirement == "开发一个 Todo API，支持增删改查和截止日期字段。"
    assert session is not None
    assert session.mode is SessionMode.PROJECT_ACTIVE
    assert session.active_project_id == response.project.id


def test_state_driven_requirement_recommendation_returns_reply_and_sets_turn_mode(tmp_path) -> None:
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / 'projects',
    )
    manager.initialize()
    project = manager.create_project(title='Snake', requirement='开发一个最小 Python 贪吃蛇游戏。')
    workflow_service = WorkflowService(
        manager=manager,
        pm_agent=RequirementTurnPMAgent(),
        planner_agent=FakePlannerAgent(),
    )
    started_project, checkpoint = workflow_service.start_project(project.id)

    updated_project, next_checkpoint, direct_reply = workflow_service.continue_requirement_discovery(
        project_id=started_project.id,
        clarification='你来建议',
    )

    snapshot = workflow_service.graph.get_state(workflow_service._config(project.id))
    assert checkpoint is not None
    assert next_checkpoint is not None
    assert updated_project.status is TaskStatus.WAIT_HUMAN_REQUIREMENT
    assert next_checkpoint.id == checkpoint.id
    assert direct_reply is not None
    assert '普通单人玩家' in direct_reply
    assert snapshot.values.get('requirement_turn_mode') == 'awaiting_recommendation_confirmation'


def test_state_driven_plan_turn_ready_to_advance_approves_without_action(tmp_path) -> None:
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / 'projects',
    )
    manager.initialize()
    project = manager.create_project(title='Snake', requirement='开发一个最小 Python 贪吃蛇游戏。')
    pm_agent = RequirementApprovalPMAgent()
    planner_agent = PlanTurnPlannerAgent()
    workflow_service = WorkflowService(
        manager=manager,
        pm_agent=pm_agent,
        planner_agent=planner_agent,
        coder_agent=FakeCoderAgent(),
        debugger_agent=FakeDebuggerAgent(),
        reviewer_agent=FakeReviewerAgent(),
        sandbox=FakeSandbox(results=[{'status': 'passed', 'failure_type': None, 'summary': 'ok', 'raw_logs': ''}]),
    )
    started_project, requirement_checkpoint = workflow_service.start_project(project.id)
    approved_requirement_project, plan_checkpoint, direct_reply = workflow_service.continue_requirement_discovery(
        project_id=started_project.id,
        clarification='可以，就这样',
    )

    assert direct_reply is None
    assert requirement_checkpoint is not None
    assert plan_checkpoint is not None
    assert approved_requirement_project.status is TaskStatus.WAIT_HUMAN_PLAN

    updated_project, next_checkpoint, plan_reply = workflow_service.continue_plan_review(
        project_id=approved_requirement_project.id,
        user_reply='可以，按这个来',
    )

    assert plan_reply is None
    assert updated_project.status is TaskStatus.WAIT_HUMAN_CODE
    assert next_checkpoint is not None
    assert next_checkpoint.type == 'code_review'
    assert planner_agent.turn_calls == 1
