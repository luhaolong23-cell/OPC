from __future__ import annotations

from dataclasses import dataclass, field

from agents.capabilities import SkillSpec
from agents.skills.registry import SkillRegistry, get_skill, get_skills
from agents.skills.sources import BuiltinSkillSource, SkillSource


@dataclass
class SkillResolver:
    skills: dict[str, SkillSpec] = field(default_factory=dict)
    sources: tuple[SkillSource, ...] = (BuiltinSkillSource.from_default_root(),)
    registry: SkillRegistry | None = None

    def _registry(self) -> SkillRegistry:
        if self.registry is not None:
            return self.registry
        self.registry = SkillRegistry(sources=self.sources, _cache=self.skills)
        return self.registry

    def resolve(self, name: str) -> SkillSpec:
        if name in self.skills:
            return self.skills[name]
        try:
            skill = self._registry().get_skill(name)
        except KeyError:
            skill = get_skill(name)
        self.skills[name] = skill
        return skill

    def resolve_many(self, names: tuple[str, ...]) -> dict[str, SkillSpec]:
        resolved: dict[str, SkillSpec] = {}
        missing: list[str] = []
        for name in names:
            if name in self.skills:
                resolved[name] = self.skills[name]
                continue
            try:
                skill = self._registry().get_skill(name)
            except KeyError:
                missing.append(name)
                continue
            self.skills[name] = skill
            resolved[name] = skill
        if missing:
            builtin = get_skills(tuple(missing))
            self.skills.update(builtin)
            resolved.update(builtin)
        return resolved
