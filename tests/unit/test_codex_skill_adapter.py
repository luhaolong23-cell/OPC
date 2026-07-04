from __future__ import annotations

from agents.skills.adapters.codex_skill_adapter import load_codex_skill_file


def test_load_codex_skill_file_maps_markdown_skill_to_skill_spec() -> None:
    skill = load_codex_skill_file("tests/contracts/samples/sample_codex_skill.md")

    assert skill.name == "pm.discovery.external"
    assert skill.description == "Discovery skill for external requirements."
    assert skill.instructions.startswith("Use collaborative discovery")
    assert skill.metadata["source"] == "codex-skill"
    assert skill.version == "1.0"
