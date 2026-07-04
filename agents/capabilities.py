from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SkillSpec:
    name: str
    instructions: str
    required_inputs: tuple[str, ...]
    output_keys: tuple[str, ...]
    version: str = "1.0"
    description: str = ""
    role: str = ""
    intent: str = ""
    optional_inputs: tuple[str, ...] = ()
    output_schema: dict[str, Any] = field(default_factory=dict)
    allowed_tool_tags: tuple[str, ...] = ()
    default_tool_chain: tuple[str, ...] = ()
    side_effect_level: str = "read"
    timeout_seconds: float | None = None
    retry_policy: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentProfile:
    name: str
    role_name: str
    default_skill: str
    allowed_skills: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    allowed_tool_tags: tuple[str, ...] = ()
