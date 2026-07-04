from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from agents.capabilities import AgentProfile, SkillSpec
from agents.runtime.skill_resolver import SkillResolver
from llm import StructuredLLMClient
from tools.registry import BoundAgentTools


class BaseAgent(ABC):
    def __init__(
        self,
        *,
        model: str | None = None,
        llm_client: StructuredLLMClient | None = None,
        profile: AgentProfile | None = None,
        skills: dict[str, SkillSpec] | None = None,
        skill_resolver: SkillResolver | None = None,
        tools: BoundAgentTools | None = None,
        role_instructions: str = "",
    ) -> None:
        self.model = model
        self.llm_client = llm_client
        self.profile = profile
        self.skills = skills or {}
        self.skill_resolver = skill_resolver or SkillResolver(skills=dict(self.skills))
        self.tools = tools or BoundAgentTools({})
        self.role_instructions = role_instructions

    def skill_instructions(self, skill_name: str, default: str) -> str:
        skill = self.skills.get(skill_name)
        if skill is None:
            skill = self.skill_resolver.resolve(skill_name)
            self.skills[skill_name] = skill
        return skill.instructions if skill is not None else default

    def build_instructions(self, skill_name: str, default: str) -> str:
        instructions = self.skill_instructions(skill_name, default)
        if not self.role_instructions:
            return instructions
        return f"{self.role_instructions}\n\n## Current Task\n{instructions}"

    @abstractmethod
    def run(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError
