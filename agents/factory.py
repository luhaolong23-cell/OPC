from __future__ import annotations

from agents.coder import CoderAgent
from agents.debugger import DebuggerAgent
from agents.planner import PlannerAgent
from agents.pm import PMAgent
from agents.profiles import get_agent_profile
from agents.roles import get_role_instructions
from agents.reviewer import ReviewerAgent
from agents.runtime.skill_resolver import SkillResolver
from agents.skills.registry import SkillRegistry, get_default_registry
from llm import StructuredLLMClient
from tools.registry import ToolRegistry


_AGENT_TYPES = {
    "pm": PMAgent,
    "planner": PlannerAgent,
    "coder": CoderAgent,
    "debugger": DebuggerAgent,
    "reviewer": ReviewerAgent,
}


def build_agent(
    name: str,
    *,
    model: str | None,
    llm_client: StructuredLLMClient | None,
    tool_registry: ToolRegistry,
    skill_registry: SkillRegistry | None = None,
) -> object:
    profile = get_agent_profile(name)
    agent_type = _AGENT_TYPES[name]
    skill_registry = skill_registry or get_default_registry()
    skill_resolver = SkillResolver(skills={}, registry=skill_registry)
    skills = skill_resolver.resolve_many(profile.allowed_skills)
    return agent_type(
        model=model,
        llm_client=llm_client,
        profile=profile,
        skills=skills,
        skill_resolver=skill_resolver,
        tools=tool_registry.bind(profile.allowed_tools, allowed_tool_tags=profile.allowed_tool_tags),
        role_instructions=get_role_instructions(profile.role_name),
    )
