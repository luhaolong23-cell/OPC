from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.runtime.policy_engine import PolicyEngine
from mcp.mapping import LogicalToolMappingRegistry
from tools.providers.local.test_runner_adapter import SandboxTestRunnerAdapter
from tools.providers.mcp.client import build_mcp_server_handle
from tools.providers.mcp.provider_registry import MCPProviderRegistry
from tools.providers.registry import ProviderRegistry
from tools.registry import ToolRegistry


_DEFAULT_CONFIG_ROOT = Path(__file__).resolve().parents[1] / "config"
_DEFAULT_LOGICAL_TOOL_MAPPINGS_PATH = _DEFAULT_CONFIG_ROOT / "mappings" / "logical_tools.yaml"
_DEFAULT_MCP_SERVERS_PATH = _DEFAULT_CONFIG_ROOT / "mcp_servers" / "default.yaml"
_DEFAULT_POLICY_PATH = _DEFAULT_CONFIG_ROOT / "policies" / "default.yaml"


@dataclass(frozen=True)
class ToolHandle:
    name: str
    description: str
    backend: Any | None = None
    capability_tags: tuple[str, ...] = ()
    side_effect_level: str = "read"
    provider: str = "local"


def _as_path(value: str | Path) -> Path:
    return value if isinstance(value, Path) else Path(value)


def _build_default_provider_registry(
    policy_engine: PolicyEngine | None,
    *,
    mcp_handle_factory=None,
) -> ProviderRegistry:
    mappings = None
    mappings_path = _as_path(_DEFAULT_LOGICAL_TOOL_MAPPINGS_PATH)
    if mappings_path.exists():
        mappings = LogicalToolMappingRegistry.from_file(mappings_path)
    mcp_registry = MCPProviderRegistry()
    servers_path = _as_path(_DEFAULT_MCP_SERVERS_PATH)
    if servers_path.exists():
        mcp_registry = MCPProviderRegistry.from_file(
            servers_path,
            handle_factory=mcp_handle_factory or build_mcp_server_handle,
        )
    return ProviderRegistry(
        mcp_registry=mcp_registry,
        mappings=mappings,
        policy_engine=policy_engine,
    )


def build_default_tool_registry(
    *,
    sandbox: object | None = None,
    mcp_handle_factory=None,
) -> ToolRegistry:
    test_runner_backend = SandboxTestRunnerAdapter(sandbox) if sandbox is not None else None
    policy_path = _as_path(_DEFAULT_POLICY_PATH)
    policy_engine = PolicyEngine.from_file(policy_path) if policy_path.exists() else None
    provider_registry = _build_default_provider_registry(
        policy_engine,
        mcp_handle_factory=mcp_handle_factory,
    )
    return ToolRegistry(
        {
            "repo_reader": ToolHandle("repo_reader", "Read repository files and code context.", capability_tags=("repo.read",)),
            "structure_summary": ToolHandle("structure_summary", "Summarize repository structure and module boundaries.", capability_tags=("repo.structure",)),
            "file_writer": ToolHandle("file_writer", "Write or replace project files.", capability_tags=("workspace.write",), side_effect_level="write"),
            "patch_applier": ToolHandle("patch_applier", "Apply targeted code patches.", capability_tags=("code.patch",), side_effect_level="write"),
            "diff_summarizer": ToolHandle("diff_summarizer", "Summarize file-level code changes.", capability_tags=("diff.read",)),
            "log_reader": ToolHandle("log_reader", "Read failure logs and execution traces.", capability_tags=("log.read",)),
            "diff_reader": ToolHandle("diff_reader", "Inspect the candidate code diff.", capability_tags=("diff.read",)),
            "test_report_reader": ToolHandle("test_report_reader", "Inspect structured test results.", capability_tags=("test.read",)),
            "static_analyzer": ToolHandle("static_analyzer", "Inspect static analysis findings.", capability_tags=("code.analyze",)),
            "rg_search": ToolHandle("rg_search", "Search repository text like BurntSushi/ripgrep.", capability_tags=("repo.search",)),
            "ast_grep_search": ToolHandle("ast_grep_search", "Perform structural code search like ast-grep/ast-grep.", capability_tags=("code.search",)),
            "py_tree_sitter_parse": ToolHandle("py_tree_sitter_parse", "Parse Python code structure like tree-sitter/py-tree-sitter.", capability_tags=("code.parse",)),
            "ruff_check": ToolHandle("ruff_check", "Run Python lint checks like astral-sh/ruff.", capability_tags=("code.analyze",)),
            "semgrep_scan": ToolHandle("semgrep_scan", "Run security-focused static analysis like semgrep/semgrep.", capability_tags=("security.scan",)),
            "difftastic_diff": ToolHandle("difftastic_diff", "Inspect syntax-aware diffs like Wilfred/difftastic.", capability_tags=("diff.syntax",)),
            "test_runner": ToolHandle("test_runner", "Execute project tests in the sandbox.", backend=test_runner_backend, capability_tags=("test.run",), side_effect_level="write"),
        },
        provider_registry=provider_registry,
        policy_engine=policy_engine,
    )
