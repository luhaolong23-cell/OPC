from __future__ import annotations

from mcp.config import MCPServerConfig
from mcp.discovery import MCPToolInfo
from mcp.mapping import LogicalToolMappingRegistry
from tools.providers.mcp.provider_registry import MCPProviderRegistry


class FakeMCPServerHandle:
    def __init__(self, name: str) -> None:
        self.name = name

    def list_tools(self) -> list[MCPToolInfo]:
        return [
            MCPToolInfo(
                name="search_docs",
                description="Search documentation",
                input_schema={"type": "object"},
            )
        ]

    def list_resources(self) -> list[dict]:
        return []


def test_mcp_provider_registry_resolves_logical_tool_to_highest_priority_available_provider() -> None:
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
        handle=FakeMCPServerHandle("context7"),
    )
    mappings = LogicalToolMappingRegistry.from_file("config/mappings/logical_tools.yaml")

    resolved = registry.resolve_logical_tool("docs.search", mappings)

    assert resolved is not None
    assert resolved.server == "context7"
    assert resolved.remote_tool == "search_docs"
