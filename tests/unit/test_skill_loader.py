from __future__ import annotations

from agents.skills import get_skill, get_skills
from agents.skills.loader import load_skill_file


def test_load_skill_file_reads_builtin_skill_metadata() -> None:
    skill = load_skill_file("agents/skills/builtin/pm.discovery.yaml")

    assert skill.name == "pm.discovery"
    assert skill.version == "1.0"
    assert skill.required_inputs == ("requirement", "conversation")
    assert skill.output_keys == ("summary", "open_questions", "constraints")
    assert skill.allowed_tool_tags == ("repo.read", "repo.search", "code.parse")


def test_skill_registry_keeps_existing_get_skill_api() -> None:
    skill = get_skill("pm.discovery")
    selected = get_skills(("pm.discovery", "pm.specify"))

    assert skill.name == "pm.discovery"
    assert set(selected) == {"pm.discovery", "pm.specify"}
