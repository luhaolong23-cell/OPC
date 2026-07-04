from __future__ import annotations

from mcp.config import MCPServerConfig
from mcp.discovery import MCPToolInfo
from mcp.mapping import LogicalToolMappingRegistry
from tools.providers.mcp.provider_registry import MCPProviderRegistry


class HealthyHandle:
    def list_tools(self) -> list[MCPToolInfo]:
        return [MCPToolInfo(name="repo_search", description="Search repo", input_schema={"type": "object"})]

    def list_resources(self) -> list[dict]:
        return []


class BrokenHandle:
    def list_tools(self) -> list[MCPToolInfo]:
        raise RuntimeError("down")

    def list_resources(self) -> list[dict]:
        return []


def test_mcp_provider_registry_falls_back_to_next_healthy_provider_for_logical_tool() -> None:
    registry = MCPProviderRegistry()
    registry.register(
        MCPServerConfig(
            name="context7",
            transport="stdio",
            command=["context7"],
            url=None,
            env={},
            enabled=True,
            timeout_seconds=5.0,
            tags=("docs",),
        ),
        handle=BrokenHandle(),
    )
    registry.register(
        MCPServerConfig(
            name="local_docs",
            transport="stdio",
            command=["local-docs"],
            url=None,
            env={},
            enabled=True,
            timeout_seconds=5.0,
            tags=("docs",),
        ),
        handle=HealthyHandle(),
    )
    mappings = LogicalToolMappingRegistry.from_file("config/mappings/logical_tools.yaml")

    resolved = registry.resolve_logical_tool("docs.search", mappings)

    assert resolved is not None
    assert resolved.server == "local_docs"
    assert resolved.remote_tool == "repo_search"
