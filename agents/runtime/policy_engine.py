from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from agents.capabilities import AgentProfile, SkillSpec
from agents.runtime.execution_context import ExecutionContext


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str | None = None


@dataclass(frozen=True)
class PolicyEngine:
    external_tool_tags: tuple[str, ...] = ()
    write_tool_tags: tuple[str, ...] = ()

    @classmethod
    def from_file(cls, path: str | Path) -> "PolicyEngine":
        file_path = Path(path)
        if not file_path.is_absolute():
            file_path = Path.cwd() / file_path
        payload = json.loads(file_path.read_text())
        return cls(
            external_tool_tags=tuple(payload.get("external_tool_tags", [])),
            write_tool_tags=tuple(payload.get("write_tool_tags", [])),
        )

    def evaluate_skill(self, skill: SkillSpec, context: ExecutionContext, profile: AgentProfile) -> PolicyDecision:
        if skill.name not in profile.allowed_skills:
            return PolicyDecision(False, "skill not allowed for agent profile")
        return PolicyDecision(True)

    def evaluate_tool_tag(self, tool_tag: str, context: ExecutionContext, profile: AgentProfile) -> PolicyDecision:
        if tool_tag in self.external_tool_tags and not context.external_allowed:
            return PolicyDecision(False, "external access disabled for current execution context")
        if profile.allowed_tool_tags and tool_tag not in profile.allowed_tool_tags:
            return PolicyDecision(False, "tool tag not allowed for agent profile")
        if tool_tag in self.write_tool_tags and not context.write_allowed:
            return PolicyDecision(False, "write access disabled for current execution context")
        return PolicyDecision(True)
