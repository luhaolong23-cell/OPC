from __future__ import annotations

from dataclasses import dataclass

from agents.runtime.execution_context import ExecutionContext
from agents.runtime.policy_engine import PolicyEngine
from tools.defaults import ToolHandle
from tools.registry import ToolRegistry
from tools.runtime import BackendToolExecutor
from tools.specs import ToolCallRequest


@dataclass
class FakeExecutor:
    def execute(self, request: ToolCallRequest):
        return {
            "ok": True,
            "output": {"patched": True},
            "error": None,
            "provider": "local",
            "latency_ms": 1,
        }


def test_tool_registry_blocks_direct_local_execution_when_policy_disallows_tool_tag() -> None:
    registry = ToolRegistry(
        _tools={
            "patch_applier": ToolHandle(
                "patch_applier",
                "Apply patches.",
                backend=BackendToolExecutor(FakeExecutor()),
                capability_tags=("code.patch",),
                side_effect_level="write",
            )
        },
        policy_engine=PolicyEngine.from_file("config/policies/default.yaml"),
    )

    result = registry.execute(
        ToolCallRequest(
            tool_name="patch_applier",
            arguments={"diff": "patch"},
            context=ExecutionContext(
                agent_name="reviewer",
                workflow_stage="review",
                project_type="python",
                environment="local",
                user_mode="interactive",
                network_allowed=False,
                write_allowed=False,
                external_allowed=False,
            ),
        )
    )

    assert result.ok is False
    assert result.error == "tool tag not allowed for agent profile"
