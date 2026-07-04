from __future__ import annotations

from fastapi.testclient import TestClient

from config import Settings
from director.router import DirectorRouter
from main import create_app
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


def test_wechat_card_callback_advances_requirement_checkpoint(tmp_path) -> None:
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
    checkpoint = run_response.json()["checkpoint"]
    version = run_response.json()["project"]["version"]

    callback_response = client.post(
        "/wechat/card-callback",
        json={
            "project_id": project_id,
            "checkpoint_id": checkpoint["id"],
            "checkpoint_type": checkpoint["type"],
            "action": "approve",
            "comments": "",
            "client_version": version,
        },
    )

    assert callback_response.status_code == 200
    payload = callback_response.json()
    assert payload["accepted"] is True
    assert payload["project"]["status"] == "wait_human_plan"
    assert payload["checkpoint"]["type"] == "plan_review"
