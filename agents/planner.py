from __future__ import annotations

import json

from agents.base import BaseAgent


class PlannerAgent(BaseAgent):
    def run(self, requirement_spec: dict[str, object]) -> dict[str, object]:
        if self.llm_client is not None:
            return self.llm_client.generate_json(
                instructions=self.build_instructions(
                    "planner.plan",
                    "Turn the requirement spec into JSON with summary, tasks, and risks.",
                ),
                input_text=json.dumps(requirement_spec, ensure_ascii=False),
            )
        return {
            "summary": str(requirement_spec["summary"]),
            "tasks": [],
            "risks": [],
        }
