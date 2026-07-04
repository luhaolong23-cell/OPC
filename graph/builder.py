from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from graph.edges import decide_after_code, decide_after_plan, decide_after_requirement, decide_after_testing
from graph.nodes import (
    build_coding_node,
    build_debugging_node,
    build_discovery_node,
    build_planning_node,
    build_testing_node,
    human_code_gate,
    human_plan_gate,
    human_requirement_gate,
)
from workspace.state import DevelopmentState


def build_development_graph(pm_agent, planner_agent, coder_agent=None, debugger_agent=None, sandbox=None, checkpointer=None):
    builder = StateGraph(DevelopmentState)
    builder.add_node('discovery', build_discovery_node(pm_agent.run))
    builder.add_node('human_requirement_gate', human_requirement_gate)
    builder.add_node('planning', build_planning_node(planner_agent.run))
    builder.add_node('human_plan_gate', human_plan_gate)
    if coder_agent is not None and debugger_agent is not None and sandbox is not None:
        builder.add_node('coding', build_coding_node(coder_agent.run))
        builder.add_node('testing', build_testing_node(sandbox.run_tests))
        builder.add_node('debugging', build_debugging_node(debugger_agent.run))
        builder.add_node('human_code_gate', human_code_gate)

    builder.add_edge(START, 'discovery')
    builder.add_edge('discovery', 'human_requirement_gate')
    builder.add_conditional_edges('human_requirement_gate', decide_after_requirement, {
        'planning': 'planning',
        'discovery': 'discovery',
        'end': END,
    })
    builder.add_edge('planning', 'human_plan_gate')
    if coder_agent is not None and debugger_agent is not None and sandbox is not None:
        builder.add_conditional_edges('human_plan_gate', decide_after_plan, {
            'coding': 'coding',
            'planning': 'planning',
            'end': END,
        })
        builder.add_edge('coding', 'testing')
        builder.add_conditional_edges('testing', decide_after_testing, {
            'human_code_gate': 'human_code_gate',
            'debugging': 'debugging',
            'coding': 'coding',
            'end': END,
        })
        builder.add_edge('debugging', 'testing')
        builder.add_conditional_edges('human_code_gate', decide_after_code, {
            'coding': 'coding',
            'planning': 'planning',
            'end': END,
        })
    else:
        builder.add_conditional_edges('human_plan_gate', decide_after_plan, {
            'planning': 'planning',
            'end': END,
        })
    return builder.compile(checkpointer=checkpointer)
