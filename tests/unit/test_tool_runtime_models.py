from __future__ import annotations

from agents.runtime.execution_context import ExecutionContext
from tools.specs import ToolCallRequest, ToolCallResult, ToolSpec


def test_tool_spec_supports_capability_tags_and_provider_metadata() -> None:
    spec = ToolSpec(
        name="docs.search",
        version="1.0",
        description="Search technical documentation.",
        capability_tags=("docs.search", "knowledge.read"),
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        side_effect_level="read",
        provider="context7",
        metadata={"priority": 100},
    )

    assert spec.name == "docs.search"
    assert spec.capability_tags == ("docs.search", "knowledge.read")
    assert spec.provider == "context7"


def test_tool_call_request_and_result_capture_execution_context() -> None:
    context = ExecutionContext(
        agent_name="pm",
        workflow_stage="discovery",
        project_type="python",
        environment="local",
        user_mode="interactive",
        network_allowed=True,
        write_allowed=False,
        external_allowed=True,
    )
    request = ToolCallRequest(
        tool_name="docs.search",
        arguments={"query": "fastapi testing"},
        context=context,
    )
    result = ToolCallResult(
        ok=True,
        output={"items": []},
        error=None,
        provider="context7",
        latency_ms=42,
        metadata={"audit": {"selected_provider": "context7"}},
    )

    assert request.context.agent_name == "pm"
    assert request.arguments["query"] == "fastapi testing"
    assert result.ok is True
    assert result.provider == "context7"
    assert result.metadata["audit"]["selected_provider"] == "context7"
