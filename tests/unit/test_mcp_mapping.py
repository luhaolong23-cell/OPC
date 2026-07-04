from __future__ import annotations

from mcp.config import MCPServerConfig
from mcp.mapping import LogicalToolMappingRegistry


def test_mcp_server_config_supports_stdio_and_tags() -> None:
    config = MCPServerConfig(
        name="context7",
        transport="stdio",
        command=["npx", "@upstash/context7-mcp"],
        url=None,
        env={"OPENAI_API_KEY": "test"},
        enabled=True,
        timeout_seconds=5.0,
        tags=("docs", "search"),
    )

    assert config.name == "context7"
    assert config.transport == "stdio"
    assert config.tags == ("docs", "search")


def test_logical_tool_mapping_registry_returns_provider_priority_order() -> None:
    registry = LogicalToolMappingRegistry.from_file("config/mappings/logical_tools.yaml")

    mapping = registry.get("docs.search")

    assert mapping.logical_tool == "docs.search"
    assert [provider.server for provider in mapping.providers] == ["context7", "local_docs"]
