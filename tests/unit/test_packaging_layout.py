from __future__ import annotations

import tomllib
from pathlib import Path


def test_pyproject_excludes_mcp_package() -> None:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    config = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    includes = config["tool"]["setuptools"]["packages"]["find"]["include"]

    assert "mcp*" not in includes
