from __future__ import annotations

from agents.capabilities import SkillSpec
from agents.pm import PMAgent
from agents.runtime.skill_resolver import SkillResolver
from agents.skills.sources import CodexSkillSource


class FakeLLMClient:
    def __init__(self) -> None:
        self.instructions: str | None = None

    def generate_json(self, *, instructions: str, input_text: str) -> dict:
        self.instructions = instructions
        return {"summary": "ok", "open_questions": [], "constraints": []}


def test_skill_resolver_returns_skill_by_name() -> None:
    skill = SkillSpec(
        name="pm.discovery",
        instructions="custom instructions",
        required_inputs=("requirement", "conversation"),
        output_keys=("summary", "open_questions", "constraints"),
    )
    resolver = SkillResolver(skills={"pm.discovery": skill})

    resolved = resolver.resolve("pm.discovery")

    assert resolved is skill


def test_agent_uses_skill_resolver_when_legacy_skill_dict_is_empty() -> None:
    llm = FakeLLMClient()
    skill = SkillSpec(
        name="pm.discovery",
        instructions="resolver instructions",
        required_inputs=("requirement", "conversation"),
        output_keys=("summary", "open_questions", "constraints"),
    )
    agent = PMAgent(
        model="gpt-pm",
        llm_client=llm,
        skills={},
        skill_resolver=SkillResolver(skills={"pm.discovery": skill}),
    )

    agent.run("build todo api")

    assert llm.instructions == "resolver instructions"


def test_skill_resolver_can_resolve_external_codex_skill_source() -> None:
    resolver = SkillResolver(
        skills={},
        sources=(
            CodexSkillSource(
                paths=("tests/contracts/samples/sample_codex_skill.md",),
            ),
        ),
    )

    resolved = resolver.resolve("pm.discovery.external")

    assert resolved.name == "pm.discovery.external"
    assert resolved.metadata["source"] == "codex-skill"
