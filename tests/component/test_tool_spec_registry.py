from __future__ import annotations

from dataclasses import dataclass

from mcp.config import MCPServerConfig
from mcp.discovery import MCPToolInfo
from mcp.mapping import LogicalToolMappingRegistry
from tools.defaults import build_default_tool_registry
from tools.providers.mcp.provider_registry import MCPProviderRegistry
from tools.providers.registry import ProviderRegistry
from tools.registry import ToolRegistry


@dataclass
class FakeSandbox:
    def run_tests(self, code_files: dict[str, str]) -> dict[str, object]:
        return {
            "status": "passed",
            "failure_type": None,
            "summary": "ok",
            "raw_logs": "",
        }


class FakeMCPServerHandle:
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


def test_tool_registry_describes_local_tool_as_tool_spec() -> None:
    registry = build_default_tool_registry(sandbox=FakeSandbox())

    spec = registry.describe_tool("test_runner")

    assert spec.name == "test_runner"
    assert spec.provider == "local"
    assert spec.capability_tags == ("test.run",)


def test_tool_registry_describes_logical_provider_tool_as_tool_spec() -> None:
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
        handle=FakeMCPServerHandle(),
    )
    provider_registry = ProviderRegistry(
        mcp_registry=mcp_registry,
        mappings=LogicalToolMappingRegistry.from_file("config/mappings/logical_tools.yaml"),
    )
    registry = ToolRegistry(_tools={}, provider_registry=provider_registry)

    spec = registry.describe_tool("docs.search")

    assert spec.name == "docs.search"
    assert spec.provider == "context7"
    assert spec.capability_tags == ("docs.search",)


def test_default_tool_registry_can_wire_mcp_handles_from_config(monkeypatch) -> None:
    monkeypatch.setattr("tools.defaults._DEFAULT_MCP_SERVERS_PATH", "tests/contracts/samples/mcp_servers_config.json")

    registry = build_default_tool_registry(
        sandbox=FakeSandbox(),
        mcp_handle_factory=lambda config: FakeMCPServerHandle(),
    )

    spec = registry.describe_tool("docs.search")

    assert spec.name == "docs.search"
    assert spec.provider == "context7"
