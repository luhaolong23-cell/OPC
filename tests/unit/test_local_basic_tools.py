from __future__ import annotations

from pathlib import Path

from agents.runtime.execution_context import ExecutionContext
from tools.defaults import build_default_tool_registry
from tools.specs import ToolCallRequest


def _context(*, agent_name: str, write_allowed: bool = False) -> ExecutionContext:
    return ExecutionContext(
        agent_name=agent_name,
        workflow_stage="tool-test",
        project_type="python",
        environment="local",
        user_mode="interactive",
        network_allowed=False,
        write_allowed=write_allowed,
        external_allowed=False,
    )


def test_repo_reader_reads_requested_files_from_root_dir(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "app.py").write_text("print('ok')\n")

    registry = build_default_tool_registry()

    result = registry.execute(
        ToolCallRequest(
            tool_name="repo_reader",
            arguments={"root_dir": str(project_root), "paths": ["app.py"]},
            context=_context(agent_name="coder"),
        )
    )

    assert result.ok is True
    assert result.output == {
        "files": {"app.py": "print('ok')\n"},
        "missing_paths": [],
    }


def test_patch_applier_writes_requested_files_under_root_dir(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()

    registry = build_default_tool_registry()

    result = registry.execute(
        ToolCallRequest(
            tool_name="patch_applier",
            arguments={
                "root_dir": str(project_root),
                "files": {"pkg/app.py": "print('patched')\n"},
            },
            context=_context(agent_name="coder", write_allowed=True),
        )
    )

    assert result.ok is True
    assert result.output == {"written_files": ["pkg/app.py"]}
    assert (project_root / "pkg" / "app.py").read_text() == "print('patched')\n"


def test_log_reader_reads_log_file_contents(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "run.log").write_text("traceback\nboom\n")

    registry = build_default_tool_registry()

    result = registry.execute(
        ToolCallRequest(
            tool_name="log_reader",
            arguments={"root_dir": str(project_root), "path": "run.log"},
            context=_context(agent_name="debugger"),
        )
    )

    assert result.ok is True
    assert result.output == {"path": "run.log", "content": "traceback\nboom\n"}


def test_rg_search_returns_matching_lines(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "app.py").write_text("alpha\nbeta target\n")
    (project_root / "notes.txt").write_text("target here too\n")

    registry = build_default_tool_registry()

    result = registry.execute(
        ToolCallRequest(
            tool_name="rg_search",
            arguments={"root_dir": str(project_root), "pattern": "target"},
            context=_context(agent_name="pm"),
        )
    )

    assert result.ok is True
    assert result.output == {
        "matches": [
            {"path": "app.py", "line": 2, "text": "beta target"},
            {"path": "notes.txt", "line": 1, "text": "target here too"},
        ]
    }


def test_test_runner_executes_pytest_against_code_files() -> None:
    registry = build_default_tool_registry()

    result = registry.execute(
        ToolCallRequest(
            tool_name="test_runner",
            arguments={
                "code_files": {
                    "test_sample.py": "def test_ok():\n    assert 1 + 1 == 2\n",
                }
            },
            context=_context(agent_name="coder", write_allowed=True),
        )
    )

    assert result.ok is True
    assert result.output["status"] == "passed"
    assert result.output["failure_type"] is None


def test_py_tree_sitter_parse_reports_python_symbols() -> None:
    registry = build_default_tool_registry()

    result = registry.execute(
        ToolCallRequest(
            tool_name="py_tree_sitter_parse",
            arguments={
                "code_files": {
                    "app.py": "import os\n\nclass App:\n    pass\n\ndef helper():\n    return 1\n",
                }
            },
            context=_context(agent_name="pm"),
        )
    )

    assert result.ok is True
    assert result.output == {
        "files": {
            "app.py": {
                "imports": ["os"],
                "classes": ["App"],
                "functions": ["helper"],
            }
        }
    }


def test_structure_summary_lists_top_level_entries_from_root_dir(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    (project_root / "api").mkdir(parents=True)
    (project_root / "tests").mkdir(parents=True)
    (project_root / "api" / "routes.py").write_text("def route():\n    return 'ok'\n")
    (project_root / "tests" / "test_api.py").write_text("def test_ok():\n    assert True\n")

    registry = build_default_tool_registry()

    result = registry.execute(
        ToolCallRequest(
            tool_name="structure_summary",
            arguments={"root_dir": str(project_root)},
            context=_context(agent_name="planner"),
        )
    )

    assert result.ok is True
    assert result.output == {
        "top_level_entries": ["api", "tests"],
        "files": ["api/routes.py", "tests/test_api.py"],
        "file_count": 2,
    }


def test_ast_grep_search_finds_named_python_nodes() -> None:
    registry = build_default_tool_registry()

    result = registry.execute(
        ToolCallRequest(
            tool_name="ast_grep_search",
            arguments={
                "code_files": {
                    "app.py": "def helper():\n    return 1\n\nclass App:\n    pass\n",
                },
                "pattern": "helper",
            },
            context=_context(agent_name="planner"),
        )
    )

    assert result.ok is True
    assert result.output == {
        "matches": [
            {"path": "app.py", "node_type": "FunctionDef", "name": "helper", "line": 1},
        ]
    }


def test_diff_reader_marks_in_memory_files_as_added_when_no_baseline() -> None:
    registry = build_default_tool_registry()

    result = registry.execute(
        ToolCallRequest(
            tool_name="diff_reader",
            arguments={
                "code_files": {
                    "app.py": "print('ok')\n",
                }
            },
            context=_context(agent_name="reviewer"),
        )
    )

    assert result.ok is True
    assert result.output == {
        "changes": [
            {"path": "app.py", "change": "added"},
        ]
    }


def test_semgrep_scan_reports_simple_eval_finding() -> None:
    registry = build_default_tool_registry()

    result = registry.execute(
        ToolCallRequest(
            tool_name="semgrep_scan",
            arguments={
                "code_files": {
                    "app.py": "def run(user_input):\n    return eval(user_input)\n",
                }
            },
            context=_context(agent_name="reviewer"),
        )
    )

    assert result.ok is True
    assert result.output == {
        "findings": [
            {"path": "app.py", "rule": "python.eval", "message": "Avoid eval().", "line": 2},
        ]
    }


def test_difftastic_diff_reports_basic_line_counts() -> None:
    registry = build_default_tool_registry()

    result = registry.execute(
        ToolCallRequest(
            tool_name="difftastic_diff",
            arguments={
                "code_files": {
                    "app.py": "print('ok')\n",
                }
            },
            context=_context(agent_name="reviewer"),
        )
    )

    assert result.ok is True
    assert result.output == {
        "files": [
            {"path": "app.py", "change": "added", "before_lines": 0, "after_lines": 1},
        ]
    }
