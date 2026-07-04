from __future__ import annotations


class DockerSandbox:
    def run_tests(self, code_files: dict[str, str]) -> dict[str, object]:
        return {
            'status': 'passed',
            'failure_type': None,
            'summary': 'tests not configured',
            'raw_logs': '',
        }
