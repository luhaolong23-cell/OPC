from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from agents.capabilities import SkillSpec
from agents.skills.adapters.codex_skill_adapter import load_codex_skill_file
from agents.skills.loader import load_skill_file


class SkillSource(Protocol):
    name: str

    def load(self, name: str) -> SkillSpec | None: ...
    def list_names(self) -> tuple[str, ...]: ...


@dataclass(frozen=True)
class BuiltinSkillSource:
    root: Path
    name: str = "builtin"

    @classmethod
    def from_default_root(cls) -> "BuiltinSkillSource":
        return cls(root=Path(__file__).resolve().parent / "builtin")

    def load(self, name: str) -> SkillSpec | None:
        path = self.root / f"{name}.yaml"
        if not path.exists():
            return None
        return load_skill_file(path)

    def list_names(self) -> tuple[str, ...]:
        return tuple(sorted(path.stem for path in self.root.glob("*.yaml")))


@dataclass(frozen=True)
class CodexSkillSource:
    paths: tuple[str, ...]
    name: str = "codex"

    def _resolved_paths(self) -> tuple[Path, ...]:
        resolved: list[Path] = []
        for raw_path in self.paths:
            path = Path(raw_path)
            if not path.is_absolute():
                path = Path.cwd() / path
            if path.exists():
                resolved.append(path)
        return tuple(resolved)

    def load(self, name: str) -> SkillSpec | None:
        for path in self._resolved_paths():
            skill = load_codex_skill_file(path)
            if skill.name == name:
                return skill
        return None

    def list_names(self) -> tuple[str, ...]:
        names: list[str] = []
        for path in self._resolved_paths():
            names.append(load_codex_skill_file(path).name)
        return tuple(names)


def load_skill_sources_file(path: str | Path) -> tuple[SkillSource, ...]:
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = Path.cwd() / file_path
    payload = json.loads(file_path.read_text())
    sources: list[SkillSource] = []
    for item in payload.get("sources", []):
        source_type = item["type"]
        source_name = item.get("name")
        if source_type == "builtin":
            root = item.get("root")
            source = BuiltinSkillSource(
                root=Path(root) if root else BuiltinSkillSource.from_default_root().root,
                name=source_name or "builtin",
            )
        elif source_type == "codex":
            source = CodexSkillSource(
                paths=tuple(item.get("paths", [])),
                name=source_name or "codex",
            )
        else:
            raise ValueError(f"unsupported skill source type: {source_type}")
        sources.append(source)
    return tuple(sources)
