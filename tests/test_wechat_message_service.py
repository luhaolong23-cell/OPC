from __future__ import annotations

from director.agent import DirectorAction, DirectorDecision
from director.router import DirectorRouter
from director.wechat_message_service import WechatMessageService
from graph.runtime import WorkflowService
from workspace.manager import WorkspaceManager
from workspace.state import TaskStatus


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
            "tasks": ["create app", "add tests"],
            "risks": [],
        }




class SequencedPMAgent:
    def __init__(self, results: list[dict]) -> None:
        self.results = results
        self.calls: list[dict] = []

    def run(self, requirement: str, conversation: list[dict] | None = None) -> dict:
        self.calls.append({"requirement": requirement, "conversation": conversation or []})
        return self.results.pop(0)

class FakeDirectorAgent:
    def __init__(self, decision: DirectorDecision) -> None:
        self.decision = decision

    def run(self, message: str, session=None) -> DirectorDecision:
        return self.decision


def test_approve_command_advances_current_pending_checkpoint(tmp_path) -> None:
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / "projects",
    )
    manager.initialize()
    project = manager.create_project(title="Todo API", requirement="Build a todo api.")
    manager.bind_active_project("alice", project.id)
    workflow_service = WorkflowService(
        manager=manager,
        pm_agent=FakePMAgent(),
        planner_agent=FakePlannerAgent(),
    )
    running_project, checkpoint = workflow_service.start_project(project.id)
    service = WechatMessageService(
        manager=manager,
        director_router=DirectorRouter(),
        workflow_service=workflow_service,
    )

    response = service.handle_message(
        wecom_user_id="alice",
        message="批准",
        is_group_chat=False,
    )

    assert response.action == "chat_reply"
    assert "已批准" in response.reply
    assert response.project is not None
    assert response.project.status == "wait_human_plan"
    assert response.project.current_checkpoint_id is not None
    assert response.project_id == running_project.id



def test_status_command_returns_active_project_status_summary(tmp_path) -> None:
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / "projects",
    )
    manager.initialize()
    project = manager.create_project(title="Todo API", requirement="Build a todo api.")
    manager.bind_active_project("alice", project.id)
    manager.update_project_flow_state(project.id, status=TaskStatus.WAIT_HUMAN_REQUIREMENT, current_checkpoint_id=None)
    workflow_service = WorkflowService(
        manager=manager,
        pm_agent=FakePMAgent(),
        planner_agent=FakePlannerAgent(),
    )
    service = WechatMessageService(
        manager=manager,
        director_router=DirectorRouter(),
        workflow_service=workflow_service,
    )

    response = service.handle_message(
        wecom_user_id="alice",
        message="状态",
        is_group_chat=False,
    )

    assert response.action == "project_query"
    assert response.project_id == project.id
    assert "wait_human_requirement" in response.reply



def test_reject_command_revises_requirement_checkpoint_instead_of_cancelling(tmp_path) -> None:
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / "projects",
    )
    manager.initialize()
    project = manager.create_project(title="Todo API", requirement="Build a todo api.")
    manager.bind_active_project("alice", project.id)
    workflow_service = WorkflowService(
        manager=manager,
        pm_agent=FakePMAgent(),
        planner_agent=FakePlannerAgent(),
    )
    workflow_service.start_project(project.id)
    service = WechatMessageService(
        manager=manager,
        director_router=DirectorRouter(),
        workflow_service=workflow_service,
    )

    response = service.handle_message(
        wecom_user_id="alice",
        message="驳回",
        is_group_chat=False,
    )

    assert response.action == "chat_reply"
    assert "已打回" in response.reply
    assert response.project is not None
    assert response.project.status == "discovery"



def test_replan_command_rejects_non_code_review_checkpoint(tmp_path) -> None:
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / "projects",
    )
    manager.initialize()
    project = manager.create_project(title="Todo API", requirement="Build a todo api.")
    manager.bind_active_project("alice", project.id)
    workflow_service = WorkflowService(
        manager=manager,
        pm_agent=FakePMAgent(),
        planner_agent=FakePlannerAgent(),
    )
    workflow_service.start_project(project.id)
    service = WechatMessageService(
        manager=manager,
        director_router=DirectorRouter(),
        workflow_service=workflow_service,
    )

    response = service.handle_message(
        wecom_user_id="alice",
        message="重新规划",
        is_group_chat=False,
    )

    assert response.action == "chat_reply"
    assert "不支持这个操作" in response.reply
    assert response.project is None


class FakeCoderAgent:
    def run(self, plan: dict, current_files: dict | None = None, task_description: str = "") -> dict:
        return {
            "modified_files": {
                "app.py": "def main():\n    return 'ok'\n",
                "test_app.py": "from app import main\n\ndef test_main():\n    assert main() == 'ok'\n",
            },
            "summary": f"implemented {plan['summary']}",
        }


class FakeDebuggerAgent:
    def run(self, code_files: dict, test_results: dict, error_log: str | None = None) -> dict:
        return {
            "patches": {},
            "diagnosis": "no-op",
        }


class FakeSandbox:
    def __init__(self, results: list[dict]) -> None:
        self.results = results

    def run_tests(self, code_files: dict) -> dict:
        return self.results.pop(0)



def test_replan_command_moves_code_review_back_to_planning(tmp_path) -> None:
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / "projects",
    )
    manager.initialize()
    project = manager.create_project(title="Todo API", requirement="Build a todo api.")
    manager.bind_active_project("alice", project.id)
    workflow_service = WorkflowService(
        manager=manager,
        pm_agent=FakePMAgent(),
        planner_agent=FakePlannerAgent(),
        coder_agent=FakeCoderAgent(),
        debugger_agent=FakeDebuggerAgent(),
        sandbox=FakeSandbox(
            results=[
                {
                    "status": "passed",
                    "failure_type": None,
                    "summary": "all tests passed",
                    "raw_logs": "",
                }
            ]
        ),
    )
    running_project, requirement_checkpoint = workflow_service.start_project(project.id)
    plan_project, plan_checkpoint = workflow_service.apply_feedback(
        project_id=project.id,
        checkpoint_id=requirement_checkpoint.id,
        checkpoint_type=requirement_checkpoint.type,
        action="approve",
        comments="",
        rejection_reason_type=None,
        client_version=running_project.version,
    )
    workflow_service.apply_feedback(
        project_id=project.id,
        checkpoint_id=plan_checkpoint.id,
        checkpoint_type=plan_checkpoint.type,
        action="approve",
        comments="",
        rejection_reason_type=None,
        client_version=plan_project.version,
    )
    service = WechatMessageService(
        manager=manager,
        director_router=DirectorRouter(),
        workflow_service=workflow_service,
    )

    response = service.handle_message(
        wecom_user_id="alice",
        message="重新规划",
        is_group_chat=False,
    )

    assert response.action == "chat_reply"
    assert "退回到重新规划阶段" in response.reply
    assert response.project is not None
    assert response.project.status == "planning"


def test_ok_alias_advances_current_pending_checkpoint(tmp_path) -> None:
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / "projects",
    )
    manager.initialize()
    project = manager.create_project(title="Todo API", requirement="Build a todo api.")
    manager.bind_active_project("alice", project.id)
    workflow_service = WorkflowService(
        manager=manager,
        pm_agent=FakePMAgent(),
        planner_agent=FakePlannerAgent(),
    )
    workflow_service.start_project(project.id)
    service = WechatMessageService(
        manager=manager,
        director_router=DirectorRouter(),
        workflow_service=workflow_service,
    )

    response = service.handle_message(
        wecom_user_id="alice",
        message="可以",
        is_group_chat=False,
    )

    assert response.action == "chat_reply"
    assert "已批准" in response.reply
    assert response.project is not None
    assert response.project.status == "wait_human_plan"


def test_start_project_message_runs_existing_active_project_in_discovery(tmp_path) -> None:
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / "projects",
    )
    manager.initialize()
    project = manager.create_project(title="Guess Game", requirement="Build a guess game.")
    manager.bind_active_project("alice", project.id)
    service = WechatMessageService(
        manager=manager,
        director_router=DirectorRouter(),
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
    assert response.project_id == project.id
    assert response.project is not None
    assert response.project.status == "discovery"


def test_requirement_draft_refreshes_active_early_project_and_clears_pending_checkpoint(tmp_path) -> None:
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / "projects",
    )
    manager.initialize()
    project = manager.create_project(title="开始开发这个项目", requirement="开始开发这个项目")
    manager.bind_active_project("alice", project.id)
    workflow_service = WorkflowService(
        manager=manager,
        pm_agent=FakePMAgent(),
        planner_agent=FakePlannerAgent(),
    )
    running_project, requirement_checkpoint = workflow_service.start_project(project.id)
    assert requirement_checkpoint is not None
    _, checkpoint = workflow_service.apply_feedback(
        project_id=project.id,
        checkpoint_id=requirement_checkpoint.id,
        checkpoint_type=requirement_checkpoint.type,
        action="approve",
        comments="",
        rejection_reason_type=None,
        client_version=running_project.version,
    )
    assert checkpoint is not None
    service = WechatMessageService(
        manager=manager,
        director_router=DirectorRouter(
            agent=FakeDirectorAgent(
                DirectorDecision(
                    action=DirectorAction.CHAT_REPLY,
                    message="需求已更新。",
                    requirement_draft="开发一个猜数字游戏，范围 1 到 100，CLI 交互。",
                    conversation_summary="用户要一个简单的猜数字游戏，范围 1 到 100。",
                )
            )
        ),
        workflow_service=workflow_service,
    )

    response = service.handle_message(
        wecom_user_id="alice",
        message="我想写一个猜数字小游戏",
        is_group_chat=False,
    )

    refreshed = manager.get_project(project.id)
    refreshed_checkpoint = manager.get_checkpoint(checkpoint.id)
    assert response.action == "chat_reply"
    assert refreshed is not None
    assert refreshed.requirement == "开发一个猜数字游戏，范围 1 到 100，CLI 交互。"
    assert refreshed.title == "开发一个猜数字游戏，范围 1 到 100，CLI 交互。"
    assert refreshed.status == TaskStatus.DISCOVERY
    assert refreshed.current_checkpoint_id is None
    assert refreshed_checkpoint is not None
    assert refreshed_checkpoint.status == "resolved"


def test_requirement_follow_up_message_reruns_pm_discovery_and_replaces_checkpoint(tmp_path) -> None:
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / "projects",
    )
    manager.initialize()
    manager.upsert_chat_session(
        "alice",
        conversation_summary="用户要做一个猜数字游戏。",
        requirement_draft="开发一个猜数字游戏。",
    )
    project = manager.create_project(title="猜数字游戏", requirement="开发一个猜数字游戏。")
    manager.bind_active_project("alice", project.id)
    pm_agent = SequencedPMAgent(
        [
            {
                "summary": "spec v1",
                "open_questions": ["你希望使用什么语言？"],
                "constraints": [],
            },
            {
                "summary": "spec v2",
                "open_questions": [],
                "constraints": [],
            },
        ]
    )
    workflow_service = WorkflowService(
        manager=manager,
        pm_agent=pm_agent,
        planner_agent=FakePlannerAgent(),
    )
    first_project, first_checkpoint = workflow_service.start_project(project.id)
    assert first_checkpoint is not None
    service = WechatMessageService(
        manager=manager,
        director_router=DirectorRouter(),
        workflow_service=workflow_service,
    )

    response = service.handle_message(
        wecom_user_id="alice",
        message="用 Python，命令行就行",
        is_group_chat=False,
    )

    refreshed = manager.get_project(project.id)
    assert response.action == "chat_reply"
    assert response.project is not None
    assert refreshed is not None
    assert refreshed.current_checkpoint_id is not None
    assert refreshed.current_checkpoint_id != first_checkpoint.id
    assert "请确认需求" in response.reply
    assert "用 Python，命令行就行" in refreshed.requirement
    assert manager.get_checkpoint(first_checkpoint.id).status == "resolved"
    assert pm_agent.calls[1]["requirement"].endswith("补充说明：用 Python，命令行就行")
