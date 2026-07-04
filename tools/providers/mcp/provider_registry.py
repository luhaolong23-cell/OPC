from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents.runtime.execution_context import ExecutionContext
from mcp.config import MCPServerConfig, load_mcp_servers_file
from mcp.fallback import choose_available_provider
from mcp.health import MCPHealthcheck
from mcp.mapping import LogicalToolMappingRegistry, LogicalToolProviderMapping
from tools.providers.mcp.tool_adapter import MCPToolAdapter
from tools.specs import ToolCallRequest, ToolCallResult, ToolSpec


@dataclass
class MCPProviderRegistry:
    _servers: dict[str, tuple[MCPServerConfig, Any]] = field(default_factory=dict)
    healthcheck: MCPHealthcheck = field(default_factory=MCPHealthcheck)

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        handle_factory,
    ) -> "MCPProviderRegistry":
        registry = cls()
        for config in load_mcp_servers_file(path):
            registry.register(config, handle=handle_factory(config))
        return registry

    def register(self, config: MCPServerConfig, *, handle: Any) -> None:
        self._servers[config.name] = (config, handle)

    def start(self) -> None:
        for _name, (_config, handle) in self._servers.items():
            if hasattr(handle, "start"):
                handle.start()

    def stop(self) -> None:
        for _name, (_config, handle) in self._servers.items():
            if hasattr(handle, "stop"):
                handle.stop()

    def health_snapshot(self) -> dict[str, dict[str, object]]:
        snapshot: dict[str, dict[str, object]] = {}
        for name, (_config, handle) in self._servers.items():
            status = self.healthcheck.check(handle)
            snapshot[name] = {
                "healthy": status.healthy,
                "error": status.error,
            }
        return snapshot

    def list_tools(self, server_name: str) -> list[Any]:
        return list(self._servers[server_name][1].list_tools())

    def list_resources(self, server_name: str) -> list[Any]:
        return list(self._servers[server_name][1].list_resources())

    def healthy_servers(self) -> set[str]:
        healthy: set[str] = set()
        for name, status in self.health_snapshot().items():
            if status["healthy"]:
                healthy.add(name)
        return healthy

    def _resolve_logical_tool_with_audit(
        self,
        logical_tool: str,
        mappings: LogicalToolMappingRegistry,
    ) -> tuple[LogicalToolProviderMapping | None, dict[str, object]]:
        mapping = mappings.get(logical_tool)
        healthy_servers = self.healthy_servers()
        provider = choose_available_provider(mapping, healthy_servers)
        ordered_providers = [candidate.server for candidate in mapping.providers]
        healthy_ordered = [server for server in ordered_providers if server in healthy_servers]
        fallback_from: list[str] = []
        if provider is not None:
            for candidate in mapping.providers:
                if candidate.server == provider.server and candidate.remote_tool == provider.remote_tool:
                    break
                fallback_from.append(candidate.server)
        audit: dict[str, object] = {
            "logical_tool": logical_tool,
            "healthy_providers": healthy_ordered,
            "fallback_from": fallback_from,
        }
        if provider is not None:
            audit.update(
                {
                    "selected_provider": provider.server,
                    "selected_remote_tool": provider.remote_tool,
                }
            )
        else:
            audit.update(
                {
                    "selected_provider": None,
                    "selected_remote_tool": None,
                }
            )
        return provider, audit

    def resolve_logical_tool(
        self,
        logical_tool: str,
        mappings: LogicalToolMappingRegistry,
    ) -> LogicalToolProviderMapping | None:
        provider, _audit = self._resolve_logical_tool_with_audit(logical_tool, mappings)
        return provider

    def describe_logical_tool(
        self,
        logical_tool: str,
        mappings: LogicalToolMappingRegistry,
    ) -> ToolSpec:
        provider = self.resolve_logical_tool(logical_tool, mappings)
        if provider is None:
            raise KeyError(f"no healthy provider available for logical tool {logical_tool}")
        handle = self._servers[provider.server][1]
        description = logical_tool
        input_schema: dict[str, object] = {}
        for tool in handle.list_tools():
            if getattr(tool, "name", None) == provider.remote_tool:
                description = getattr(tool, "description", logical_tool)
                input_schema = getattr(tool, "input_schema", {})
                break
        return ToolSpec(
            name=logical_tool,
            version="1.0",
            description=description,
            capability_tags=(logical_tool,),
            input_schema=input_schema,
            output_schema={},
            side_effect_level="read",
            provider=provider.server,
            metadata={"remote_tool": provider.remote_tool},
        )

    def list_tool_specs(self, mappings: LogicalToolMappingRegistry) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for logical_tool in sorted(mappings._mappings):
            try:
                spec = self.describe_logical_tool(logical_tool, mappings)
            except KeyError:
                continue
            specs.append(spec)
        return specs

    def execute_logical_tool(
        self,
        logical_tool: str,
        arguments: dict,
        context: ExecutionContext,
        mappings: LogicalToolMappingRegistry,
    ) -> ToolCallResult:
        provider, audit = self._resolve_logical_tool_with_audit(logical_tool, mappings)
        if provider is None:
            return ToolCallResult(
                ok=False,
                output=None,
                error=f"no healthy provider available for logical tool {logical_tool}",
                provider="mcp",
                latency_ms=0,
                metadata={"audit": audit},
            )
        handle = self._servers[provider.server][1]
        adapter = MCPToolAdapter(
            server_name=provider.server,
            remote_tool=provider.remote_tool,
            handle=handle,
        )
        result = adapter.execute(
            ToolCallRequest(
                tool_name=logical_tool,
                arguments=arguments,
                context=context,
            )
        )
        metadata = dict(result.metadata)
        metadata.setdefault("remote_tool", provider.remote_tool)
        metadata["audit"] = audit
        return ToolCallResult(
            ok=result.ok,
            output=result.output,
            error=result.error,
            provider=result.provider,
            latency_ms=result.latency_ms,
            metadata=metadata,
        )
