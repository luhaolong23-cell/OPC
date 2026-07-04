from __future__ import annotations

import json
from pathlib import Path

from agents.capabilities import SkillSpec


_TUPLE_FIELDS = (
    "required_inputs",
    "optional_inputs",
    "output_keys",
    "allowed_tool_tags",
    "default_tool_chain",
)


def _normalize_skill_payload(payload: dict) -> dict:
    normalized = dict(payload)
    for field_name in _TUPLE_FIELDS:
        value = normalized.get(field_name)
        if value is not None and not isinstance(value, tuple):
            normalized[field_name] = tuple(value)
    return normalized


def load_skill_file(path: str | Path) -> SkillSpec:
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = Path.cwd() / file_path
    payload = json.loads(file_path.read_text())
    return SkillSpec(**_normalize_skill_payload(payload))
