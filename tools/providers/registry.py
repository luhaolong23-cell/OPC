from __future__ import annotations

from dataclasses import dataclass, field

from agents.profiles import get_agent_profile
from agents.runtime.policy_engine import PolicyEngine
from tools.specs import ToolCallRequest, ToolCallResult, ToolSpec


@dataclass
class RegisteredExecutor:
    executor: object
    capability_tags: tuple[str, ...] = ()
    provider_name: str = "local"
    description: str | None = None
    side_effect_level: str = "read"


@dataclass
class ProviderRegistry:
    executors: dict[str, RegisteredExecutor] = field(default_factory=dict)
    policy_engine: PolicyEngine | None = None

    def register_executor(
        self,
        name: str,
        executor: object,
        capability_tags: tuple[str, ...] = (),
        provider_name: str = "local",
        description: str | None = None,
        side_effect_level: str = "read",
    ) -> None:
        self.executors[name] = RegisteredExecutor(
            executor=executor,
            capability_tags=capability_tags,
            provider_name=provider_name,
            description=description,
            side_effect_level=side_effect_level,
        )

    def start(self) -> None:
        seen: set[int] = set()
        for registered in self.executors.values():
            executor = registered.executor
            marker = id(executor)
            if marker in seen:
                continue
            seen.add(marker)
            if hasattr(executor, "start"):
                executor.start()

    def stop(self) -> None:
        seen: set[int] = set()
        for registered in self.executors.values():
            executor = registered.executor
            marker = id(executor)
            if marker in seen:
                continue
            seen.add(marker)
            if hasattr(executor, "stop"):
                executor.stop()

    def health_snapshot(self) -> dict[str, dict[str, object]]:
        snapshot: dict[str, dict[str, object]] = {}
        seen: set[tuple[str, int]] = set()
        for registered in self.executors.values():
            executor = registered.executor
            key = (registered.provider_name, id(executor))
            if key in seen:
                continue
            seen.add(key)
            if hasattr(executor, "health"):
                status = executor.health()
                snapshot[registered.provider_name] = dict(status)
            else:
                snapshot[registered.provider_name] = {"healthy": True, "detail": "unknown"}
        return snapshot

    def describe_tool(self, tool_name: str) -> ToolSpec:
        registered = self.executors.get(tool_name)
        if registered is None:
            raise KeyError(tool_name)
        return ToolSpec(
            name=tool_name,
            version="1.0",
            description=registered.description or tool_name,
            capability_tags=registered.capability_tags,
            input_schema={},
            output_schema={},
            side_effect_level=registered.side_effect_level,
            provider=registered.provider_name,
            metadata={},
        )

    def list_tool_specs(self) -> list[ToolSpec]:
        specs = [
            ToolSpec(
                name=tool_name,
                version="1.0",
                description=registered.description or tool_name,
                capability_tags=registered.capability_tags,
                input_schema={},
                output_schema={},
                side_effect_level=registered.side_effect_level,
                provider=registered.provider_name,
                metadata={},
            )
            for tool_name, registered in sorted(self.executors.items())
        ]
        return sorted(specs, key=lambda spec: spec.name)

    def _enforce_policy(self, tool_name: str, capability_tags: tuple[str, ...], request: ToolCallRequest) -> ToolCallResult | None:
        if self.policy_engine is None:
            return None
        profile = get_agent_profile(request.context.agent_name)
        tags = capability_tags or (tool_name,)
        for tag in tags:
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

    def execute(self, request: ToolCallRequest) -> ToolCallResult:
        registered = self.executors.get(request.tool_name)
        if registered is not None and hasattr(registered.executor, "execute"):
            blocked = self._enforce_policy(request.tool_name, registered.capability_tags, request)
            if blocked is not None:
                return blocked
            return registered.executor.execute(request)
        return ToolCallResult(
            ok=False,
            output=None,
            error=f"no provider available for tool {request.tool_name}",
            provider="provider-registry",
            latency_ms=0,
        )
