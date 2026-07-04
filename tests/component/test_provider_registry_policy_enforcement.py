from __future__ import annotations

from dataclasses import dataclass

from agents.runtime.execution_context import ExecutionContext
from agents.runtime.policy_engine import PolicyEngine
from mcp.config import MCPServerConfig
from mcp.discovery import MCPToolInfo
from mcp.mapping import LogicalToolMappingRegistry
from tools.providers.mcp.provider_registry import MCPProviderRegistry
from tools.providers.registry import ProviderRegistry
from tools.specs import ToolCallRequest


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


@dataclass
class FakeLocalExecutor:
    def execute(self, request: ToolCallRequest):
        return {
            "ok": True,
            "output": {"wrote": True},
            "error": None,
            "provider": "local",
            "latency_ms": 1,
        }


def test_provider_registry_blocks_logical_tool_when_policy_disallows_external_access() -> None:
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
    registry = ProviderRegistry(
        mcp_registry=mcp_registry,
        mappings=LogicalToolMappingRegistry.from_file("config/mappings/logical_tools.yaml"),
        policy_engine=PolicyEngine.from_file("config/policies/default.yaml"),
    )

    result = registry.execute(
        ToolCallRequest(
            tool_name="docs.search",
            arguments={"query": "fastapi"},
            context=ExecutionContext(
                agent_name="coder",
                workflow_stage="coding",
                project_type="python",
                environment="local",
                user_mode="interactive",
                network_allowed=False,
                write_allowed=True,
                external_allowed=False,
            ),
        )
    )

    assert result.ok is False
    assert result.error == "external access disabled for current execution context"


def test_provider_registry_blocks_registered_executor_when_policy_disallows_write() -> None:
    registry = ProviderRegistry(
        policy_engine=PolicyEngine.from_file("config/policies/default.yaml"),
    )
    registry.register_executor(
        "workspace.write",
        FakeLocalExecutor(),
        capability_tags=("workspace.write",),
    )

    result = registry.execute(
        ToolCallRequest(
            tool_name="workspace.write",
            arguments={"path": "notes.txt", "content": "hello"},
            context=ExecutionContext(
                agent_name="reviewer",
                workflow_stage="review",
                project_type="python",
                environment="local",
                user_mode="interactive",
                network_allowed=False,
                write_allowed=False,
                external_allowed=False,
            ),
        )
    )

    assert result.ok is False
    assert result.error == "tool tag not allowed for agent profile"
