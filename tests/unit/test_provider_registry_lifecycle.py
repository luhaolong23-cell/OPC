from __future__ import annotations

from dataclasses import dataclass, field

from tools.providers.registry import ProviderRegistry


@dataclass
class FakeLifecycleExecutor:
    events: list[str] = field(default_factory=list)

    def start(self) -> None:
        self.events.append("start")

    def stop(self) -> None:
        self.events.append("stop")

    def health(self) -> dict[str, object]:
        return {"healthy": True, "detail": "ok"}

    def execute(self, request):
        return {
            "ok": True,
            "output": {"events": list(self.events)},
            "error": None,
            "provider": "local",
            "latency_ms": 1,
        }


def test_provider_registry_reports_registered_provider_health_snapshot() -> None:
    executor = FakeLifecycleExecutor()
    registry = ProviderRegistry()
    registry.register_executor(
        "workspace.write",
        executor,
        capability_tags=("workspace.write",),
        provider_name="local_workspace",
    )

    snapshot = registry.health_snapshot()

    assert snapshot["local_workspace"]["healthy"] is True
    assert snapshot["local_workspace"]["detail"] == "ok"


def test_provider_registry_start_and_stop_call_registered_provider_lifecycle() -> None:
    executor = FakeLifecycleExecutor()
    registry = ProviderRegistry()
    registry.register_executor(
        "workspace.write",
        executor,
        capability_tags=("workspace.write",),
        provider_name="local_workspace",
    )

    registry.start()
    registry.stop()

    assert executor.events == ["start", "stop"]
