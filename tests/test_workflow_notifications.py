from __future__ import annotations

from dataclasses import dataclass, field

from graph.runtime import WorkflowService
from workspace.manager import WorkspaceManager


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


class FakeCoderAgent:
    def run(self, plan: dict, current_files: dict | None = None, task_description: str = "") -> dict:
        return {
            "modified_files": {"app.py": "def main():\n    return 'ok'\n"},
            "summary": "implemented",
        }


class FakeDebuggerAgent:
    def run(self, code_files: dict, test_results: dict, error_log: str | None = None) -> dict:
        return {
            "patches": code_files,
            "diagnosis": "no-op",
        }


class FakeReviewerAgent:
    def run(self, plan: dict, code_files: dict, test_results: dict) -> dict:
        return {
            "approved": True,
            "issues": [],
            "risk_level": "low",
            "summary": "review passed",
        }


@dataclass
class FakeSandbox:
    results: list[dict]

    def run_tests(self, code_files: dict) -> dict:
        return self.results.pop(0)




@dataclass
class RecordingPMAgent:
    result: dict
    calls: list[dict] = field(default_factory=list)

    def run(self, requirement: str, conversation: list[dict] | None = None) -> dict:
        self.calls.append({"requirement": requirement, "conversation": conversation or []})
        return self.result

@dataclass
class RecordingPublisher:
    events: list[dict] = field(default_factory=list)

    def publish_event(
        self,
        *,
        event_type: str,
        project_id: str,
        wecom_user_id: str,
        message: str,
        status: str,
        checkpoint_type: str | None = None,
        event_id: str | None = None,
    ) -> str:
        event = {
            "event_type": event_type,
            "project_id": project_id,
            "wecom_user_id": wecom_user_id,
            "message": message,
            "status": status,
            "checkpoint_type": checkpoint_type,
            "event_id": event_id or f"{event_type}:{project_id}",
        }
        self.events.append(event)
        return event["event_id"]


def test_start_project_publishes_requirement_checkpoint_notification(tmp_path) -> None:
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / "projects",
    )
    manager.initialize()
    project = manager.create_project(title="Todo API", requirement="Build a todo api.")
    manager.bind_active_project("alice", project.id)
    publisher = RecordingPublisher()
    service = WorkflowService(
        manager=manager,
        pm_agent=FakePMAgent(),
        planner_agent=FakePlannerAgent(),
        notification_publisher=publisher,
    )

    running_project, checkpoint = service.start_project(project.id)

    assert running_project.status.value == "wait_human_requirement"
    assert checkpoint is not None
    assert [event["event_type"] for event in publisher.events] == ["project_started", "checkpoint_ready"]
    assert publisher.events[1]["checkpoint_type"] == "requirement_review"


def test_workflow_service_publishes_started_and_checkpoint_notifications(tmp_path) -> None:
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / "projects",
    )
    manager.initialize()
    project = manager.create_project(title="Todo API", requirement="Build a todo api.")
    manager.bind_active_project("alice", project.id)
    publisher = RecordingPublisher()
    service = WorkflowService(
        manager=manager,
        pm_agent=FakePMAgent(),
        planner_agent=FakePlannerAgent(),
        notification_publisher=publisher,
    )

    running_project, checkpoint = service.start_project(project.id)
    updated_project, next_checkpoint = service.apply_feedback(
        project_id=project.id,
        checkpoint_id=checkpoint.id,
        checkpoint_type=checkpoint.type,
        action="approve",
        comments="",
        rejection_reason_type=None,
        client_version=running_project.version,
    )

    assert updated_project.status.value == "wait_human_plan"
    assert next_checkpoint is not None
    assert [event["event_type"] for event in publisher.events] == ["project_started", "checkpoint_ready", "checkpoint_ready"]
    assert publisher.events[0]["wecom_user_id"] == "alice"
    assert publisher.events[1]["checkpoint_type"] == "requirement_review"
    assert publisher.events[2]["checkpoint_type"] == "plan_review"


def test_workflow_service_publishes_completion_and_failure_notifications(tmp_path) -> None:
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / "projects",
    )
    manager.initialize()
    done_project = manager.create_project(title="Done", requirement="Build done app.")
    failed_project = manager.create_project(title="Fail", requirement="Build failing app.")
    manager.bind_active_project("alice", done_project.id)
    manager.bind_active_project("bob", failed_project.id)
    publisher = RecordingPublisher()

    done_service = WorkflowService(
        manager=manager,
        pm_agent=FakePMAgent(),
        planner_agent=FakePlannerAgent(),
        coder_agent=FakeCoderAgent(),
        debugger_agent=FakeDebuggerAgent(),
        reviewer_agent=FakeReviewerAgent(),
        sandbox=FakeSandbox(
            results=[
                {"status": "passed", "failure_type": None, "summary": "ok", "raw_logs": ""},
            ]
        ),
        notification_publisher=publisher,
    )
    failed_service = WorkflowService(
        manager=manager,
        pm_agent=FakePMAgent(),
        planner_agent=FakePlannerAgent(),
        coder_agent=FakeCoderAgent(),
        debugger_agent=FakeDebuggerAgent(),
        reviewer_agent=FakeReviewerAgent(),
        sandbox=FakeSandbox(
            results=[
                {"status": "failed", "failure_type": "unknown", "summary": "boom", "raw_logs": "boom"},
            ]
        ),
        notification_publisher=publisher,
    )

    done_running, done_requirement = done_service.start_project(done_project.id)
    done_plan_project, done_plan_checkpoint = done_service.apply_feedback(
        project_id=done_project.id,
        checkpoint_id=done_requirement.id,
        checkpoint_type=done_requirement.type,
        action="approve",
        comments="",
        rejection_reason_type=None,
        client_version=done_running.version,
    )
    done_code_project, done_code_checkpoint = done_service.apply_feedback(
        project_id=done_project.id,
        checkpoint_id=done_plan_checkpoint.id,
        checkpoint_type=done_plan_checkpoint.type,
        action="approve",
        comments="",
        rejection_reason_type=None,
        client_version=done_plan_project.version,
    )
    done_final_project, done_final_checkpoint = done_service.apply_feedback(
        project_id=done_project.id,
        checkpoint_id=done_code_checkpoint.id,
        checkpoint_type=done_code_checkpoint.type,
        action="approve",
        comments="",
        rejection_reason_type=None,
        client_version=done_code_project.version,
    )
    done_service.apply_feedback(
        project_id=done_project.id,
        checkpoint_id=done_final_checkpoint.id,
        checkpoint_type=done_final_checkpoint.type,
        action="approve",
        comments="",
        rejection_reason_type=None,
        client_version=done_final_project.version,
    )

    failed_running, failed_requirement = failed_service.start_project(failed_project.id)
    failed_plan_project, failed_plan_checkpoint = failed_service.apply_feedback(
        project_id=failed_project.id,
        checkpoint_id=failed_requirement.id,
        checkpoint_type=failed_requirement.type,
        action="approve",
        comments="",
        rejection_reason_type=None,
        client_version=failed_running.version,
    )
    failed_service.apply_feedback(
        project_id=failed_project.id,
        checkpoint_id=failed_plan_checkpoint.id,
        checkpoint_type=failed_plan_checkpoint.type,
        action="approve",
        comments="",
        rejection_reason_type=None,
        client_version=failed_plan_project.version,
    )

    event_types = [event["event_type"] for event in publisher.events]
    assert "project_completed" in event_types
    assert "project_failed" in event_types


def test_start_project_passes_director_context_to_pm_and_notifies_open_questions(tmp_path) -> None:
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / "projects",
    )
    manager.initialize()
    manager.upsert_chat_session(
        "alice",
        conversation_summary="用户要做一个 Todo API，需要登录和截止日期。",
        requirement_draft="开发一个 Todo API，支持登录、截止日期、完成状态。",
    )
    project = manager.create_project(title="Todo API", requirement="开发一个 Todo API，支持登录、截止日期、完成状态。")
    manager.bind_active_project("alice", project.id)
    publisher = RecordingPublisher()
    pm_agent = RecordingPMAgent(
        result={
            "summary": "spec for todo api",
            "open_questions": ["你希望使用什么语言？", "是否需要数据库持久化？"],
            "constraints": [],
        }
    )
    service = WorkflowService(
        manager=manager,
        pm_agent=pm_agent,
        planner_agent=FakePlannerAgent(),
        notification_publisher=publisher,
    )

    running_project, checkpoint = service.start_project(project.id)

    assert running_project.status.value == "wait_human_requirement"
    assert checkpoint is not None
    assert pm_agent.calls == [
        {
            "requirement": "开发一个 Todo API，支持登录、截止日期、完成状态。",
            "conversation": [
                {"role": "director_summary", "content": "用户要做一个 Todo API，需要登录和截止日期。"},
                {"role": "director_draft", "content": "开发一个 Todo API，支持登录、截止日期、完成状态。"},
            ],
        }
    ]
    assert publisher.events[1]["event_type"] == "checkpoint_ready"
    assert "我先只确认一个最关键的问题" in publisher.events[1]["message"]
    assert "你希望使用什么语言？" in publisher.events[1]["message"]
    assert "是否需要数据库持久化？" not in publisher.events[1]["message"]
