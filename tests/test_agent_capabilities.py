from __future__ import annotations

from dataclasses import dataclass

from agents.factory import build_agent
from agents.pm import PMAgent
from agents.profiles import get_agent_profile
from agents.reviewer import ReviewerAgent
from agents.skills import get_skill
from tools.defaults import build_default_tool_registry
from tools.registry import ToolRegistry


@dataclass
class FakeLLMClient:
    payload: dict
    instructions: str | None = None
    input_text: str | None = None

    def generate_json(self, *, instructions: str, input_text: str) -> dict:
        self.instructions = instructions
        self.input_text = input_text
        return self.payload


def test_tool_registry_binds_only_allowed_tools() -> None:
    registry = ToolRegistry(
        {
            "repo_reader": object(),
            "file_writer": object(),
            "patch_applier": object(),
        }
    )

    bound = registry.bind(("repo_reader", "patch_applier"))

    assert set(bound.tools) == {"repo_reader", "patch_applier"}


def test_pm_agent_uses_skill_catalog_instructions() -> None:
    llm = FakeLLMClient(payload={"summary": "spec", "open_questions": [], "constraints": []})
    skill = get_skill("pm.brainstorm")
    agent = PMAgent(model="gpt-pm", llm_client=llm, skills={skill.name: skill})

    result = agent.run("build todo api")

    assert result == {
        "summary": "spec",
        "candidate_solutions": [],
        "open_questions": [],
        "assumptions": [],
        "risks": [],
        "constraints": [],
        "recommended_direction": None,
        "next_action": "close_brainstorm",
    }
    assert llm.instructions == skill.instructions


def test_build_agent_binds_profile_skills_and_tools() -> None:
    llm = FakeLLMClient(payload={"summary": "implemented", "modified_files": {}})
    registry = ToolRegistry(
        {
            "repo_reader": object(),
            "patch_applier": object(),
            "test_runner": object(),
        }
    )

    agent = build_agent("coder", model="gpt-coder", llm_client=llm, tool_registry=registry)
    profile = get_agent_profile("coder")

    assert agent.profile == profile
    assert set(agent.skills) == set(profile.allowed_skills)
    assert set(agent.tools.tools) == set(profile.allowed_tools)
    assert "核心职责" in agent.role_instructions


def test_agent_profiles_use_curated_two_or_three_skills_and_tools() -> None:
    expected = {
        "pm": {
            "skills": {"pm.discovery", "pm.brainstorm", "pm.specify"},
            "tools": {"repo_reader", "rg_search", "py_tree_sitter_parse"},
        },
        "planner": {
            "skills": {"planner.plan", "planner.write_tasks", "planner.verify_scope"},
            "tools": {"repo_reader", "structure_summary", "ast_grep_search"},
        },
        "coder": {
            "skills": {"coder.implement", "coder.tdd", "coder.spec_driven"},
            "tools": {"repo_reader", "patch_applier", "test_runner"},
        },
        "debugger": {
            "skills": {"debugger.fix", "debugger.systematic", "debugger.verify_loop"},
            "tools": {"log_reader", "patch_applier", "test_runner"},
        },
        "reviewer": {
            "skills": {"reviewer.audit", "reviewer.code_review", "reviewer.security_review"},
            "tools": {"diff_reader", "semgrep_scan", "difftastic_diff"},
        },
    }

    for agent_name, capability_set in expected.items():
        profile = get_agent_profile(agent_name)

        assert profile.role_name == agent_name
        assert set(profile.allowed_skills) == capability_set["skills"]
        assert 2 <= len(profile.allowed_skills) <= 3
        assert set(profile.allowed_tools) == capability_set["tools"]
        assert 2 <= len(profile.allowed_tools) <= 3


def test_default_tool_registry_includes_curated_external_tool_wrappers() -> None:
    registry = build_default_tool_registry()
    bound = registry.bind(
        (
            "rg_search",
            "ast_grep_search",
            "py_tree_sitter_parse",
            "ruff_check",
            "test_runner",
            "semgrep_scan",
            "difftastic_diff",
        )
    )

    assert set(bound.tools) == {
        "rg_search",
        "ast_grep_search",
        "py_tree_sitter_parse",
        "ruff_check",
        "test_runner",
        "semgrep_scan",
        "difftastic_diff",
    }


def test_curated_agents_expose_requested_default_skills() -> None:
    assert get_agent_profile("pm").default_skill == "pm.brainstorm"
    assert get_agent_profile("planner").default_skill == "planner.write_tasks"
    assert get_agent_profile("reviewer").default_skill == "reviewer.code_review"


def test_reviewer_agent_uses_code_review_skill_catalog_instructions() -> None:
    llm = FakeLLMClient(payload={"approved": True, "issues": [], "risk_level": "low", "summary": "ok"})
    skill = get_skill("reviewer.code_review")
    agent = ReviewerAgent(model="gpt-reviewer", llm_client=llm, skills={skill.name: skill})

    result = agent.run(
        plan={"summary": "Build todo api"},
        code_files={"app.py": "print('ok')\n"},
        test_results={"status": "passed", "failure_type": None, "summary": "ok", "raw_logs": ""},
    )

    assert result == {"approved": True, "issues": [], "risk_level": "low", "summary": "ok"}
    assert llm.instructions == skill.instructions
