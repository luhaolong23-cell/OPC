from __future__ import annotations

import json

from agents.base import BaseAgent


class PMAgent(BaseAgent):
    def run(self, requirement: str, conversation: list[dict] | None = None) -> dict[str, object]:
        if self.llm_client is not None:
            return self.llm_client.generate_json(
                instructions=self.build_instructions(
                    "pm.discovery",
                    "Analyze the requirement and return JSON with summary, open_questions, and constraints.",
                ),
                input_text=json.dumps(
                    {"requirement": requirement, "conversation": conversation or []},
                    ensure_ascii=False,
                ),
            )
        return {
            "summary": requirement,
            "open_questions": [],
            "constraints": [],
        }
