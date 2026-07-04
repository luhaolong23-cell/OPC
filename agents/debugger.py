from __future__ import annotations

import json

from agents.base import BaseAgent


class DebuggerAgent(BaseAgent):
    def run(self, code_files: dict[str, str], test_results: dict[str, object], error_log: str | None = None) -> dict[str, object]:
        if self.llm_client is not None:
            return self.llm_client.generate_json(
                instructions=self.build_instructions(
                    "debugger.fix",
                    "Debug the failure and return JSON with patches and diagnosis.",
                ),
                input_text=json.dumps(
                    {
                        "code_files": code_files,
                        "test_results": test_results,
                        "error_log": error_log,
                    },
                    ensure_ascii=False,
                ),
            )
        return {
            "patches": code_files,
            "diagnosis": error_log or test_results.get("summary", ""),
        }
