from __future__ import annotations

from dataclasses import dataclass

from agents.coder import CoderAgent
from agents.debugger import DebuggerAgent
from agents.planner import PlannerAgent
from agents.pm import PMAgent
from agents.reviewer import ReviewerAgent


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
    llm = FakeLLMClient(payload={"summary": "spec summary", "open_questions": ["q1"], "constraints": ["c1"]})
    agent = PMAgent(
        model="gpt-pm",
        llm_client=llm,
        role_instructions="# PM Role\n\n## 核心职责\n- 澄清需求",
    )

    result = agent.run("build todo api")

    assert result == {"summary": "spec summary", "open_questions": ["q1"], "constraints": ["c1"]}
    assert llm.input_text is not None and "build todo api" in llm.input_text
    assert "# PM Role" in llm.instructions
    assert "Analyze the requirement" in llm.instructions


def test_planner_agent_uses_llm_client_when_configured() -> None:
    llm = FakeLLMClient(payload={"summary": "plan summary", "tasks": ["t1"], "risks": ["r1"]})
    agent = PlannerAgent(model="gpt-planner", llm_client=llm)

    result = agent.run({"summary": "spec summary"})

    assert result == {"summary": "plan summary", "tasks": ["t1"], "risks": ["r1"]}


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
