from __future__ import annotations

from agents.profiles import get_agent_profile
from agents.runtime.execution_context import ExecutionContext
from agents.runtime.policy_engine import PolicyEngine


def test_policy_engine_allows_pm_to_use_docs_search_in_discovery() -> None:
    engine = PolicyEngine.from_file("config/policies/default.yaml")
    profile = get_agent_profile("pm")
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

    decision = engine.evaluate_tool_tag("docs.search", context, profile)

    assert decision.allowed is True


def test_policy_engine_blocks_coder_external_docs_search_in_offline_mode() -> None:
    engine = PolicyEngine.from_file("config/policies/default.yaml")
    profile = get_agent_profile("coder")
    context = ExecutionContext(
        agent_name="coder",
        workflow_stage="coding",
        project_type="python",
        environment="local",
        user_mode="interactive",
        network_allowed=False,
        write_allowed=True,
        external_allowed=False,
    )

    decision = engine.evaluate_tool_tag("docs.search", context, profile)

    assert decision.allowed is False
    assert decision.reason == "external access disabled for current execution context"


def test_policy_engine_blocks_reviewer_from_write_side_effects() -> None:
    engine = PolicyEngine.from_file("config/policies/default.yaml")
    profile = get_agent_profile("reviewer")
    context = ExecutionContext(
        agent_name="reviewer",
        workflow_stage="review",
        project_type="python",
        environment="local",
        user_mode="interactive",
        network_allowed=False,
        write_allowed=False,
        external_allowed=False,
    )

    decision = engine.evaluate_tool_tag("code.patch", context, profile)

    assert decision.allowed is False
    assert decision.reason == "tool tag not allowed for agent profile"
