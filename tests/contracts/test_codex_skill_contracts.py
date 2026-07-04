from __future__ import annotations

from agents.skills.adapters.codex_skill_adapter import load_codex_skill_file


def test_codex_skill_contract_keeps_front_matter_name_description_and_body() -> None:
    skill = load_codex_skill_file("tests/contracts/samples/sample_codex_skill.md")

    assert skill.name == "pm.discovery.external"
    assert skill.description == "Discovery skill for external requirements."
    assert "Current repo context first." in skill.instructions
    assert skill.metadata["source_path"].endswith("sample_codex_skill.md")
