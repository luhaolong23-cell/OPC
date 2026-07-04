from __future__ import annotations

import json

from agents.base import BaseAgent


class CoderAgent(BaseAgent):
    def run(self, plan: dict[str, object], current_files: dict[str, str] | None = None, task_description: str = "") -> dict[str, object]:
        if self.llm_client is not None:
            return self.llm_client.generate_json(
                instructions=self.build_instructions(
                    "coder.implement",
                    "Implement the task and return JSON with modified_files and summary.",
                ),
                input_text=json.dumps(
                    {
                        "plan": plan,
                        "current_files": current_files or {},
                        "task_description": task_description,
                    },
                    ensure_ascii=False,
                ),
            )
        return {
            "modified_files": current_files or {},
            "summary": f"implemented {plan['summary']}",
        }
