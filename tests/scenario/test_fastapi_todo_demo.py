from __future__ import annotations

import json
from pathlib import Path

from tests.factories.app import build_main_test_client
from tests.factories.workflow import build_feedback_payload, create_project_and_run
from tests.fakes.workflow import FakeCoderAgent, FakeDebuggerAgent, FakePMAgent, FakePlannerAgent, FakeReviewerAgent, FakeSandbox
from tests.fixtures.demo_requirements import FASTAPI_TODO_REQUIREMENT


REPLAYS_DIR = Path(__file__).parent / "replays"


def test_fastapi_todo_demo_reaches_done(tmp_path) -> None:
    replay = json.loads((REPLAYS_DIR / "fastapi_todo_happy_path.json").read_text())
    client, _manager = build_main_test_client(
        tmp_path,
        pm_agent=FakePMAgent(),
        planner_agent=FakePlannerAgent(),
        coder_agent=FakeCoderAgent(modified_files=replay["coder_agent"]["modified_files"]),
        debugger_agent=FakeDebuggerAgent(patches=replay["coder_agent"]["modified_files"], diagnosis="not needed"),
        reviewer_agent=FakeReviewerAgent(),
        sandbox=FakeSandbox(results=replay["sandbox_results"]),
    )

    project_id, payload = create_project_and_run(
        client,
        title=replay["title"],
        requirement=FASTAPI_TODO_REQUIREMENT,
    )

    for action in replay["feedback_actions"]:
        response = client.post(
            f"/projects/{project_id}/feedback",
            json=build_feedback_payload(payload, action=action),
        )
        payload = response.json()

    assert payload["project"]["status"] == "done"
    assert payload["checkpoint"] is None
