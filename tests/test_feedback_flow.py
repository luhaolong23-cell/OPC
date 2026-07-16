from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from config import Settings
from director.router import DirectorRouter
from graph.runtime import WorkflowService
from main import create_app
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


class ExplodingPlannerAgent:
    def run(self, requirement_spec: dict) -> dict:
        raise RuntimeError("planner boom")


def test_workspace_manager_creates_pending_requirement_checkpoint(tmp_path) -> None:
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / "projects",
    )
    manager.initialize()
    project = manager.create_project(title="Todo API", requirement="Build a todo api.")

    checkpoint = manager.create_checkpoint(
        project_id=project.id,
        checkpoint_type="requirement_review",
        available_actions=["approve", "revise", "reject", "pause"],
    )
    loaded_project = manager.get_project(project.id)
    loaded_checkpoint = manager.get_checkpoint(checkpoint.id)

    assert loaded_project is not None
    assert loaded_project.current_checkpoint_id == checkpoint.id
    assert loaded_checkpoint is not None
    assert loaded_checkpoint.type == "requirement_review"
    assert loaded_checkpoint.status == "pending"


def test_run_and_feedback_advance_from_requirement_to_plan_gate(tmp_path) -> None:
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / "projects",
    )
    manager.initialize()
    settings = Settings(
        app_name="OPC Development",
        database_url=manager.database_url,
        workspace_root=manager.workspace_root,
        wecom_agent_id=None,
        wecom_corp_id=None,
        wecom_corp_secret=None,
        llm_model="gpt-5",
        docker_prepare_timeout_seconds=120,
        docker_test_timeout_seconds=120,
    )
    client = TestClient(
        create_app(
            settings=settings,
            workspace_manager=manager,
            director_router=DirectorRouter(),
            pm_agent=FakePMAgent(),
            planner_agent=FakePlannerAgent(),
        )
    )
    create_response = client.post(
        "/projects",
        json={"title": "Todo API", "requirement": "Build a todo api."},
    )
    project_id = create_response.json()["project"]["id"]

    run_response = client.post(f"/projects/{project_id}/run")

    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["project"]["status"] == "wait_human_requirement"
    assert run_payload["checkpoint"]["type"] == "requirement_review"

    feedback_response = client.post(
        f"/projects/{project_id}/feedback",
        json={
            "checkpoint_id": run_payload["checkpoint"]["id"],
            "checkpoint_type": "requirement_review",
            "action": "approve",
            "comments": "",
            "client_version": run_payload["project"]["version"],
        },
    )

    assert feedback_response.status_code == 200
    feedback_payload = feedback_response.json()
    assert feedback_payload["accepted"] is True
    assert feedback_payload["project"]["status"] == "wait_human_plan"
    assert feedback_payload["checkpoint"]["type"] == "plan_review"
    assert feedback_payload["checkpoint"]["status"] == "pending"
    assert feedback_payload["project"]["current_checkpoint_id"] == feedback_payload["checkpoint"]["id"]
    assert TaskStatus(feedback_payload["project"]["status"]) is TaskStatus.WAIT_HUMAN_PLAN


def test_requirement_approve_failure_keeps_pending_checkpoint(tmp_path) -> None:
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
        planner_agent=ExplodingPlannerAgent(),
    )
    running_project, checkpoint = workflow_service.start_project(project.id)

    with pytest.raises(RuntimeError, match="planner boom"):
        workflow_service.apply_feedback(
            project_id=project.id,
            checkpoint_id=checkpoint.id,
            checkpoint_type=checkpoint.type,
            action="approve",
            comments="",
            rejection_reason_type=None,
            client_version=running_project.version,
        )

    project_after = manager.get_project(project.id)
    checkpoint_after = manager.get_checkpoint(checkpoint.id)

    assert project_after is not None
    assert checkpoint_after is not None
    assert project_after.status is TaskStatus.WAIT_HUMAN_REQUIREMENT
    assert project_after.current_checkpoint_id == checkpoint.id
    assert checkpoint_after.status == "pending"


def test_requirement_approval_writes_project_memory_markdown(tmp_path) -> None:
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / "projects",
    )
    manager.initialize()
    project = manager.create_project(title="Todo API", requirement="Build a todo api.")
    manager.bind_active_project("alice", project.id)
    manager.upsert_chat_session(
        "alice",
        conversation_summary="用户偏好最小可用，先不要过度设计。",
        requirement_draft="Build a todo api.",
    )
    workflow_service = WorkflowService(
        manager=manager,
        pm_agent=FakePMAgent(),
        planner_agent=FakePlannerAgent(),
    )
    running_project, checkpoint = workflow_service.start_project(project.id)

    updated_project, next_checkpoint = workflow_service.apply_feedback(
        project_id=project.id,
        checkpoint_id=checkpoint.id,
        checkpoint_type=checkpoint.type,
        action="approve",
        comments="",
        rejection_reason_type=None,
        client_version=running_project.version,
    )

    memory = manager.read_project_memory(project.id)

    assert updated_project.status is TaskStatus.WAIT_HUMAN_PLAN
    assert next_checkpoint is not None
    assert "# Project Memory" in memory
    assert "## Goal" in memory
    assert "Build a todo api." in memory
    assert "## User Preferences" in memory
    assert "用户偏好最小可用，先不要过度设计。" in memory
    assert "## Decisions" in memory
    assert "requirement_review approved" in memory
