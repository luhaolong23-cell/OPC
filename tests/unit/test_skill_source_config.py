from __future__ import annotations

from agents.skills.registry import SkillRegistry
from agents.skills.sources import load_skill_sources_file


def test_load_skill_sources_file_builds_builtin_and_codex_sources() -> None:
    sources = load_skill_sources_file("tests/contracts/samples/skill_sources_config.json")

    assert [source.name for source in sources] == ["builtin", "codex"]


def test_skill_registry_from_source_config_resolves_external_codex_skill() -> None:
    registry = SkillRegistry.from_file("tests/contracts/samples/skill_sources_config.json")

    skill = registry.get_skill("pm.discovery.external")

    assert skill.name == "pm.discovery.external"
    assert skill.metadata["source"] == "codex-skill"
