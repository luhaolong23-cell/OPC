from __future__ import annotations

from agents.runtime.execution_context import ExecutionContext
from mcp.config import MCPServerConfig
from mcp.discovery import MCPToolInfo
from mcp.mapping import LogicalToolMappingRegistry
from tools.providers.mcp.provider_registry import MCPProviderRegistry


class FakeMCPServerHandle:
    def list_tools(self) -> list[MCPToolInfo]:
        return [MCPToolInfo(name="search_docs", description="Search docs", input_schema={"type": "object"})]

    def list_resources(self) -> list[dict]:
        return []

    def call_tool(self, name: str, arguments: dict) -> dict:
        return {
            "ok": True,
            "output": {"remote_tool": name, "query": arguments["query"]},
            "provider": "context7",
            "latency_ms": 2,
        }


def test_mcp_provider_registry_executes_logical_tool_via_selected_provider() -> None:
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
        handle=FakeMCPServerHandle(),
    )
    mappings = LogicalToolMappingRegistry.from_file("config/mappings/logical_tools.yaml")

    result = registry.execute_logical_tool(
        logical_tool="docs.search",
        arguments={"query": "fastapi"},
        context=ExecutionContext(
            agent_name="pm",
            workflow_stage="discovery",
            project_type="python",
            environment="local",
            user_mode="interactive",
            network_allowed=True,
            write_allowed=False,
            external_allowed=True,
        ),
        mappings=mappings,
    )

    assert result.ok is True
    assert result.output == {"remote_tool": "search_docs", "query": "fastapi"}
    assert result.provider == "context7"
