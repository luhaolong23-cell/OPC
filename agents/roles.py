from __future__ import annotations

from pathlib import Path


_ROLES_DIR = Path(__file__).resolve().parent / "roles"


def get_role_instructions(name: str) -> str:
    path = _ROLES_DIR / f"{name}.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()
