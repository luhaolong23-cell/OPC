from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver

from graph.builder import build_development_graph
from workspace.state import TaskStatus


class FakePMAgent:
    def run(self, requirement: str, conversation: list[dict] | None = None) -> dict:
        return {
            "summary": f"spec for {requirement}",
            "open_questions": [],
            "constraints": [],
        }


class FakePlannerAgent:
    def run(self, requirement_spec: dict) -> dict:
        return {
            "summary": f"plan for {requirement_spec['summary']}",
            "tasks": ["create app", "add tests"],
            "risks": [],
        }


def test_graph_stops_at_requirement_approval_without_feedback() -> None:
    graph = build_development_graph(
        pm_agent=FakePMAgent(),
        planner_agent=FakePlannerAgent(),
    )

    result = graph.invoke({"requirement": "Build a todo api."})

    assert result["current_task"] is TaskStatus.WAIT_HUMAN_REQUIREMENT
    assert result["requirement_spec"]["summary"] == "spec for Build a todo api."
    assert result["plan"] is None


def test_graph_reaches_plan_wait_after_requirement_approval() -> None:
    graph = build_development_graph(
        pm_agent=FakePMAgent(),
        planner_agent=FakePlannerAgent(),
    )

    result = graph.invoke(
        {
            "requirement": "Build a todo api.",
            "human_feedback": {
                "target": "requirement_review",
                "action": "approve",
                "comments": "",
            },
        }
    )

    assert result["current_task"] is TaskStatus.WAIT_HUMAN_PLAN
    assert result["plan"]["summary"] == "plan for spec for Build a todo api."


def test_graph_persists_latest_state_in_memory_checkpointer() -> None:
    graph = build_development_graph(
        pm_agent=FakePMAgent(),
        planner_agent=FakePlannerAgent(),
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "thread-1"}}

    graph.invoke({"requirement": "Build a todo api."}, config=config)
    snapshot = graph.get_state(config)

    assert snapshot.values["current_task"] is TaskStatus.WAIT_HUMAN_REQUIREMENT
    assert snapshot.values["requirement_spec"]["summary"] == "spec for Build a todo api."
