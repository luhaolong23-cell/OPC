from __future__ import annotations

import pytest

from mcp.config import MCPServerConfig
from mcp.discovery import MCPToolInfo
from tools.providers.mcp.client import MCPTransportClient, build_mcp_server_handle


class FakeTransportClient(MCPTransportClient):
    def __init__(self) -> None:
        self.events: list[str] = []

    def start(self) -> None:
        self.events.append("start")

    def stop(self) -> None:
        self.events.append("stop")

    def list_tools(self) -> list[MCPToolInfo]:
        return [MCPToolInfo(name="search_docs", description="Search docs", input_schema={"type": "object"})]

    def list_resources(self) -> list[dict]:
        return [{"uri": "memory://docs/1"}]

    def call_tool(self, name: str, arguments: dict) -> dict:
        return {"ok": True, "output": {"tool": name, "arguments": arguments}}

    def read_resource(self, uri: str) -> str:
        return f"resource:{uri}"


def test_build_mcp_server_handle_uses_transport_factory_and_delegates_operations() -> None:
    handle = build_mcp_server_handle(
        MCPServerConfig(
            name="context7",
            transport="stdio",
            command=["context7"],
            url=None,
            env={"TOKEN": "x"},
            enabled=True,
            timeout_seconds=5.0,
            tags=("docs",),
        ),
        stdio_client_factory=lambda config: FakeTransportClient(),
    )

    handle.start()
    tools = handle.list_tools()
    resources = handle.list_resources()
    result = handle.call_tool("search_docs", {"query": "fastapi"})
    content = handle.read_resource("memory://docs/1")
    handle.stop()

    assert [tool.name for tool in tools] == ["search_docs"]
    assert resources == [{"uri": "memory://docs/1"}]
    assert result == {"ok": True, "output": {"tool": "search_docs", "arguments": {"query": "fastapi"}}}
    assert content == "resource:memory://docs/1"
    assert handle.client.events == ["start", "stop"]


def test_build_mcp_server_handle_returns_deterministic_error_for_unsupported_transport() -> None:
    handle = build_mcp_server_handle(
        MCPServerConfig(
            name="context7",
            transport="sse",
            command=None,
            url="http://mcp.local",
            env={},
            enabled=True,
            timeout_seconds=5.0,
            tags=("docs",),
        )
    )

    with pytest.raises(RuntimeError, match="unsupported MCP transport sse for server context7"):
        handle.list_tools()
