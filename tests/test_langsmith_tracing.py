from __future__ import annotations

from contextlib import contextmanager

from agents.pm import PMAgent
from graph.runtime import WorkflowService
from llm.client import OpenAIJSONClient
from workspace.manager import WorkspaceManager
from workspace.state import TaskStatus


class FakeLLMClient:
    def generate_json(self, *, instructions: str, input_text: str) -> dict:
        return {"summary": "ok", "open_questions": [], "constraints": []}


class FakeAgent:
    def run(self, *args, **kwargs):
        return {"summary": "ok", "tasks": [], "risks": []}


class FakeSandbox:
    def run_tests(self, code_files: dict[str, str]) -> dict[str, object]:
        return {
            "status": "passed",
            "failure_type": None,
            "summary": "ok",
            "raw_logs": "",
        }


class FakeResponsesAPI:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, *, model: str, instructions: str, input: str):
        self.calls.append({"model": model, "instructions": instructions, "input": input})
        return type("Response", (), {"output_text": '{"summary":"ok"}'})()


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.responses = FakeResponsesAPI()


class RecordingTrace:
    def __init__(self, sink: list[dict[str, object]], payload: dict[str, object]) -> None:
        self._sink = sink
        self._payload = payload
        self.outputs = None

    def end(self, *, outputs=None) -> None:
        self.outputs = outputs
        self._payload["outputs"] = outputs


@contextmanager
def _recording_trace_factory(sink: list[dict[str, object]], **kwargs):
    payload = dict(kwargs)
    sink.append(payload)
    yield RecordingTrace(sink, payload)


def test_openai_json_client_wraps_client_for_tracing(monkeypatch) -> None:
    fake_client = FakeOpenAIClient()
    wrapped_client = object()
    seen: list[object] = []

    def fake_wrap(client):
        seen.append(client)
        return wrapped_client

    monkeypatch.setattr("llm.client.wrap_openai_client", fake_wrap)

    client = OpenAIJSONClient(model="gpt-5", client=fake_client)

    assert seen == [fake_client]
    assert client.client is wrapped_client


def test_pm_agent_runs_inside_trace_span(monkeypatch) -> None:
    traces: list[dict[str, object]] = []

    monkeypatch.setattr(
        "agents.pm.trace_span",
        lambda **kwargs: _recording_trace_factory(traces, **kwargs),
    )

    agent = PMAgent(model="gpt-pm", llm_client=FakeLLMClient())

    result = agent.run("build todo api", conversation=[{"role": "user", "content": "hello"}])

    assert result["summary"] == "ok"
    assert traces[0]["name"] == "agent.pm.run"
    assert traces[0]["metadata"] == {"agent_role": "pm", "model": "gpt-pm"}
    assert traces[0]["outputs"] == result


def test_workflow_service_start_project_runs_inside_parent_trace(monkeypatch, tmp_path) -> None:
    traces: list[dict[str, object]] = []
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / "projects",
    )
    manager.initialize()
    service = WorkflowService(
        manager=manager,
        pm_agent=FakeAgent(),
        planner_agent=FakeAgent(),
        coder_agent=FakeAgent(),
        debugger_agent=FakeAgent(),
        reviewer_agent=FakeAgent(),
        sandbox=FakeSandbox(),
    )

    monkeypatch.setattr(
        "graph.runtime.trace_span",
        lambda **kwargs: _recording_trace_factory(traces, **kwargs),
    )

    project = manager.create_project(title="Todo API", requirement="build todo api")
    checkpoint = manager.create_checkpoint(
        project_id=project.id,
        checkpoint_type="requirement_review",
        available_actions=["approve"],
    )

    def fake_run_discovery(self, *args, **kwargs):
        return project, checkpoint, {"current_task": TaskStatus.WAIT_HUMAN_REQUIREMENT}

    monkeypatch.setattr(WorkflowService, "_run_discovery", fake_run_discovery)

    resolved_project, resolved_checkpoint = service.start_project(project.id)

    assert resolved_project.id == project.id
    assert resolved_checkpoint.id == checkpoint.id
    assert traces[0]["name"] == "workflow.start_project"
    assert traces[0]["metadata"]["project_id"] == project.id
    assert traces[0]["outputs"]["checkpoint_type"] == "requirement_review"


def test_workflow_service_traces_checkpoint_creation(monkeypatch, tmp_path) -> None:
    traces: list[dict[str, object]] = []
    manager = WorkspaceManager(
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / "projects",
    )
    manager.initialize()
    project = manager.create_project(title="Todo API", requirement="build todo api")
    service = WorkflowService(
        manager=manager,
        pm_agent=FakeAgent(),
        planner_agent=FakeAgent(),
        coder_agent=FakeAgent(),
        debugger_agent=FakeAgent(),
        reviewer_agent=FakeAgent(),
        sandbox=FakeSandbox(),
    )

    monkeypatch.setattr(
        "graph.runtime.trace_span",
        lambda **kwargs: _recording_trace_factory(traces, **kwargs),
    )

    checkpoint = service._create_checkpoint_for_task(project.id, TaskStatus.WAIT_HUMAN_PLAN)

    assert checkpoint is not None
    assert checkpoint.type == "plan_review"
    assert traces[0]["name"] == "workflow.create_checkpoint"
    assert traces[0]["outputs"] == {"checkpoint_type": "plan_review"}
