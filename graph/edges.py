from __future__ import annotations

from workspace.state import DevelopmentState


def decide_after_requirement(state: DevelopmentState) -> str:
    feedback = state.get('human_feedback')
    if feedback is None or feedback.get('target') != 'requirement_review':
        return 'end'
    if feedback.get('action') == 'approve':
        return 'planning'
    if feedback.get('action') == 'revise':
        return 'discovery'
    return 'end'


def decide_after_plan(state: DevelopmentState) -> str:
    feedback = state.get('human_feedback')
    if feedback is None or feedback.get('target') != 'plan_review':
        return 'end'
    if feedback.get('action') == 'approve':
        return 'coding'
    if feedback.get('action') == 'revise':
        return 'planning'
    return 'end'


def decide_after_testing(state: DevelopmentState) -> str:
    test_results = state.get('test_results')
    if test_results is None:
        return 'end'
    if test_results.get('status') == 'passed':
        return 'human_code_gate'
    failure_type = test_results.get('failure_type')
    if failure_type in {'runtime_error', 'assertion_failure'}:
        return 'debugging'
    if failure_type in {'static_check', 'build_error'}:
        return 'coding'
    return 'end'


def decide_after_code(state: DevelopmentState) -> str:
    feedback = state.get('human_feedback')
    if feedback is None or feedback.get('target') != 'code_review':
        return 'end'
    if feedback.get('action') == 'approve':
        return 'end'
    if feedback.get('action') == 'revise':
        return 'coding'
    if feedback.get('action') == 'replan':
        return 'planning'
    return 'end'
