from __future__ import annotations

from mcp.discovery import MCPToolInfo
from tools.providers.mcp.provider_registry import MCPProviderRegistry


class FakeMCPHandle:
    def list_tools(self) -> list[MCPToolInfo]:
        return [MCPToolInfo(name="search_docs", description="Search docs", input_schema={"type": "object"})]

    def list_resources(self) -> list[dict]:
        return []


def test_mcp_provider_registry_can_be_built_from_config_file() -> None:
    registry = MCPProviderRegistry.from_file(
        "tests/contracts/samples/mcp_servers_config.json",
        handle_factory=lambda config: FakeMCPHandle(),
    )

    tools = registry.list_tools("context7")

    assert [tool.name for tool in tools] == ["search_docs"]
