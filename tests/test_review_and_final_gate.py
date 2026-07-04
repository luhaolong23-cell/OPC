from __future__ import annotations

from dataclasses import dataclass

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
            "patches": code_files,
            "diagnosis": "not needed",
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
            pm_agent=FakePMAgent(),
            planner_agent=FakePlannerAgent(),
            coder_agent=FakeCoderAgent(),
            debugger_agent=FakeDebuggerAgent(),
            reviewer_agent=FakeReviewerAgent(),
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
    )


def _advance_to_code_review(client: TestClient) -> tuple[str, dict]:
    create_response = client.post(
        "/projects",
        json={"title": "Todo API", "requirement": "Build a todo api."},
    )
    project_id = create_response.json()["project"]["id"]

    run_response = client.post(f"/projects/{project_id}/run")
    requirement_checkpoint = run_response.json()["checkpoint"]
    requirement_response = client.post(
        f"/projects/{project_id}/feedback",
        json={
            "checkpoint_id": requirement_checkpoint["id"],
            "checkpoint_type": requirement_checkpoint["type"],
            "action": "approve",
            "comments": "",
            "client_version": run_response.json()["project"]["version"],
        },
    )
    plan_checkpoint = requirement_response.json()["checkpoint"]
    plan_response = client.post(
        f"/projects/{project_id}/feedback",
        json={
            "checkpoint_id": plan_checkpoint["id"],
            "checkpoint_type": plan_checkpoint["type"],
            "action": "approve",
            "comments": "",
            "client_version": requirement_response.json()["project"]["version"],
        },
    )
    return project_id, plan_response.json()


def test_code_review_approval_creates_final_review_checkpoint(tmp_path) -> None:
    client = _make_client(tmp_path)
    project_id, payload = _advance_to_code_review(client)

    response = client.post(
        f"/projects/{project_id}/feedback",
        json={
            "checkpoint_id": payload["checkpoint"]["id"],
            "checkpoint_type": payload["checkpoint"]["type"],
            "action": "approve",
            "comments": "",
            "client_version": payload["project"]["version"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["project"]["status"] == "wait_human_final"
    assert body["checkpoint"]["type"] == "final_review"


def test_final_review_approval_marks_project_done(tmp_path) -> None:
    client = _make_client(tmp_path)
    project_id, payload = _advance_to_code_review(client)
    code_review_response = client.post(
        f"/projects/{project_id}/feedback",
        json={
            "checkpoint_id": payload["checkpoint"]["id"],
            "checkpoint_type": payload["checkpoint"]["type"],
            "action": "approve",
            "comments": "",
            "client_version": payload["project"]["version"],
        },
    )
    final_payload = code_review_response.json()

    response = client.post(
        f"/projects/{project_id}/feedback",
        json={
            "checkpoint_id": final_payload["checkpoint"]["id"],
            "checkpoint_type": final_payload["checkpoint"]["type"],
            "action": "approve",
            "comments": "",
            "client_version": final_payload["project"]["version"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["project"]["status"] == "done"
    assert body["checkpoint"] is None


def test_final_review_revise_with_implementation_issue_returns_to_coding(tmp_path) -> None:
    client = _make_client(tmp_path)
    project_id, payload = _advance_to_code_review(client)
    code_review_response = client.post(
        f"/projects/{project_id}/feedback",
        json={
            "checkpoint_id": payload["checkpoint"]["id"],
            "checkpoint_type": payload["checkpoint"]["type"],
            "action": "approve",
            "comments": "",
            "client_version": payload["project"]["version"],
        },
    )
    final_payload = code_review_response.json()

    response = client.post(
        f"/projects/{project_id}/feedback",
        json={
            "checkpoint_id": final_payload["checkpoint"]["id"],
            "checkpoint_type": final_payload["checkpoint"]["type"],
            "action": "revise",
            "comments": "need code changes",
            "rejection_reason_type": "implementation_issue",
            "client_version": final_payload["project"]["version"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["project"]["status"] == "coding"
    assert body["checkpoint"] is None
