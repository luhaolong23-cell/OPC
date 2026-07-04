from __future__ import annotations

from agents.factory import build_agent
from tools.defaults import ToolHandle
from tools.registry import ToolRegistry


class FakeLLMClient:
    def generate_json(self, *, instructions: str, input_text: str) -> dict:
        return {"summary": "implemented", "modified_files": {}}


def test_build_agent_binds_profile_tool_tags_into_runtime_tool_resolution() -> None:
    registry = ToolRegistry(
        {
            "repo_reader": ToolHandle(
                "repo_reader",
                "Read repository files.",
                capability_tags=("repo.read",),
            ),
            "patch_applier": ToolHandle(
                "patch_applier",
                "Apply patches.",
                capability_tags=("code.patch",),
            ),
            "test_runner": ToolHandle(
                "test_runner",
                "Run tests.",
                capability_tags=("test.run",),
            ),
        }
    )

    agent = build_agent("coder", model="gpt-coder", llm_client=FakeLLMClient(), tool_registry=registry)

    assert [tool.name for tool in agent.tools.resolve_by_tag("repo.read")] == ["repo_reader"]
