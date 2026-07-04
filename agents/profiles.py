from __future__ import annotations

from agents.capabilities import AgentProfile


_PROFILES = {
    "pm": AgentProfile(
        name="pm",
        role_name="pm",
        default_skill="pm.discovery",
        allowed_skills=("pm.discovery", "pm.brainstorm", "pm.specify"),
        allowed_tools=("repo_reader", "rg_search", "py_tree_sitter_parse"),
        allowed_tool_tags=("repo.read", "repo.search", "code.parse", "docs.search"),
    ),
    "planner": AgentProfile(
        name="planner",
        role_name="planner",
        default_skill="planner.plan",
        allowed_skills=("planner.plan", "planner.write_tasks", "planner.verify_scope"),
        allowed_tools=("repo_reader", "structure_summary", "ast_grep_search"),
        allowed_tool_tags=("repo.read", "repo.structure", "code.search"),
    ),
    "coder": AgentProfile(
        name="coder",
        role_name="coder",
        default_skill="coder.implement",
        allowed_skills=("coder.implement", "coder.tdd", "coder.spec_driven"),
        allowed_tools=("repo_reader", "patch_applier", "test_runner"),
        allowed_tool_tags=("repo.read", "code.patch", "test.run"),
    ),
    "debugger": AgentProfile(
        name="debugger",
        role_name="debugger",
        default_skill="debugger.fix",
        allowed_skills=("debugger.fix", "debugger.systematic", "debugger.verify_loop"),
        allowed_tools=("log_reader", "patch_applier", "test_runner"),
        allowed_tool_tags=("log.read", "code.patch", "test.run"),
    ),
    "reviewer": AgentProfile(
        name="reviewer",
        role_name="reviewer",
        default_skill="reviewer.audit",
        allowed_skills=("reviewer.audit", "reviewer.code_review", "reviewer.security_review"),
        allowed_tools=("diff_reader", "semgrep_scan", "difftastic_diff"),
        allowed_tool_tags=("diff.read", "security.scan", "diff.syntax"),
    ),
}


def get_agent_profile(name: str) -> AgentProfile:
    return _PROFILES[name]
