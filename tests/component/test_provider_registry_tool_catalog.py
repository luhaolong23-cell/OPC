from __future__ import annotations

from dataclasses import dataclass

from mcp.config import MCPServerConfig
from mcp.discovery import MCPToolInfo
from mcp.mapping import LogicalToolMappingRegistry
from tools.providers.mcp.provider_registry import MCPProviderRegistry
from tools.providers.registry import ProviderRegistry
from tools.registry import ToolRegistry


@dataclass
class FakeLocalExecutor:
    def execute(self, request):
        return {"ok": True, "output": {}, "error": None, "provider": "local", "latency_ms": 1}


class FakeMCPHandle:
    def list_tools(self) -> list[MCPToolInfo]:
        return [MCPToolInfo(name="search_docs", description="Search docs", input_schema={"type": "object"})]

    def list_resources(self) -> list[dict]:
        return []


def test_provider_registry_lists_local_and_logical_tool_specs() -> None:
    mcp_registry = MCPProviderRegistry()
    mcp_registry.register(
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
        handle=FakeMCPHandle(),
    )
    provider_registry = ProviderRegistry(
        mcp_registry=mcp_registry,
        mappings=LogicalToolMappingRegistry.from_file("config/mappings/logical_tools.yaml"),
    )
    provider_registry.register_executor(
        "workspace.write",
        FakeLocalExecutor(),
        capability_tags=("workspace.write",),
        provider_name="local_workspace",
        description="Write files in workspace.",
        side_effect_level="write",
    )

    specs = provider_registry.list_tool_specs()

    assert [spec.name for spec in specs] == ["docs.search", "workspace.write"]


def test_tool_registry_lists_local_and_provider_tool_specs_together() -> None:
    mcp_registry = MCPProviderRegistry()
    mcp_registry.register(
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
        handle=FakeMCPHandle(),
    )
    provider_registry = ProviderRegistry(
        mcp_registry=mcp_registry,
        mappings=LogicalToolMappingRegistry.from_file("config/mappings/logical_tools.yaml"),
    )
    provider_registry.register_executor(
        "workspace.write",
        FakeLocalExecutor(),
        capability_tags=("workspace.write",),
        provider_name="local_workspace",
        description="Write files in workspace.",
        side_effect_level="write",
    )
    registry = ToolRegistry(_tools={}, provider_registry=provider_registry)

    specs = registry.list_tool_specs()

    assert [spec.name for spec in specs] == ["docs.search", "workspace.write"]
