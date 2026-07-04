from __future__ import annotations

from agents.runtime.execution_context import ExecutionContext
from agents.runtime.policy_engine import PolicyEngine
from mcp.config import MCPServerConfig
from mcp.discovery import MCPToolInfo
from mcp.mapping import LogicalToolMappingRegistry
from tools.providers.mcp.provider_registry import MCPProviderRegistry
from tools.providers.registry import ProviderRegistry
from tools.specs import ToolCallRequest


class HealthyLocalDocsHandle:
    def list_tools(self) -> list[MCPToolInfo]:
        return [MCPToolInfo(name="repo_search", description="Search local docs", input_schema={"type": "object"})]

    def list_resources(self) -> list[dict]:
        return []

    def call_tool(self, name: str, arguments: dict) -> dict:
        return {
            "ok": True,
            "output": {"remote_tool": name, "query": arguments["query"]},
            "provider": "local_docs",
            "latency_ms": 1,
        }


class BrokenDocsHandle:
    def list_tools(self) -> list[MCPToolInfo]:
        raise RuntimeError("down")

    def list_resources(self) -> list[dict]:
        return []


def _external_context(*, external_allowed: bool) -> ExecutionContext:
    return ExecutionContext(
        agent_name="coder",
        workflow_stage="coding",
        project_type="python",
        environment="local",
        user_mode="interactive",
        network_allowed=external_allowed,
        write_allowed=True,
        external_allowed=external_allowed,
    )


def test_runtime_records_fallback_audit_when_primary_mcp_provider_is_unavailable() -> None:
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
        handle=BrokenDocsHandle(),
    )
    mcp_registry.register(
        MCPServerConfig(
            name="local_docs",
            transport="stdio",
            command=["local-docs"],
            url=None,
            env={},
            enabled=True,
            timeout_seconds=5.0,
            tags=("docs",),
        ),
        handle=HealthyLocalDocsHandle(),
    )
    registry = ProviderRegistry(
        mcp_registry=mcp_registry,
        mappings=LogicalToolMappingRegistry.from_file("config/mappings/logical_tools.yaml"),
    )

    result = registry.execute(
        ToolCallRequest(
            tool_name="docs.search",
            arguments={"query": "fastapi"},
            context=_external_context(external_allowed=True),
        )
    )

    assert result.ok is True
    assert result.provider == "local_docs"
    assert result.metadata["audit"] == {
        "logical_tool": "docs.search",
        "selected_provider": "local_docs",
        "selected_remote_tool": "repo_search",
        "healthy_providers": ["local_docs"],
        "fallback_from": ["context7"],
    }


def test_runtime_returns_deterministic_refusal_audit_when_policy_blocks_external_tool() -> None:
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
        handle=HealthyLocalDocsHandle(),
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
            context=_external_context(external_allowed=False),
        )
    )

    assert result.ok is False
    assert result.provider == "policy"
    assert result.error == "external access disabled for current execution context"
    assert result.metadata["audit"] == {
        "decision": "blocked",
        "tool_name": "docs.search",
        "capability_tag": "docs.search",
        "provider": "policy",
        "reason": "external access disabled for current execution context",
    }
