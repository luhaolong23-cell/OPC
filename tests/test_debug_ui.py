from __future__ import annotations

from fastapi.testclient import TestClient

from config import Settings
from director.router import DirectorRouter
from main import create_app
from workspace.manager import WorkspaceManager


def _make_client(tmp_path) -> TestClient:
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
    return TestClient(
        create_app(
            settings=settings,
            workspace_manager=manager,
            director_router=DirectorRouter(),
        )
    )


def test_debug_projects_page_lists_projects(tmp_path) -> None:
    client = _make_client(tmp_path)
    client.post(
        "/projects",
        json={"title": "Todo API", "requirement": "Build a todo api."},
    )

    response = client.get("/debug/projects")

    assert response.status_code == 200
    assert "Todo API" in response.text


def test_debug_project_detail_page_shows_project_status(tmp_path) -> None:
    client = _make_client(tmp_path)
    create_response = client.post(
        "/projects",
        json={"title": "Todo API", "requirement": "Build a todo api."},
    )
    project_id = create_response.json()["project"]["id"]

    response = client.get(f"/debug/projects/{project_id}")

    assert response.status_code == 200
    assert "Todo API" in response.text
    assert "discovery" in response.text


def test_project_events_endpoint_streams_sse_payload(tmp_path) -> None:
    client = _make_client(tmp_path)
    create_response = client.post(
        "/projects",
        json={"title": "Todo API", "requirement": "Build a todo api."},
    )
    project_id = create_response.json()["project"]["id"]

    with client.stream("GET", f"/projects/{project_id}/events") as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: project.updated" in body
    assert project_id in body
