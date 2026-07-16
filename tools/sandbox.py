from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


class DockerSandbox:
    def run_tests(self, code_files: dict[str, str]) -> dict[str, object]:
        with TemporaryDirectory() as tmp_dir:
            root_dir = Path(tmp_dir)
            for relative_path, content in code_files.items():
                path = root_dir / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)

            env = dict(os.environ)
            env.setdefault('PYTEST_DISABLE_PLUGIN_AUTOLOAD', '1')
            completed = subprocess.run(
                [sys.executable, '-m', 'pytest', '-q'],
                cwd=root_dir,
                capture_output=True,
                text=True,
                env=env,
            )
            raw_logs = (completed.stdout or '') + (completed.stderr or '')
            if completed.returncode == 0:
                return {
                    'status': 'passed',
                    'failure_type': None,
                    'summary': 'pytest passed',
                    'raw_logs': raw_logs,
                }
            failure_type = 'assertion_failure'
            if 'ERROR' in raw_logs and 'FAILED' not in raw_logs:
                failure_type = 'runtime_error'
            return {
                'status': 'failed',
                'failure_type': failure_type,
                'summary': 'pytest failed',
                'raw_logs': raw_logs,
            }
