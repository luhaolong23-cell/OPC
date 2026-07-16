from __future__ import annotations

import pytest

from workspace.manager import ActiveProjectExistsError
from workspace.state import SessionMode, TaskStatus


def test_workspace_manager_creates_and_reads_project(workspace_manager_factory) -> None:
    manager = workspace_manager_factory()

    created = manager.create_project(
        title="Todo API",
        requirement="Build a todo api service.",
    )
    loaded = manager.get_project(created.id)

    assert loaded is not None
    assert loaded.id == created.id
    assert loaded.title == "Todo API"
    assert loaded.requirement == "Build a todo api service."
    assert loaded.status is TaskStatus.DISCOVERY
    assert loaded.version == 1
    assert loaded.current_checkpoint_id is None


def test_workspace_manager_rejects_second_active_project_for_same_user(workspace_manager_factory) -> None:
    manager = workspace_manager_factory()
    first = manager.create_project(
        title="Todo API",
        requirement="Build a todo api service.",
    )
    second = manager.create_project(
        title="Markdown CLI",
        requirement="Build a markdown statistics cli.",
    )

    session = manager.bind_active_project("alice", first.id)

    assert session.mode is SessionMode.PROJECT_ACTIVE
    assert session.active_project_id == first.id

    with pytest.raises(ActiveProjectExistsError):
        manager.bind_active_project("alice", second.id)


def test_workspace_manager_persists_project_memory_markdown(workspace_manager_factory) -> None:
    manager = workspace_manager_factory()
    project = manager.create_project(
        title="Todo API",
        requirement="Build a todo api service.",
    )

    manager.write_project_memory(
        project.id,
        "# Project Memory\n\n## Goal\n- Build a todo api.\n",
    )

    memory_path = manager.project_memory_path(project.id)

    assert memory_path.exists()
    assert manager.read_project_memory(project.id) == "# Project Memory\n\n## Goal\n- Build a todo api.\n"
