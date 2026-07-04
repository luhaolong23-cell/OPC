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


class NestedContentCoderAgent:
    def run(self, plan: dict, current_files: dict | None = None, task_description: str = "") -> dict:
        return {
            "modified_files": {
                "app.py": {"content": "def main():\n    return 'ok'\n"},
                "test_app.py": {"content": "from app import main\n\ndef test_main():\n    assert main() == 'ok'\n"},
            },
            "summary": f"implemented {plan['summary']}",
        }


class FakeDebuggerAgent:
    def run(self, code_files: dict, test_results: dict, error_log: str | None = None) -> dict:
        return {
            "patches": {
                "app.py": "def main():\n    return 'fixed'\n",
                "test_app.py": "from app import main\n\ndef test_main():\n    assert main() == 'fixed'\n",
            },
            "diagnosis": "fixed failing assertion",
        }


@dataclass
class FakeSandbox:
    results: list[dict]

    def run_tests(self, code_files: dict) -> dict:
        return self.results.pop(0)


def _make_client(tmp_path, sandbox_results: list[dict]) -> TestClient:
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
            sandbox=FakeSandbox(results=sandbox_results),
        )
    )


def _advance_to_plan_review(client: TestClient) -> tuple[str, dict]:
    create_response = client.post(
        "/projects",
        json={"title": "Todo API", "requirement": "Build a todo api."},
    )
    project_id = create_response.json()["project"]["id"]
    run_response = client.post(f"/projects/{project_id}/run")
    requirement_checkpoint = run_response.json()["checkpoint"]
    version = run_response.json()["project"]["version"]
    feedback_response = client.post(
        f"/projects/{project_id}/feedback",
        json={
            "checkpoint_id": requirement_checkpoint["id"],
            "checkpoint_type": requirement_checkpoint["type"],
            "action": "approve",
            "comments": "",
            "client_version": version,
        },
    )
    return project_id, feedback_response.json()


def test_plan_approval_runs_coding_and_reaches_code_review(tmp_path) -> None:
    client = _make_client(
        tmp_path,
        sandbox_results=[
            {
                "status": "passed",
                "failure_type": None,
                "summary": "all tests passed",
                "raw_logs": "",
            }
        ],
    )
    project_id, payload = _advance_to_plan_review(client)

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
    assert body["project"]["status"] == "wait_human_code"
    assert body["checkpoint"]["type"] == "code_review"


def test_assertion_failure_routes_through_debugging_before_code_review(tmp_path) -> None:
    client = _make_client(
        tmp_path,
        sandbox_results=[
            {
                "status": "failed",
                "failure_type": "assertion_failure",
                "summary": "assertion failed",
                "raw_logs": "AssertionError: expected fixed",
            },
            {
                "status": "passed",
                "failure_type": None,
                "summary": "all tests passed",
                "raw_logs": "",
            },
        ],
    )
    project_id, payload = _advance_to_plan_review(client)

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
    assert body["project"]["status"] == "wait_human_code"
    assert body["checkpoint"]["type"] == "code_review"


def test_plan_approval_persists_generated_files_to_workspace(tmp_path) -> None:
    client = _make_client(
        tmp_path,
        sandbox_results=[
            {
                "status": "passed",
                "failure_type": None,
                "summary": "all tests passed",
                "raw_logs": "",
            }
        ],
    )
    project_id, payload = _advance_to_plan_review(client)

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
    workspace_dir = tmp_path / "projects" / project_id / "workspace"
    assert (workspace_dir / "app.py").read_text() == "def main():\n    return 'ok'\n"
    assert (workspace_dir / "test_app.py").read_text() == "from app import main\n\ndef test_main():\n    assert main() == 'ok'\n"


def test_plan_approval_accepts_nested_file_content_objects(tmp_path) -> None:
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
            coder_agent=NestedContentCoderAgent(),
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
    )
    project_id, payload = _advance_to_plan_review(client)

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
    assert body["project"]["status"] == "wait_human_code"
    workspace_dir = tmp_path / "projects" / project_id / "workspace"
    assert (workspace_dir / "app.py").read_text() == "def main():\n    return 'ok'\n"
