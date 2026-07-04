from __future__ import annotations

from dataclasses import dataclass, field


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


class FakeCoderAgent:
    def __init__(self, modified_files: dict | None = None, summary: str = "implemented") -> None:
        self.modified_files = modified_files or {
            "app.py": "def main():\n    return 'ok'\n",
            "test_app.py": "from app import main\n\ndef test_main():\n    assert main() == 'ok'\n",
        }
        self.summary = summary

    def run(self, plan: dict, current_files: dict | None = None, task_description: str = "") -> dict:
        return {
            "modified_files": self.modified_files,
            "summary": f"{self.summary} {plan['summary']}".strip(),
        }


class NestedContentCoderAgent(FakeCoderAgent):
    def __init__(self) -> None:
        super().__init__(
            modified_files={
                "app.py": {"content": "def main():\n    return 'ok'\n"},
                "test_app.py": {"content": "from app import main\n\ndef test_main():\n    assert main() == 'ok'\n"},
            }
        )


class FakeDebuggerAgent:
    def __init__(self, patches: dict | None = None, diagnosis: str = "fixed failing assertion") -> None:
        self.patches = patches or {
            "app.py": "def main():\n    return 'fixed'\n",
            "test_app.py": "from app import main\n\ndef test_main():\n    assert main() == 'fixed'\n",
        }
        self.diagnosis = diagnosis

    def run(self, code_files: dict, test_results: dict, error_log: str | None = None) -> dict:
        return {
            "patches": self.patches,
            "diagnosis": self.diagnosis,
        }


class FakeReviewerAgent:
    def __init__(
        self,
        *,
        approved: bool = True,
        issues: list[str] | None = None,
        risk_level: str = "low",
        summary: str = "review passed",
    ) -> None:
        self.approved = approved
        self.issues = issues or []
        self.risk_level = risk_level
        self.summary = summary

    def run(self, plan: dict, code_files: dict, test_results: dict) -> dict:
        return {
            "approved": self.approved,
            "issues": self.issues,
            "risk_level": self.risk_level,
            "summary": self.summary,
        }


@dataclass
class FakeSandbox:
    results: list[dict]

    def run_tests(self, code_files: dict) -> dict:
        return self.results.pop(0)


@dataclass
class FakeNotifier:
    sent_messages: list[tuple[str, str]] = field(default_factory=list)

    async def send_text(self, wecom_user_id: str, content: str) -> None:
        self.sent_messages.append((wecom_user_id, content))


class FakeBridgeClient:
    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None
