from __future__ import annotations

import json

from agents.base import BaseAgent


class ReviewerAgent(BaseAgent):
    def run(self, plan: dict[str, object], code_files: dict[str, str], test_results: dict[str, object]) -> dict[str, object]:
        if self.llm_client is not None:
            return self.llm_client.generate_json(
                instructions=self.build_instructions(
                    "reviewer.audit",
                    "Review the change and return JSON with approved, issues, risk_level, and summary.",
                ),
                input_text=json.dumps(
                    {
                        "plan": plan,
                        "code_files": code_files,
                        "test_results": test_results,
                    },
                    ensure_ascii=False,
                ),
            )
        return {
            "approved": True,
            "issues": [],
            "risk_level": "low",
            "summary": f"reviewed {plan['summary']}",
        }
