from __future__ import annotations

from dataclasses import dataclass, field

from agents import base as base_module
from agents.factory import build_agent
from llm.client import OpenAIJSONClient
from tools.defaults import build_default_tool_registry


class DummyOpenAIClient:
    pass


@dataclass
class FakeGraph:
    response: dict
    inputs: list[dict] = field(default_factory=list)

    def invoke(self, payload: dict) -> dict:
        self.inputs.append(payload)
        return {'structured_response': self.response}


@dataclass
class DummyChatModel:
    kwargs: dict


def test_pm_agent_uses_create_react_agent_when_openai_json_client_is_available(monkeypatch) -> None:
    created: dict[str, object] = {}
    fake_graph = FakeGraph(
        {
            'summary': 'spec summary',
            'candidate_solutions': ['cli'],
            'open_questions': [],
            'assumptions': [],
            'risks': [],
            'constraints': [],
            'recommended_direction': None,
            'next_action': 'close_brainstorm',
        }
    )

    def fake_chat_openai(**kwargs):
        created['chat_kwargs'] = kwargs
        return DummyChatModel(kwargs)

    def fake_create_react_agent(model, tools, **kwargs):
        created['model'] = model
        created['tools'] = tools
        created['kwargs'] = kwargs
        return fake_graph

    monkeypatch.setattr(base_module, 'ChatOpenAI', fake_chat_openai)
    monkeypatch.setattr(base_module, 'create_react_agent', fake_create_react_agent)

    llm = OpenAIJSONClient(model='gpt-test', api_key='key', base_url='http://example.com/v1', client=DummyOpenAIClient())
    agent = build_agent('pm', model='gpt-test', llm_client=llm, tool_registry=build_default_tool_registry())

    result = agent.run('build todo api')

    assert result['summary'] == 'spec summary'
    assert created['chat_kwargs']['model'] == 'gpt-test'
    assert created['chat_kwargs']['api_key'] == 'key'
    assert created['chat_kwargs']['base_url'] == 'http://example.com/v1'
    assert len(created['tools']) == 3
    assert fake_graph.inputs[0]['messages'][0]['role'] == 'user'


def test_coder_agent_passes_bound_executable_tools_to_create_react_agent(monkeypatch) -> None:
    created: dict[str, object] = {}
    fake_graph = FakeGraph({'modified_files': {'app.py': "print('ok')\n"}, 'summary': 'implemented'})

    def fake_chat_openai(**kwargs):
        return DummyChatModel(kwargs)

    def fake_create_react_agent(model, tools, **kwargs):
        created['tools'] = tools
        created['kwargs'] = kwargs
        return fake_graph

    monkeypatch.setattr(base_module, 'ChatOpenAI', fake_chat_openai)
    monkeypatch.setattr(base_module, 'create_react_agent', fake_create_react_agent)

    llm = OpenAIJSONClient(model='gpt-test', api_key='key', base_url='http://example.com/v1', client=DummyOpenAIClient())
    agent = build_agent('coder', model='gpt-test', llm_client=llm, tool_registry=build_default_tool_registry())

    result = agent.run({'summary': 'plan summary'}, current_files={'app.py': "print('old')\n"}, task_description='implement feature')

    assert result == {'modified_files': {'app.py': "print('ok')\n"}, 'summary': 'implemented'}
    assert [tool.name for tool in created['tools']] == ['repo_reader', 'patch_applier', 'test_runner']


def test_director_agent_uses_create_react_agent_when_openai_json_client_is_available(monkeypatch) -> None:
    created: dict[str, object] = {}
    fake_graph = FakeGraph(
        {
            'reply': '请继续补充一个最关键约束。',
            'state_patch': {
                'requirement_draft': '开发一个最小 Python 贪吃蛇游戏。',
                'conversation_summary': '用户希望开发最小 Python 贪吃蛇游戏。',
                'ready_to_start': False,
            },
        }
    )

    def fake_chat_openai(**kwargs):
        created['chat_kwargs'] = kwargs
        return DummyChatModel(kwargs)

    def fake_create_react_agent(model, tools, **kwargs):
        created['model'] = model
        created['tools'] = tools
        created['kwargs'] = kwargs
        return fake_graph

    monkeypatch.setattr(base_module, 'ChatOpenAI', fake_chat_openai)
    monkeypatch.setattr(base_module, 'create_react_agent', fake_create_react_agent)

    llm = OpenAIJSONClient(model='gpt-test', api_key='key', base_url='http://example.com/v1', client=DummyOpenAIClient())
    agent = build_agent('director', model='gpt-test', llm_client=llm, tool_registry=build_default_tool_registry())

    turn = agent.run(
        '我想做一个贪吃蛇游戏',
        project_context={'available_actions': ['chat_reply']},
    )

    assert turn.message == '请继续补充一个最关键约束。'
    assert created['chat_kwargs']['model'] == 'gpt-test'
    assert created['chat_kwargs']['api_key'] == 'key'
    assert created['chat_kwargs']['base_url'] == 'http://example.com/v1'
    assert [tool.name for tool in created['tools']] == ['repo_reader', 'structure_summary', 'rg_search']
    assert fake_graph.inputs[0]['messages'][0]['role'] == 'user'


def test_coder_agent_react_prompt_requires_multi_step_tool_loop_before_structured_output(monkeypatch) -> None:
    created: dict[str, object] = {}
    fake_graph = FakeGraph({'modified_files': {'app.py': "print('ok')\n"}, 'summary': 'implemented'})

    def fake_chat_openai(**kwargs):
        return DummyChatModel(kwargs)

    def fake_create_react_agent(model, tools, **kwargs):
        created['tools'] = tools
        created['kwargs'] = kwargs
        return fake_graph

    monkeypatch.setattr(base_module, 'ChatOpenAI', fake_chat_openai)
    monkeypatch.setattr(base_module, 'create_react_agent', fake_create_react_agent)

    llm = OpenAIJSONClient(model='gpt-test', api_key='key', base_url='http://example.com/v1', client=DummyOpenAIClient())
    agent = build_agent('coder', model='gpt-test', llm_client=llm, tool_registry=build_default_tool_registry())

    agent.run({'summary': 'plan summary'}, current_files={'app.py': "print('old')\n"}, task_description='implement feature')

    prompt = str(created['kwargs']['prompt'])
    assert 'Use tools for as many steps as needed' in prompt
    assert 'Only produce the final structured response after' in prompt
