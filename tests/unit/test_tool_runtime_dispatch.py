from __future__ import annotations

from dataclasses import dataclass

from agents.runtime.execution_context import ExecutionContext
from tools.defaults import ToolHandle
from tools.registry import ToolRegistry
from tools.runtime import BackendToolExecutor
from tools.specs import ToolCallRequest


@dataclass
class FakeExecutor:
    provider: str = "local"

    def execute(self, request: ToolCallRequest):
        return {
            "ok": True,
            "output": {"echo": request.arguments["query"]},
            "error": None,
            "provider": self.provider,
            "latency_ms": 1,
        }


def test_tool_registry_executes_named_tool_via_runtime_dispatch() -> None:
    registry = ToolRegistry(
        {
            "docs_search": ToolHandle(
                "docs_search",
                "Search docs.",
                backend=BackendToolExecutor(FakeExecutor()),
                capability_tags=("docs.search",),
                provider="local",
            )
        }
    )
    request = ToolCallRequest(
        tool_name="docs_search",
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

    result = registry.execute(request)

    assert result.ok is True
    assert result.output == {"echo": "fastapi"}
    assert result.provider == "local"


def test_backend_tool_executor_wraps_existing_executor_backend() -> None:
    executor = BackendToolExecutor(FakeExecutor(provider="memory"))
    request = ToolCallRequest(
        tool_name="memory.lookup",
        arguments={"query": "design doc"},
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

    result = executor.execute(request)

    assert result.ok is True
    assert result.provider == "memory"
