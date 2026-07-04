from __future__ import annotations

from agents.capabilities import AgentProfile, SkillSpec
from agents.runtime.execution_context import ExecutionContext


def test_skill_spec_supports_runtime_metadata_without_breaking_legacy_shape() -> None:
    skill = SkillSpec(
        name="coder.implement",
        instructions="Implement the task and return JSON.",
        required_inputs=("plan", "current_files", "task_description"),
        output_keys=("modified_files", "summary"),
        version="1.0",
        description="Default implementation skill for coder.",
        intent="implement approved plan items",
        optional_inputs=("human_feedback",),
        output_schema={
            "type": "object",
            "required": ["modified_files", "summary"],
        },
        allowed_tool_tags=("repo.read", "code.patch", "test.run"),
        default_tool_chain=("repo_reader", "patch_applier", "test_runner"),
        side_effect_level="write",
        timeout_seconds=60.0,
        retry_policy="never",
        metadata={"owner": "core"},
    )

    assert skill.name == "coder.implement"
    assert skill.version == "1.0"
    assert skill.optional_inputs == ("human_feedback",)
    assert skill.allowed_tool_tags == ("repo.read", "code.patch", "test.run")
    assert skill.output_keys == ("modified_files", "summary")
    assert skill.metadata == {"owner": "core"}


def test_agent_profile_supports_tool_tags_alongside_legacy_allowed_tools() -> None:
    profile = AgentProfile(
        name="coder",
        role_name="coder",
        default_skill="coder.implement",
        allowed_skills=("coder.implement", "coder.tdd"),
        allowed_tools=("repo_reader", "patch_applier", "test_runner"),
        allowed_tool_tags=("repo.read", "code.patch", "test.run"),
    )

    assert profile.allowed_tools == ("repo_reader", "patch_applier", "test_runner")
    assert profile.allowed_tool_tags == ("repo.read", "code.patch", "test.run")


def test_execution_context_captures_stage_and_environment_constraints() -> None:
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

    assert context.agent_name == "coder"
    assert context.workflow_stage == "coding"
    assert context.network_allowed is False
