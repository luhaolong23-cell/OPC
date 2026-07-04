from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient

from config import Settings
from director.router import DirectorRouter
from main import create_app
from tests.fixtures.demo_requirements import CLI_MARKDOWN_REQUIREMENT
from workspace.manager import WorkspaceManager


class FakePMAgent:
    def run(self, requirement: str, conversation: list[dict] | None = None) -> dict:
        return {"summary": f"spec for {requirement}", "open_questions": [], "constraints": []}


class FakePlannerAgent:
    def run(self, requirement_spec: dict) -> dict:
        return {"summary": f"plan for {requirement_spec['summary']}", "tasks": ["cli", "tests"], "risks": []}


class FakeCoderAgent:
    def run(self, plan: dict, current_files: dict | None = None, task_description: str = "") -> dict:
        return {
            "modified_files": {
                "cli.py": "def main():\n    return {'headings': 0, 'links': 0, 'words': 0}\n",
                "test_cli.py": "def test_placeholder():\n    assert True\n",
            },
            "summary": f"implemented {plan['summary']}",
        }


class FakeDebuggerAgent:
    def run(self, code_files: dict, test_results: dict, error_log: str | None = None) -> dict:
        return {"patches": code_files, "diagnosis": "not needed"}


class FakeReviewerAgent:
    def run(self, plan: dict, code_files: dict, test_results: dict) -> dict:
        return {"approved": True, "issues": [], "risk_level": "low", "summary": "review passed"}


@dataclass
class FakeSandbox:
    results: list[dict]

    def run_tests(self, code_files: dict) -> dict:
        return self.results.pop(0)


def test_cli_markdown_demo_reaches_done(tmp_path) -> None:
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
            coder_agent=FakeCoderAgent(),
            debugger_agent=FakeDebuggerAgent(),
            reviewer_agent=FakeReviewerAgent(),
            sandbox=FakeSandbox(
                results=[
                    {"status": "passed", "failure_type": None, "summary": "tests passed", "raw_logs": ""}
                ]
            ),
        )
    )

    create_response = client.post(
        "/projects",
        json={"title": "CLI Markdown Stats", "requirement": CLI_MARKDOWN_REQUIREMENT},
    )
    project_id = create_response.json()["project"]["id"]

    run_response = client.post(f"/projects/{project_id}/run")
    requirement_payload = run_response.json()
    plan_response = client.post(
        f"/projects/{project_id}/feedback",
        json={
            "checkpoint_id": requirement_payload["checkpoint"]["id"],
            "checkpoint_type": requirement_payload["checkpoint"]["type"],
            "action": "approve",
            "comments": "",
            "client_version": requirement_payload["project"]["version"],
        },
    )
    code_response = client.post(
        f"/projects/{project_id}/feedback",
        json={
            "checkpoint_id": plan_response.json()["checkpoint"]["id"],
            "checkpoint_type": plan_response.json()["checkpoint"]["type"],
            "action": "approve",
            "comments": "",
            "client_version": plan_response.json()["project"]["version"],
        },
    )
    final_response = client.post(
        f"/projects/{project_id}/feedback",
        json={
            "checkpoint_id": code_response.json()["checkpoint"]["id"],
            "checkpoint_type": code_response.json()["checkpoint"]["type"],
            "action": "approve",
            "comments": "",
            "client_version": code_response.json()["project"]["version"],
        },
    )
    done_response = client.post(
        f"/projects/{project_id}/feedback",
        json={
            "checkpoint_id": final_response.json()["checkpoint"]["id"],
            "checkpoint_type": final_response.json()["checkpoint"]["type"],
            "action": "approve",
            "comments": "",
            "client_version": final_response.json()["project"]["version"],
        },
    )

    assert done_response.status_code == 200
    assert done_response.json()["project"]["status"] == "done"
    assert done_response.json()["checkpoint"] is None
