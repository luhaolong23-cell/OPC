from __future__ import annotations

from agents.skills.registry import SkillRegistry
from agents.skills.sources import BuiltinSkillSource, CodexSkillSource


def test_skill_registry_lists_builtin_and_external_skill_names() -> None:
    registry = SkillRegistry(
        sources=(
            BuiltinSkillSource.from_default_root(),
            CodexSkillSource(paths=("tests/contracts/samples/sample_codex_skill.md",)),
        )
    )

    names = registry.list_skills()

    assert "pm.discovery" in names
    assert "pm.discovery.external" in names


def test_skill_registry_prefers_first_matching_source_order() -> None:
    registry = SkillRegistry(
        sources=(
            CodexSkillSource(paths=("tests/contracts/samples/sample_codex_skill.md",)),
            BuiltinSkillSource.from_default_root(),
        )
    )

    skill = registry.get_skill("pm.discovery.external")

    assert skill.metadata["source"] == "codex-skill"


def test_skill_registry_can_read_same_skill_name_from_specific_source() -> None:
    registry = SkillRegistry(
        sources=(
            CodexSkillSource(paths=("tests/contracts/samples/sample_codex_skill_override.md",), name="codex"),
            BuiltinSkillSource.from_default_root(),
        )
    )

    builtin_skill = registry.get_skill_from("builtin", "pm.discovery")
    codex_skill = registry.get_skill_from("codex", "pm.discovery")

    assert builtin_skill.metadata.get("source") != "codex-skill"
    assert codex_skill.metadata["source"] == "codex-skill"
