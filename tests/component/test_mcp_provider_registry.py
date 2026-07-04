from __future__ import annotations

from mcp.config import MCPServerConfig
from mcp.discovery import MCPToolInfo
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


def test_mcp_provider_registry_registers_server_and_lists_tools() -> None:
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

    tools = registry.list_tools("context7")

    assert [tool.name for tool in tools] == ["search_docs"]
