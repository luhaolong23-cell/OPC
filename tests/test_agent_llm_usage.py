from __future__ import annotations

import json
from dataclasses import dataclass

from agents.coder import CoderAgent
from agents.debugger import DebuggerAgent
from agents.factory import build_agent
from agents.planner import PlannerAgent
from agents.pm import PMAgent
from agents.reviewer import ReviewerAgent
from tools.defaults import ToolHandle
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


def test_pm_agent_uses_llm_client_when_configured() -> None:
    llm = FakeLLMClient(payload={"summary": "spec summary", "candidate_solutions": ["cli", "web"], "open_questions": ["q1"], "assumptions": ["a1"], "risks": ["r1"], "constraints": ["c1"], "recommended_direction": "cli"})
    agent = PMAgent(
        model="gpt-pm",
        llm_client=llm,
        role_instructions="# PM Role\n\n## 核心职责\n- 澄清需求",
    )

    result = agent.run("build todo api")

    assert result == {"summary": "spec summary", "candidate_solutions": ["cli", "web"], "open_questions": ["q1"], "assumptions": ["a1"], "risks": ["r1"], "constraints": ["c1"], "recommended_direction": "cli", "next_action": "ask_question"}
    assert llm.input_text is not None and "build todo api" in llm.input_text
    assert "# PM Role" in llm.instructions
    assert "Explore multiple implementation directions" in llm.instructions


def test_pm_agent_requirement_turn_returns_state_fields_without_action() -> None:
    llm = FakeLLMClient(
        payload={
            "recommendation": "默认先做 Python CLI 版，最小可运行。",
            "reply": None,
            "requirement_update": None,
            "ready_to_advance": False,
        }
    )
    agent = PMAgent(model="gpt-pm", llm_client=llm)

    result = agent.decide_requirement_turn(
        requirement_spec={
            "recommended_direction": {"choice": "Python CLI", "justification": "最小可运行"},
            "candidate_solutions": ["Python CLI", "Pygame"],
        },
        current_question="用户希望游戏具备哪些具体功能和特性？",
        user_reply="你来建议",
    )

    assert result == {
        "recommendation": "默认先做 Python CLI 版，最小可运行。",
        "reply": None,
        "requirement_update": None,
        "ready_to_advance": False,
    }
    assert "action" not in result


def test_planner_agent_plan_turn_returns_state_fields_without_action() -> None:
    llm = FakeLLMClient(
        payload={
            "recommendation": "建议先按最小计划推进。",
            "reply": None,
            "plan_update": None,
            "ready_to_advance": False,
        }
    )
    agent = PlannerAgent(model="gpt-planner", llm_client=llm)

    result = agent.decide_plan_turn(plan={"summary": "plan summary", "tasks": ["t1"]}, user_reply="你来建议")

    assert result == {
        "recommendation": "建议先按最小计划推进。",
        "reply": None,
        "plan_update": None,
        "ready_to_advance": False,
    }
    assert llm.instructions is not None
    assert "writing-plans skill" in llm.instructions
    assert "action" not in result


def test_planner_agent_uses_llm_client_when_configured() -> None:
    llm = FakeLLMClient(payload={"summary": "plan summary", "tasks": ["t1"], "milestones": ["m1"], "dependencies": ["d1"], "risks": ["r1"], "out_of_scope": ["o1"], "open_questions": ["q1"]})
    agent = PlannerAgent(model="gpt-planner", llm_client=llm)

    result = agent.run({"summary": "spec summary"})

    assert result == {"summary": "plan summary", "tasks": ["t1"], "milestones": ["m1"], "dependencies": ["d1"], "risks": ["r1"], "out_of_scope": ["o1"], "open_questions": ["q1"]}


def test_coder_agent_uses_llm_client_when_configured() -> None:
    llm = FakeLLMClient(payload={"modified_files": {"app.py": "print('ok')\n"}, "summary": "implemented"})
    agent = CoderAgent(model="gpt-coder", llm_client=llm)

    result = agent.run({"summary": "plan summary"}, current_files={"old.py": "pass\n"}, task_description="implement feature")

    assert result == {"modified_files": {"app.py": "print('ok')\n"}, "summary": "implemented"}


def test_debugger_agent_uses_llm_client_when_configured() -> None:
    llm = FakeLLMClient(payload={"patches": {"app.py": "print('fixed')\n"}, "diagnosis": "fixed bug"})
    agent = DebuggerAgent(model="gpt-debugger", llm_client=llm)

    result = agent.run({"app.py": "print('broken')\n"}, {"summary": "traceback"}, error_log="boom")

    assert result == {"patches": {"app.py": "print('fixed')\n"}, "diagnosis": "fixed bug"}


def test_reviewer_agent_uses_llm_client_when_configured() -> None:
    llm = FakeLLMClient(payload={"approved": False, "issues": ["missing test"], "risk_level": "medium", "summary": "needs changes"})
    agent = ReviewerAgent(model="gpt-reviewer", llm_client=llm)

    result = agent.run({"summary": "plan summary"}, {"app.py": "print('ok')\n"}, {"summary": "tests passed"})

    assert result == {"approved": False, "issues": ["missing test"], "risk_level": "medium", "summary": "needs changes"}


def test_build_agent_includes_bound_tools_in_llm_input() -> None:
    llm = FakeLLMClient(payload={"modified_files": {}, "summary": "implemented"})
    registry = ToolRegistry(
        {
            "repo_reader": ToolHandle("repo_reader", "Read repository files.", capability_tags=("repo.read",)),
            "patch_applier": ToolHandle("patch_applier", "Apply patches.", capability_tags=("code.patch",), side_effect_level="write"),
            "test_runner": ToolHandle("test_runner", "Run tests.", capability_tags=("test.run",), side_effect_level="write"),
        }
    )
    agent = build_agent("coder", model="gpt-coder", llm_client=llm, tool_registry=registry)

    agent.run({"summary": "plan summary"}, current_files={"app.py": "print('ok')\n"}, task_description="implement feature")

    assert llm.input_text is not None
    payload = json.loads(llm.input_text)
    assert payload["tools"] == [
        {"name": "repo_reader", "description": "Read repository files.", "capability_tags": ["repo.read"], "side_effect_level": "read"},
        {"name": "patch_applier", "description": "Apply patches.", "capability_tags": ["code.patch"], "side_effect_level": "write"},
        {"name": "test_runner", "description": "Run tests.", "capability_tags": ["test.run"], "side_effect_level": "write"},
    ]


def test_pm_agent_requirement_turn_rejects_meta_plan_question_as_requirement_update() -> None:
    llm = FakeLLMClient(
        payload={
            "recommendation": None,
            "reply": None,
            "requirement_update": "计划呢",
            "ready_to_advance": False,
        }
    )
    agent = PMAgent(model="gpt-pm", llm_client=llm)

    result = agent.decide_requirement_turn(
        requirement_spec={
            "recommended_direction": {"choice": "Python CLI", "justification": "最小可运行"},
        },
        current_question="用户希望游戏在哪个平台上运行？",
        user_reply="计划呢",
    )

    assert result["reply"] is not None
    assert "还没到规划阶段" in str(result["reply"])
    assert "用户希望游戏在哪个平台上运行" in str(result["reply"])
    assert result["requirement_update"] is None
    assert result["recommendation"] is None
    assert result["ready_to_advance"] is False
    assert "action" not in result


def test_pm_agent_requirement_turn_replaces_weak_target_user_recommendation() -> None:
    llm = FakeLLMClient(
        payload={
            "recommendation": "建议先明确目标用户。",
            "reply": None,
            "requirement_update": None,
            "ready_to_advance": False,
        }
    )
    agent = PMAgent(model="gpt-pm", llm_client=llm)

    result = agent.decide_requirement_turn(
        requirement_spec={
            "recommended_direction": {"choice": "Python CLI", "justification": "最小可运行"},
            "candidate_solutions": ["Python CLI"],
        },
        current_question="目标用户是谁？",
        user_reply="你来建议",
    )

    assert result["recommendation"] is not None
    assert "普通单人玩家" in str(result["recommendation"])
    assert "先明确目标用户" not in str(result["recommendation"])
    assert result["requirement_update"] is None
    assert result["ready_to_advance"] is False
    assert "action" not in result


def test_pm_agent_requirement_turn_replaces_procedural_recommendation_with_concrete_default() -> None:
    llm = FakeLLMClient(
        payload={
            "recommendation": "建议先调研用户需求，再明确目标和功能。",
            "reply": None,
            "requirement_update": None,
            "ready_to_advance": False,
        }
    )
    agent = PMAgent(model="gpt-pm", llm_client=llm)

    result = agent.decide_requirement_turn(
        requirement_spec={
            "recommended_direction": {"choice": "Python CLI", "justification": "最小可运行"},
            "candidate_solutions": ["Python CLI"],
        },
        current_question="该项目的具体目标和预期功能是什么？",
        user_reply="你来建议",
    )

    assert result["recommendation"] is not None
    assert "最小可交付版本" in str(result["recommendation"])
    assert "调研用户需求" not in str(result["recommendation"])
    assert result["requirement_update"] is None
    assert result["ready_to_advance"] is False
    assert "action" not in result


def test_pm_agent_requirement_turn_replaces_followup_question_list_with_default_scope() -> None:
    llm = FakeLLMClient(
        payload={
            "recommendation": "为了更好地建议项目的具体目标和功能，我们需要明确以下几点：1. 主要目的是什么？2. 预期用户群体是谁？请提供更多信息。",
            "reply": None,
            "requirement_update": None,
            "ready_to_advance": False,
        }
    )
    agent = PMAgent(model="gpt-pm", llm_client=llm)

    result = agent.decide_requirement_turn(
        requirement_spec={},
        current_question="该项目的具体目标和功能是什么？",
        user_reply="你来建议",
    )

    assert result["recommendation"] is not None
    assert "最小可交付版本" in str(result["recommendation"])
    assert "请提供更多信息" not in str(result["recommendation"])
    assert result["requirement_update"] is None
    assert result["ready_to_advance"] is False
    assert "action" not in result
