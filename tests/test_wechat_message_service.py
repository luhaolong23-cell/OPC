from __future__ import annotations

from dataclasses import dataclass

from director.agent import DirectorTurn
from director.router import DirectorRouter
from director.wechat_message_service import WechatMessageService
from graph.runtime import WorkflowService
from workspace.manager import WorkspaceManager
from workspace.state import TaskStatus


class FakePMAgent:
    def run(self, requirement: str, conversation: list[dict] | None = None) -> dict:
        return {
            'summary': f'spec for {requirement}',
            'open_questions': [],
            'constraints': [],
        }


class RequirementRecommendationPMAgent:
    def run(self, requirement: str, conversation: list[dict] | None = None) -> dict:
        return {
            'summary': f'spec for {requirement}',
            'open_questions': ['目标用户是谁？'],
            'constraints': [],
            'recommended_direction': {'choice': 'Python CLI', 'justification': '最小可运行'},
        }

    def decide_requirement_turn(self, *, requirement_spec: dict[str, object], current_question: str | None, user_reply: str) -> dict[str, object]:
        return {
            'reply': None,
            'recommendation': '默认面向普通单人玩家，先做 Python CLI 最小版。',
            'requirement_update': None,
            'ready_to_advance': False,
        }


class FakePlannerAgent:
    def run(self, requirement_spec: dict) -> dict:
        return {
            'summary': f"plan for {requirement_spec['summary']}",
            'tasks': ['create app', 'add tests'],
            'risks': [],
        }


@dataclass
class FakeDirectorAgent:
    turn: DirectorTurn

    def run(self, message: str, session=None, project_memory=None, project_context=None) -> DirectorTurn:
        return self.turn


def test_approve_command_advances_current_pending_checkpoint(tmp_path) -> None:
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / 'projects',
    )
    manager.initialize()
    project = manager.create_project(title='Todo API', requirement='Build a todo api.')
    manager.bind_active_project('alice', project.id)
    workflow_service = WorkflowService(
        manager=manager,
        pm_agent=FakePMAgent(),
        planner_agent=FakePlannerAgent(),
    )
    running_project, _ = workflow_service.start_project(project.id)
    service = WechatMessageService(
        manager=manager,
        director_router=DirectorRouter(),
        workflow_service=workflow_service,
    )

    response = service.handle_message(
        wecom_user_id='alice',
        message='批准',
        is_group_chat=False,
    )

    assert response.action == 'chat_reply'
    assert '已批准' in response.reply
    assert response.project is not None
    assert response.project.status == 'wait_human_plan'
    assert response.project.current_checkpoint_id is not None
    assert response.project_id == running_project.id


def test_status_command_returns_active_project_status_summary(tmp_path) -> None:
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / 'projects',
    )
    manager.initialize()
    project = manager.create_project(title='Todo API', requirement='Build a todo api.')
    manager.bind_active_project('alice', project.id)
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
        wecom_user_id='alice',
        message='状态',
        is_group_chat=False,
    )

    assert response.action == 'project_query'
    assert response.project_id == project.id
    assert 'Todo API' in response.reply
    assert 'wait_human_requirement' in response.reply


def test_requirement_stage_follow_up_returns_pm_recommendation_reply(tmp_path) -> None:
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / 'projects',
    )
    manager.initialize()
    project = manager.create_project(title='Snake', requirement='开发一个最小 Python 贪吃蛇游戏。', owner_wecom_user_id='alice')
    manager.bind_active_project('alice', project.id)
    workflow_service = WorkflowService(
        manager=manager,
        pm_agent=RequirementRecommendationPMAgent(),
        planner_agent=FakePlannerAgent(),
    )
    workflow_service.start_project(project.id)
    service = WechatMessageService(
        manager=manager,
        director_router=DirectorRouter(agent=FakeDirectorAgent(DirectorTurn(message='should not happen'))),
        workflow_service=workflow_service,
    )

    response = service.handle_message(
        wecom_user_id='alice',
        message='你来建议',
        is_group_chat=False,
    )

    assert response.action == 'chat_reply'
    assert 'PM 的建议' in response.reply
    assert '普通单人玩家' in response.reply
    assert response.project is not None
    assert response.project.status == 'wait_human_requirement'


def test_new_session_command_resets_active_project_binding(tmp_path) -> None:
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / 'projects',
    )
    manager.initialize()
    project = manager.create_project(title='Snake', requirement='开发一个最小 Python 贪吃蛇游戏。', owner_wecom_user_id='alice')
    manager.bind_active_project('alice', project.id)
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
        wecom_user_id='alice',
        message='新会话',
        is_group_chat=False,
    )

    session = manager.get_session('alice')
    assert response.action == 'chat_reply'
    assert '新会话' in response.reply
    assert session is not None
    assert session.active_project_id is None
