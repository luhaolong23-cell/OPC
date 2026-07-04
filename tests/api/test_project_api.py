from __future__ import annotations

from tests.fakes.workflow import FakePMAgent, FakePlannerAgent
from workspace.state import TaskStatus


def test_post_projects_creates_discovery_project(main_client_factory) -> None:
    client, _manager = main_client_factory()

    response = client.post(
        "/projects",
        json={"title": "Todo API", "requirement": "Build a todo api service."},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["project"]["title"] == "Todo API"
    assert payload["project"]["status"] == "discovery"
    assert payload["project"]["version"] == 1


def test_get_project_returns_404_for_unknown_id(main_client_factory) -> None:
    client, _manager = main_client_factory()

    response = client.get("/projects/missing-project")

    assert response.status_code == 404


def test_wechat_event_starts_project_and_binds_active_session(main_client_factory) -> None:
    client, _manager = main_client_factory()

    response = client.post(
        "/wechat/events",
        json={
            "wecom_user_id": "alice",
            "message": "开始开发这个项目",
            "is_group_chat": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["action"] == "start_project"
    assert payload["project"]["status"] == "discovery"
    assert payload["project"]["title"] == "开始开发这个项目"


def test_wechat_event_approve_command_advances_current_checkpoint(main_client_factory) -> None:
    client, manager = main_client_factory(
        pm_agent=FakePMAgent(),
        planner_agent=FakePlannerAgent(),
    )
    project = manager.create_project(title="Todo API", requirement="Build a todo api.")
    manager.bind_active_project("alice", project.id)

    run_response = client.post(f"/projects/{project.id}/run")
    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["checkpoint"]["type"] == "requirement_review"

    response = client.post(
        "/wechat/events",
        json={
            "wecom_user_id": "alice",
            "message": "批准",
            "is_group_chat": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "chat_reply"
    assert "已批准" in body["reply"]
    assert body["project"]["status"] == "wait_human_plan"


def test_terminal_project_state_releases_active_session_for_new_start(main_client_factory) -> None:
    client, manager = main_client_factory()
    first = manager.create_project(title="First", requirement="Build first")
    manager.bind_active_project("alice", first.id)
    manager.update_project_flow_state(first.id, status=TaskStatus.DONE, current_checkpoint_id=None)

    response = client.post(
        "/wechat/events",
        json={
            "wecom_user_id": "alice",
            "message": "开始开发第二个项目",
            "is_group_chat": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["action"] == "start_project"
    assert payload["project"]["title"] == "开始开发第二个项目"
