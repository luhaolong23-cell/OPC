from __future__ import annotations

from collections.abc import Callable

from workspace.state import DevelopmentState, TaskStatus


def build_discovery_node(pm_run: Callable[[str, list[dict] | None], dict[str, object]]) -> Callable[[DevelopmentState], dict[str, object]]:
    def discovery_node(state: DevelopmentState) -> dict[str, object]:
        requirement_spec = pm_run(state['requirement'], state.get('conversation') or [])
        return {
            'requirement_spec': requirement_spec,
            'plan': None,
            'current_task': TaskStatus.WAIT_HUMAN_REQUIREMENT,
        }
    return discovery_node


def human_requirement_gate(_: DevelopmentState) -> dict[str, object]:
    return {}


def build_planning_node(planner_run: Callable[[dict[str, object]], dict[str, object]]) -> Callable[[DevelopmentState], dict[str, object]]:
    def planning_node(state: DevelopmentState) -> dict[str, object]:
        plan = planner_run(state['requirement_spec'])
        return {
            'plan': plan,
            'current_task': TaskStatus.WAIT_HUMAN_PLAN,
        }
    return planning_node


def human_plan_gate(_: DevelopmentState) -> dict[str, object]:
    return {}


def build_coding_node(coder_run: Callable[..., dict[str, object]]) -> Callable[[DevelopmentState], dict[str, object]]:
    def coding_node(state: DevelopmentState) -> dict[str, object]:
        result = coder_run(
            plan=state['plan'],
            current_files=state.get('code_files') or {},
            task_description=str(state['plan']['summary']),
        )
        return {
            'code_files': result.get('modified_files', {}),
            'current_task': TaskStatus.TESTING,
        }
    return coding_node


def build_testing_node(run_tests: Callable[[dict[str, str]], dict[str, object]]) -> Callable[[DevelopmentState], dict[str, object]]:
    def testing_node(state: DevelopmentState) -> dict[str, object]:
        test_results = run_tests(state.get('code_files') or {})
        next_task = TaskStatus.TESTING
        if test_results.get('status') == 'passed':
            next_task = TaskStatus.WAIT_HUMAN_CODE
        elif test_results.get('failure_type') in {'runtime_error', 'assertion_failure'}:
            next_task = TaskStatus.DEBUGGING
        elif test_results.get('failure_type') in {'static_check', 'build_error'}:
            next_task = TaskStatus.CODING
        return {
            'test_results': test_results,
            'current_task': next_task,
        }
    return testing_node


def build_debugging_node(debugger_run: Callable[..., dict[str, object]]) -> Callable[[DevelopmentState], dict[str, object]]:
    def debugging_node(state: DevelopmentState) -> dict[str, object]:
        result = debugger_run(
            code_files=state.get('code_files') or {},
            test_results=state.get('test_results') or {},
            error_log=(state.get('test_results') or {}).get('raw_logs'),
        )
        patched_files = dict(state.get('code_files') or {})
        patched_files.update(result.get('patches', {}))
        return {
            'code_files': patched_files,
            'debug_summary': result.get('diagnosis', ''),
            'current_task': TaskStatus.TESTING,
        }
    return debugging_node


def human_code_gate(_: DevelopmentState) -> dict[str, object]:
    return {}
