from __future__ import annotations

from dataclasses import dataclass, field

from tools.providers.registry import ProviderRegistry


@dataclass
class FakeMCPRegistry:
    events: list[str] = field(default_factory=list)

    def start(self) -> None:
        self.events.append("start")

    def stop(self) -> None:
        self.events.append("stop")

    def health_snapshot(self) -> dict[str, dict[str, object]]:
        return {"context7": {"healthy": True}}


def test_provider_registry_lifecycle_calls_nested_mcp_registry() -> None:
    mcp_registry = FakeMCPRegistry()
    registry = ProviderRegistry(mcp_registry=mcp_registry)

    registry.start()
    snapshot = registry.health_snapshot()
    registry.stop()

    assert mcp_registry.events == ["start", "stop"]
    assert snapshot["context7"]["healthy"] is True
