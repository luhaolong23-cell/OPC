from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from config import Settings
from director.router import DirectorRouter
from main import create_app
from workspace.manager import WorkspaceManager


def build_test_settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "app_name": "OPC Development",
        "database_url": f"sqlite:///{tmp_path / 'opc.db'}",
        "workspace_root": tmp_path / "projects",
        "wecom_agent_id": None,
        "wecom_corp_id": None,
        "wecom_corp_secret": None,
        "llm_model": "gpt-5",
        "docker_prepare_timeout_seconds": 120,
        "docker_test_timeout_seconds": 120,
    }
    values.update(overrides)
    return Settings(**values)


def create_workspace_manager(tmp_path: Path, **overrides) -> WorkspaceManager:
    manager = WorkspaceManager(
        database_url=overrides.pop("database_url", f"sqlite:///{tmp_path / 'opc.db'}"),
        workspace_root=overrides.pop("workspace_root", tmp_path / "projects"),
        **overrides,
    )
    manager.initialize()
    return manager


def build_main_test_client(
    tmp_path: Path,
    *,
    settings: Settings | None = None,
    workspace_manager: WorkspaceManager | None = None,
    director_router: DirectorRouter | None = None,
    **app_kwargs,
) -> tuple[TestClient, WorkspaceManager]:
    manager = workspace_manager or create_workspace_manager(tmp_path)
    app_settings = settings or build_test_settings(
        tmp_path,
        database_url=manager.database_url,
        workspace_root=manager.workspace_root,
    )
    client = TestClient(
        create_app(
            settings=app_settings,
            workspace_manager=manager,
            director_router=director_router or DirectorRouter(),
            **app_kwargs,
        )
    )
    return client, manager
