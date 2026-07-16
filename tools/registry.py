from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.profiles import get_agent_profile
from agents.runtime.execution_context import ExecutionContext
from agents.runtime.policy_engine import PolicyEngine
from tools.providers.registry import ProviderRegistry
from tools.runtime import BackendToolExecutor
from tools.specs import ToolCallRequest, ToolCallResult, ToolSpec


@dataclass
class BoundAgentTools:
    tools: dict[str, Any]
    registry: "ToolRegistry | None" = None
    allowed_tool_tags: tuple[str, ...] = ()

    def require(self, name: str) -> Any:
        return self.tools[name]

    def resolve_by_tag(self, tag: str) -> list[Any]:
        if tag not in self.allowed_tool_tags:
            return []
        if self.registry is None:
            return []
        return self.registry.resolve_by_tag(tag)

    def execute(self, name: str, arguments: dict[str, Any], context: ExecutionContext) -> ToolCallResult:
        if name not in self.tools:
            return ToolCallResult(
                ok=False,
                output=None,
                error=f"tool {name} is not bound for this agent",
                provider="bound-agent-tools",
                latency_ms=0,
            )
        if self.registry is None:
            return ToolCallResult(
                ok=False,
                output=None,
                error="tool registry is not available",
                provider="bound-agent-tools",
                latency_ms=0,
            )
        return self.registry.execute(
            ToolCallRequest(
                tool_name=name,
                arguments=arguments,
                context=context,
            )
        )


@dataclass
class ToolRegistry:
    _tools: dict[str, Any] = field(default_factory=dict)
    provider_registry: ProviderRegistry | None = None
    policy_engine: PolicyEngine | None = None

    def start(self) -> None:
        if self.provider_registry is not None:
            self.provider_registry.start()

    def stop(self) -> None:
        if self.provider_registry is not None:
            self.provider_registry.stop()

    def health_snapshot(self) -> dict[str, dict[str, object]]:
        if self.provider_registry is None:
            return {}
        return self.provider_registry.health_snapshot()

    def bind(
        self,
        allowed_tools: tuple[str, ...],
        allowed_tool_tags: tuple[str, ...] = (),
    ) -> BoundAgentTools:
        return BoundAgentTools(
            {name: self._tools[name] for name in allowed_tools if name in self._tools},
            registry=self,
            allowed_tool_tags=allowed_tool_tags,
        )

    def resolve_by_tag(self, tag: str) -> list[Any]:
        resolved: list[Any] = []
        for tool in self._tools.values():
            capability_tags = getattr(tool, "capability_tags", ())
            if tag in capability_tags:
                resolved.append(tool)
        return resolved

    def _executor_for(self, tool: Any):
        backend = getattr(tool, "backend", None)
        if backend is None:
            return None
        if hasattr(backend, "execute"):
            return BackendToolExecutor(backend)
        return None

    def _enforce_policy(self, tool_name: str, request: ToolCallRequest, tool: Any) -> ToolCallResult | None:
        if self.policy_engine is None:
            return None
        profile = get_agent_profile(request.context.agent_name)
        capability_tags = getattr(tool, "capability_tags", ()) or (tool_name,)
        for tag in capability_tags:
            decision = self.policy_engine.evaluate_tool_tag(tag, request.context, profile)
            if not decision.allowed:
                return ToolCallResult(
                    ok=False,
                    output=None,
                    error=decision.reason,
                    provider="policy",
                    latency_ms=0,
                    metadata={
                        "audit": {
                            "decision": "blocked",
                            "tool_name": tool_name,
                            "capability_tag": tag,
                            "provider": "policy",
                            "reason": decision.reason,
                        }
                    },
                )
        return None

    def describe_tool(self, tool_name: str) -> ToolSpec:
        tool = self._tools.get(tool_name)
        if tool is not None:
            return ToolSpec(
                name=tool.name,
                version="1.0",
                description=tool.description,
                capability_tags=tool.capability_tags,
                input_schema={},
                output_schema={},
                side_effect_level=tool.side_effect_level,
                provider=tool.provider,
                metadata={},
            )
        if self.provider_registry is not None:
            return self.provider_registry.describe_tool(tool_name)
        raise KeyError(tool_name)

    def list_tool_specs(self) -> list[ToolSpec]:
        specs = [
            ToolSpec(
                name=tool.name,
                version="1.0",
                description=tool.description,
                capability_tags=tool.capability_tags,
                input_schema={},
                output_schema={},
                side_effect_level=tool.side_effect_level,
                provider=tool.provider,
                metadata={},
            )
            for tool in self._tools.values()
        ]
        if self.provider_registry is not None:
            specs.extend(self.provider_registry.list_tool_specs())
        return sorted(specs, key=lambda spec: spec.name)

    def execute(self, request: ToolCallRequest) -> ToolCallResult:
        tool = self._tools.get(request.tool_name)
        if tool is not None:
            blocked = self._enforce_policy(request.tool_name, request, tool)
            if blocked is not None:
                return blocked
            executor = self._executor_for(tool)
            if executor is not None:
                return executor.execute(request)
            return ToolCallResult(
                ok=False,
                output=None,
                error=f"tool {request.tool_name} has no executable backend",
                provider=getattr(tool, "provider", "local"),
                latency_ms=0,
            )
        if self.provider_registry is not None:
            return self.provider_registry.execute(request)
        return ToolCallResult(
            ok=False,
            output=None,
            error=f"tool {request.tool_name} is not registered",
            provider="tool-registry",
            latency_ms=0,
        )
