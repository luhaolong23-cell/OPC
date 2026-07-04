from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from agents.capabilities import SkillSpec
from agents.skills.sources import BuiltinSkillSource, SkillSource, load_skill_sources_file


_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "skills" / "sources.yaml"


@dataclass
class SkillRegistry:
    sources: tuple[SkillSource, ...] = (BuiltinSkillSource.from_default_root(),)
    _cache: dict[str, SkillSpec] = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: str | Path) -> "SkillRegistry":
        return cls(sources=load_skill_sources_file(path))

    def list_sources(self) -> tuple[str, ...]:
        return tuple(source.name for source in self.sources)

    def list_skills(self) -> tuple[str, ...]:
        names: list[str] = []
        for source in self.sources:
            for name in source.list_names():
                if name not in names:
                    names.append(name)
        return tuple(names)

    def get_skill_from(self, source_name: str, skill_name: str) -> SkillSpec:
        for source in self.sources:
            if source.name != source_name:
                continue
            skill = source.load(skill_name)
            if skill is not None:
                self._cache[skill_name] = skill
                return skill
            break
        raise KeyError(f"skill {skill_name} not found in source {source_name}")

    def get_skill(self, name: str) -> SkillSpec:
        if name in self._cache:
            return self._cache[name]
        for source in self.sources:
            skill = source.load(name)
            if skill is not None:
                self._cache[name] = skill
                return skill
        raise KeyError(name)

    def get_skills(self, names: tuple[str, ...]) -> dict[str, SkillSpec]:
        return {name: self.get_skill(name) for name in names}


_DEFAULT_REGISTRY = SkillRegistry.from_file(_DEFAULT_CONFIG_PATH) if _DEFAULT_CONFIG_PATH.exists() else SkillRegistry()


def get_default_registry() -> SkillRegistry:
    return _DEFAULT_REGISTRY


def list_skills() -> tuple[str, ...]:
    return _DEFAULT_REGISTRY.list_skills()


def get_skill(name: str) -> SkillSpec:
    return _DEFAULT_REGISTRY.get_skill(name)


def get_skills(names: tuple[str, ...]) -> dict[str, SkillSpec]:
    return _DEFAULT_REGISTRY.get_skills(names)
