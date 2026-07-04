from __future__ import annotations

from agents.runtime.execution_context import ExecutionContext
from tools.providers.mcp.resource_adapter import MCPResourceAdapter
from tools.providers.mcp.tool_adapter import MCPToolAdapter
from tools.specs import ToolCallRequest


class FakeMCPHandle:
    def call_tool(self, name: str, arguments: dict) -> dict:
        return {
            "ok": True,
            "output": {"tool": name, "arguments": arguments},
            "provider": "context7",
            "latency_ms": 3,
        }

    def read_resource(self, uri: str) -> str:
        return f"resource:{uri}"


def test_mcp_tool_adapter_executes_remote_tool_and_returns_tool_call_result() -> None:
    adapter = MCPToolAdapter(server_name="context7", remote_tool="search_docs", handle=FakeMCPHandle())
    request = ToolCallRequest(
        tool_name="docs.search",
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
    )

    result = adapter.execute(request)

    assert result.ok is True
    assert result.output == {"tool": "search_docs", "arguments": {"query": "fastapi"}}
    assert result.provider == "context7"


def test_mcp_resource_adapter_reads_resource_into_tool_call_result() -> None:
    adapter = MCPResourceAdapter(server_name="memory", resource_uri="memory://docs/1", handle=FakeMCPHandle())
    request = ToolCallRequest(
        tool_name="memory.lookup",
        arguments={},
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
    )

    result = adapter.execute(request)

    assert result.ok is True
    assert result.output == {"content": "resource:memory://docs/1"}
    assert result.provider == "memory"
