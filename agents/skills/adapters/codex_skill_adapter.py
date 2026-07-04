from __future__ import annotations

from pathlib import Path

from agents.capabilities import SkillSpec


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text.strip()
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return {}, text.strip()
    front_matter = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        front_matter[key.strip()] = value.strip()
    return front_matter, parts[2].strip()


def load_codex_skill_file(path: str | Path) -> SkillSpec:
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = Path.cwd() / file_path
    front_matter, body = _parse_front_matter(file_path.read_text())
    name = front_matter.get("name", file_path.stem)
    description = front_matter.get("description", "")
    role = name.split(".", 1)[0] if "." in name else ""
    return SkillSpec(
        name=name,
        version="1.0",
        description=description,
        role=role,
        intent=description or name,
        instructions=body,
        required_inputs=(),
        optional_inputs=(),
        output_keys=(),
        output_schema={},
        allowed_tool_tags=(),
        default_tool_chain=(),
        side_effect_level="read",
        metadata={
            "source": "codex-skill",
            "source_path": str(file_path),
        },
    )
