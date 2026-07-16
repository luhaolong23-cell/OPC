from __future__ import annotations

import ast
import re
import time
from pathlib import Path

from tools.specs import ToolCallRequest, ToolCallResult


def _root_dir(arguments: dict[str, object]) -> Path:
    return Path(str(arguments.get("root_dir") or Path.cwd())).resolve()


def _safe_path(root_dir: Path, relative_path: str) -> Path:
    candidate = (root_dir / relative_path).resolve()
    try:
        candidate.relative_to(root_dir)
    except ValueError as exc:
        raise ValueError(f"path escapes root_dir: {relative_path}") from exc
    return candidate


def _normalize_file_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, str] = {}
    for raw_path, raw_content in value.items():
        content = raw_content
        if isinstance(raw_content, dict) and 'content' in raw_content:
            content = raw_content['content']
        normalized[str(raw_path)] = str(content)
    return normalized


def _load_files(arguments: dict[str, object]) -> dict[str, str]:
    code_files = _normalize_file_mapping(arguments.get('code_files') or arguments.get('current_files'))
    if code_files and 'root_dir' not in arguments:
        return dict(sorted(code_files.items()))
    root_dir = _root_dir(arguments)
    loaded: dict[str, str] = {}
    for path in sorted(root_dir.rglob('*')):
        if path.is_file():
            loaded[path.relative_to(root_dir).as_posix()] = path.read_text(errors='ignore')
    return loaded


def _ok(*, output: dict[str, object], started_at: float) -> ToolCallResult:
    return ToolCallResult(
        ok=True,
        output=output,
        error=None,
        provider='local',
        latency_ms=int((time.perf_counter() - started_at) * 1000),
    )


def _error(message: str, *, started_at: float) -> ToolCallResult:
    return ToolCallResult(
        ok=False,
        output=None,
        error=message,
        provider='local',
        latency_ms=int((time.perf_counter() - started_at) * 1000),
    )


class LocalRepoReader:
    def execute(self, request: ToolCallRequest) -> ToolCallResult:
        started_at = time.perf_counter()
        paths = [str(raw_path) for raw_path in request.arguments.get('paths', [])]
        code_files = _normalize_file_mapping(request.arguments.get('code_files') or request.arguments.get('current_files'))
        if code_files and 'root_dir' not in request.arguments:
            files = {path: code_files[path] for path in paths if path in code_files}
            missing_paths = [path for path in paths if path not in code_files]
            return _ok(output={'files': files, 'missing_paths': missing_paths}, started_at=started_at)

        root_dir = _root_dir(request.arguments)
        files: dict[str, str] = {}
        missing_paths: list[str] = []
        for relative_path in paths:
            path = _safe_path(root_dir, relative_path)
            if not path.exists() or not path.is_file():
                missing_paths.append(relative_path)
                continue
            files[relative_path] = path.read_text()
        return _ok(output={'files': files, 'missing_paths': missing_paths}, started_at=started_at)


class LocalStructureSummary:
    def execute(self, request: ToolCallRequest) -> ToolCallResult:
        started_at = time.perf_counter()
        files = _load_files(request.arguments)
        top_level_entries = sorted({path.split('/', 1)[0] for path in files})
        return _ok(
            output={
                'top_level_entries': top_level_entries,
                'files': sorted(files),
                'file_count': len(files),
            },
            started_at=started_at,
        )


class LocalPatchApplier:
    def execute(self, request: ToolCallRequest) -> ToolCallResult:
        started_at = time.perf_counter()
        payload = _normalize_file_mapping(request.arguments.get('files') or request.arguments.get('code_files'))
        current_files = _normalize_file_mapping(request.arguments.get('current_files') or request.arguments.get('code_files'))
        if 'root_dir' not in request.arguments:
            merged_files = dict(current_files)
            merged_files.update(payload)
            return _ok(output={'written_files': sorted(payload), 'files': merged_files}, started_at=started_at)

        root_dir = _root_dir(request.arguments)
        written_files: list[str] = []
        for relative_path, content in payload.items():
            path = _safe_path(root_dir, relative_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            written_files.append(relative_path)
        return _ok(output={'written_files': sorted(written_files)}, started_at=started_at)


class LocalDiffReader:
    def execute(self, request: ToolCallRequest) -> ToolCallResult:
        started_at = time.perf_counter()
        after_files = _normalize_file_mapping(request.arguments.get('code_files') or request.arguments.get('current_files'))
        if not after_files:
            after_files = _load_files(request.arguments)
        before_files = _normalize_file_mapping(request.arguments.get('baseline_files') or request.arguments.get('before_files'))
        changes: list[dict[str, object]] = []
        for path in sorted(set(before_files) | set(after_files)):
            before = before_files.get(path)
            after = after_files.get(path)
            if before is None and after is not None:
                changes.append({'path': path, 'change': 'added'})
            elif before is not None and after is None:
                changes.append({'path': path, 'change': 'removed'})
            elif before != after:
                changes.append({'path': path, 'change': 'modified'})
        return _ok(output={'changes': changes}, started_at=started_at)


class LocalLogReader:
    def execute(self, request: ToolCallRequest) -> ToolCallResult:
        started_at = time.perf_counter()
        inline_content = request.arguments.get('content') or request.arguments.get('error_log') or request.arguments.get('raw_logs')
        if inline_content is not None:
            return _ok(output={'path': None, 'content': str(inline_content)}, started_at=started_at)

        root_dir = _root_dir(request.arguments)
        relative_path = str(request.arguments.get('path') or '')
        if not relative_path:
            return _error('path is required', started_at=started_at)
        path = _safe_path(root_dir, relative_path)
        if not path.exists() or not path.is_file():
            return _error(f'log file not found: {relative_path}', started_at=started_at)
        return _ok(output={'path': relative_path, 'content': path.read_text()}, started_at=started_at)


class LocalRgSearch:
    def execute(self, request: ToolCallRequest) -> ToolCallResult:
        started_at = time.perf_counter()
        pattern = str(request.arguments.get('pattern') or '')
        if not pattern:
            return _error('pattern is required', started_at=started_at)
        regex = re.compile(pattern)
        files = _load_files(request.arguments)
        matches: list[dict[str, object]] = []
        for relative_path, content in files.items():
            for line_number, line in enumerate(content.splitlines(), start=1):
                if regex.search(line):
                    matches.append({'path': relative_path, 'line': line_number, 'text': line})
        return _ok(output={'matches': matches}, started_at=started_at)


class LocalPythonTreeSitterParse:
    def execute(self, request: ToolCallRequest) -> ToolCallResult:
        started_at = time.perf_counter()
        files = _load_files(request.arguments)
        parsed: dict[str, dict[str, object]] = {}
        for relative_path, content in files.items():
            if not relative_path.endswith('.py'):
                continue
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            imports: list[str] = []
            classes: list[str] = []
            functions: list[str] = []
            for node in tree.body:
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ''
                    if module:
                        imports.append(module)
                elif isinstance(node, ast.ClassDef):
                    classes.append(node.name)
                elif isinstance(node, ast.FunctionDef):
                    functions.append(node.name)
            parsed[relative_path] = {
                'imports': imports,
                'classes': classes,
                'functions': functions,
            }
        return _ok(output={'files': parsed}, started_at=started_at)


class LocalAstGrepSearch:
    def execute(self, request: ToolCallRequest) -> ToolCallResult:
        started_at = time.perf_counter()
        pattern = str(request.arguments.get('pattern') or '')
        if not pattern:
            return _error('pattern is required', started_at=started_at)
        files = _load_files(request.arguments)
        matches: list[dict[str, object]] = []
        for relative_path, content in files.items():
            if not relative_path.endswith('.py'):
                continue
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == pattern:
                    matches.append({'path': relative_path, 'node_type': 'FunctionDef', 'name': node.name, 'line': node.lineno})
                elif isinstance(node, ast.ClassDef) and node.name == pattern:
                    matches.append({'path': relative_path, 'node_type': 'ClassDef', 'name': node.name, 'line': node.lineno})
        return _ok(output={'matches': matches}, started_at=started_at)


class LocalSemgrepScan:
    RULES = [
        ('python.eval', 'Avoid eval().', re.compile(r'\beval\s*\(')),
        ('python.exec', 'Avoid exec().', re.compile(r'\bexec\s*\(')),
        ('python.subprocess.shell_true', 'Avoid subprocess with shell=True.', re.compile(r'subprocess\.[^(]+\([^\n]*shell\s*=\s*True')),
    ]

    def execute(self, request: ToolCallRequest) -> ToolCallResult:
        started_at = time.perf_counter()
        files = _load_files(request.arguments)
        findings: list[dict[str, object]] = []
        for relative_path, content in files.items():
            for line_number, line in enumerate(content.splitlines(), start=1):
                for rule, message, regex in self.RULES:
                    if regex.search(line):
                        findings.append({'path': relative_path, 'rule': rule, 'message': message, 'line': line_number})
        return _ok(output={'findings': findings}, started_at=started_at)


class LocalDifftasticDiff:
    def execute(self, request: ToolCallRequest) -> ToolCallResult:
        started_at = time.perf_counter()
        after_files = _normalize_file_mapping(request.arguments.get('code_files') or request.arguments.get('current_files'))
        if not after_files:
            after_files = _load_files(request.arguments)
        before_files = _normalize_file_mapping(request.arguments.get('baseline_files') or request.arguments.get('before_files'))
        files: list[dict[str, object]] = []
        for path in sorted(set(before_files) | set(after_files)):
            before = before_files.get(path)
            after = after_files.get(path)
            if before is None and after is not None:
                change = 'added'
            elif before is not None and after is None:
                change = 'removed'
            elif before != after:
                change = 'modified'
            else:
                continue
            files.append(
                {
                    'path': path,
                    'change': change,
                    'before_lines': 0 if before is None else len(before.splitlines()),
                    'after_lines': 0 if after is None else len(after.splitlines()),
                }
            )
        return _ok(output={'files': files}, started_at=started_at)
