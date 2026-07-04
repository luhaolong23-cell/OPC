from __future__ import annotations

from dataclasses import dataclass, field

from mcp.config import MCPServerConfig
from tools.providers.mcp.provider_registry import MCPProviderRegistry


@dataclass
class FakeMCPHandle:
    events: list[str] = field(default_factory=list)

    def start(self) -> None:
        self.events.append("start")

    def stop(self) -> None:
        self.events.append("stop")

    def list_tools(self) -> list[dict]:
        return []

    def list_resources(self) -> list[dict]:
        return []


def test_mcp_provider_registry_supports_start_stop_and_health_snapshot() -> None:
    handle = FakeMCPHandle()
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
        handle=handle,
    )

    registry.start()
    snapshot = registry.health_snapshot()
    registry.stop()

    assert handle.events == ["start", "stop"]
    assert snapshot["context7"]["healthy"] is True
