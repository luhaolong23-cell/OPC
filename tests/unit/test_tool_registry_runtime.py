from __future__ import annotations

from agents.profiles import get_agent_profile
from tools.defaults import ToolHandle
from tools.registry import ToolRegistry


def test_tool_registry_resolves_tools_by_capability_tag() -> None:
    registry = ToolRegistry(
        {
            "repo_reader": ToolHandle(
                "repo_reader",
                "Read repository files.",
                capability_tags=("repo.read",),
            ),
            "docs_search": ToolHandle(
                "docs_search",
                "Search documentation.",
                capability_tags=("docs.search", "knowledge.read"),
            ),
        }
    )

    resolved = registry.resolve_by_tag("docs.search")

    assert [tool.name for tool in resolved] == ["docs_search"]


def test_tool_registry_bind_preserves_legacy_name_binding() -> None:
    registry = ToolRegistry(
        {
            "repo_reader": ToolHandle("repo_reader", "Read repository files."),
            "patch_applier": ToolHandle("patch_applier", "Apply patches."),
            "test_runner": ToolHandle("test_runner", "Run tests."),
        }
    )

    bound = registry.bind(get_agent_profile("coder").allowed_tools)

    assert set(bound.tools) == {"repo_reader", "patch_applier", "test_runner"}


def test_bound_agent_tools_exposes_runtime_resolution_for_allowed_tags() -> None:
    registry = ToolRegistry(
        {
            "repo_reader": ToolHandle(
                "repo_reader",
                "Read repository files.",
                capability_tags=("repo.read",),
            ),
            "docs_search": ToolHandle(
                "docs_search",
                "Search documentation.",
                capability_tags=("docs.search",),
            ),
        }
    )

    bound = registry.bind(
        ("repo_reader",),
        allowed_tool_tags=("docs.search", "repo.read"),
    )

    assert [tool.name for tool in bound.resolve_by_tag("docs.search")] == ["docs_search"]
    assert [tool.name for tool in bound.resolve_by_tag("repo.read")] == ["repo_reader"]
