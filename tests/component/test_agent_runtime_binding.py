from __future__ import annotations

from agents.factory import build_agent
from agents.runtime.skill_resolver import SkillResolver
from agents.skills.registry import SkillRegistry
from tools.registry import ToolRegistry


class FakeLLMClient:
    def generate_json(self, *, instructions: str, input_text: str) -> dict:
        return {"summary": "implemented", "modified_files": {}}


def test_build_agent_injects_skill_resolver_without_breaking_legacy_skills() -> None:
    registry = ToolRegistry(
        {
            "repo_reader": object(),
            "patch_applier": object(),
            "test_runner": object(),
        }
    )

    agent = build_agent("coder", model="gpt-coder", llm_client=FakeLLMClient(), tool_registry=registry)

    assert isinstance(agent.skill_resolver, SkillResolver)
    assert agent.skill_resolver.resolve("coder.implement").name == "coder.implement"
    assert set(agent.skills) == {"coder.implement", "coder.tdd", "coder.spec_driven"}


def test_build_agent_prefers_runtime_skill_registry_for_profile_skill_loading() -> None:
    tool_registry = ToolRegistry(
        {
            "repo_reader": object(),
            "rg_search": object(),
            "py_tree_sitter_parse": object(),
        }
    )
    skill_registry = SkillRegistry.from_file("tests/contracts/samples/skill_sources_override_config.json")

    agent = build_agent(
        "pm",
        model="gpt-pm",
        llm_client=FakeLLMClient(),
        tool_registry=tool_registry,
        skill_registry=skill_registry,
    )

    assert agent.skills["pm.discovery"].metadata["source"] == "codex-skill"
    assert "Use external override discovery instructions." in agent.skills["pm.discovery"].instructions
    assert agent.skill_resolver.resolve("pm.discovery").metadata["source"] == "codex-skill"
