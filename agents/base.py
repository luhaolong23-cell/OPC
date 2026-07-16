from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from agents.capabilities import AgentProfile, SkillSpec
from agents.runtime.execution_context import ExecutionContext
from agents.runtime.skill_resolver import SkillResolver
from llm import StructuredLLMClient
from tools.registry import BoundAgentTools
from tools.specs import ToolCallResult

try:
    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI
    from langgraph.prebuilt import create_react_agent
except ImportError:  # pragma: no cover
    tool = None
    ChatOpenAI = None
    create_react_agent = None


class BaseAgent(ABC):
    def __init__(
        self,
        *,
        model: str | None = None,
        llm_client: StructuredLLMClient | None = None,
        profile: AgentProfile | None = None,
        skills: dict[str, SkillSpec] | None = None,
        skill_resolver: SkillResolver | None = None,
        tools: BoundAgentTools | None = None,
        role_instructions: str = "",
    ) -> None:
        self.model = model
        self.llm_client = llm_client
        self.profile = profile
        self.skills = skills or {}
        self.skill_resolver = skill_resolver or SkillResolver(skills=dict(self.skills))
        self.tools = tools or BoundAgentTools({})
        self.role_instructions = role_instructions

    def skill_instructions(self, skill_name: str, default: str) -> str:
        skill = self.skills.get(skill_name)
        if skill is None:
            skill = self.skill_resolver.resolve(skill_name)
            self.skills[skill_name] = skill
        return skill.instructions if skill is not None else default

    def available_tools(self) -> list[dict[str, object]]:
        return [
            {
                'name': getattr(tool_handle, 'name', name),
                'description': getattr(tool_handle, 'description', name),
                'capability_tags': list(getattr(tool_handle, 'capability_tags', ())),
                'side_effect_level': getattr(tool_handle, 'side_effect_level', 'read'),
            }
            for name, tool_handle in self.tools.tools.items()
        ]

    def build_instructions(self, skill_name: str, default: str) -> str:
        instructions = self.skill_instructions(skill_name, default)
        if self.role_instructions:
            instructions = f"{self.role_instructions}\n\n## Current Task\n{instructions}"
        tools = self.available_tools()
        if not tools:
            return instructions
        lines = [instructions, '', '## Bound Tools', 'You may only rely on the following tools that are already bound to this agent.']
        for tool_info in tools:
            lines.append(
                f"- {tool_info['name']}: {tool_info['description']} "
                f"(tags: {', '.join(tool_info['capability_tags']) or 'none'}, side_effect: {tool_info['side_effect_level']})"
            )
        return '\n'.join(lines)

    def build_input_text(self, payload: dict[str, Any]) -> str:
        enriched_payload = dict(payload)
        enriched_payload['tools'] = self.available_tools()
        return json.dumps(enriched_payload, ensure_ascii=False)

    def _agent_name(self) -> str:
        if self.profile is not None and self.profile.name:
            return self.profile.name
        return self.__class__.__name__.removesuffix('Agent').lower()

    def build_execution_context(self, *, workflow_stage: str, write_allowed: bool) -> ExecutionContext:
        return ExecutionContext(
            agent_name=self._agent_name(),
            workflow_stage=workflow_stage,
            project_type='python',
            environment='local',
            user_mode='interactive',
            network_allowed=False,
            write_allowed=write_allowed,
            external_allowed=False,
        )

    def execute_bound_tool(self, name: str, arguments: dict[str, Any], *, workflow_stage: str, write_allowed: bool) -> ToolCallResult:
        context = self.build_execution_context(workflow_stage=workflow_stage, write_allowed=write_allowed)
        return self.tools.execute(name, arguments, context)

    def _react_capable(self) -> bool:
        return (
            self.llm_client is not None
            and ChatOpenAI is not None
            and create_react_agent is not None
            and tool is not None
            and hasattr(self.llm_client, 'model')
            and hasattr(self.llm_client, 'api_key')
            and hasattr(self.llm_client, 'base_url')
        )

    def _build_chat_model(self):
        return ChatOpenAI(
            model=getattr(self.llm_client, 'model'),
            api_key=getattr(self.llm_client, 'api_key', None),
            base_url=getattr(self.llm_client, 'base_url', None),
            temperature=0,
        )

    def _augment_tool_arguments(self, tool_name: str, arguments: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(arguments)
        current_files = payload.get('current_files') or payload.get('code_files') or {}
        if tool_name in {'repo_reader', 'rg_search', 'py_tree_sitter_parse', 'ast_grep_search', 'structure_summary', 'diff_reader', 'semgrep_scan', 'difftastic_diff'} and 'root_dir' not in enriched and current_files:
            enriched.setdefault('code_files', current_files)
        if tool_name == 'patch_applier' and 'root_dir' not in enriched:
            enriched.setdefault('current_files', current_files)
        if tool_name == 'test_runner' and 'root_dir' not in enriched and current_files:
            enriched.setdefault('code_files', current_files)
        if tool_name == 'log_reader' and 'path' not in enriched and 'root_dir' not in enriched:
            if 'content' not in enriched:
                enriched['content'] = payload.get('error_log') or (payload.get('test_results') or {}).get('raw_logs') or ''
        return enriched

    def _build_react_tools(self, *, payload: dict[str, Any], workflow_stage: str, write_allowed: bool):
        if tool is None:
            return []
        react_tools = []
        for name, tool_handle in self.tools.tools.items():
            if getattr(tool_handle, 'backend', None) is None:
                continue
            description = getattr(tool_handle, 'description', name)

            def _make_tool(tool_name: str, tool_description: str):
                @tool(name_or_callable=tool_name, description=f"{tool_description} Pass tool arguments as a JSON string in the `payload` field.")
                def _run_tool(payload_json: str = '{}') -> str:
                    raw_arguments = json.loads(payload_json) if payload_json and payload_json.strip() else {}
                    if not isinstance(raw_arguments, dict):
                        raise ValueError('tool payload must decode to a JSON object')
                    tool_arguments = self._augment_tool_arguments(tool_name, raw_arguments, payload)
                    result = self.execute_bound_tool(tool_name, tool_arguments, workflow_stage=workflow_stage, write_allowed=write_allowed)
                    return json.dumps(
                        {
                            'ok': result.ok,
                            'output': result.output,
                            'error': result.error,
                            'provider': result.provider,
                        },
                        ensure_ascii=False,
                    )

                return _run_tool

            react_tools.append(_make_tool(name, description))
        return react_tools

    def build_react_prompt(self, skill_name: str, default: str) -> str:
        instructions = self.skill_instructions(skill_name, default)
        react_contract = (
            'Use tools for as many steps as needed before deciding on the final answer. '
            'Observe each tool result, update your plan, and continue until you have enough evidence to finish. '
            'Only produce the final structured response after the work has converged or no further tool call would add value.'
        )
        if self.role_instructions:
            return f"{self.role_instructions}\n\n## ReAct Execution Contract\n{react_contract}\n\n## Current Task\n{instructions}"
        return f"## ReAct Execution Contract\n{react_contract}\n\n## Current Task\n{instructions}"

    def run_via_react(
        self,
        *,
        skill_name: str,
        default_instructions: str,
        payload: dict[str, Any],
        response_format: Any,
        workflow_stage: str,
        write_allowed: bool,
    ) -> dict[str, Any] | None:
        if not self._react_capable():
            return None
        graph = create_react_agent(
            self._build_chat_model(),
            tools=self._build_react_tools(payload=payload, workflow_stage=workflow_stage, write_allowed=write_allowed),
            prompt=self.build_react_prompt(skill_name, default_instructions),
            response_format=response_format,
            name=f"{self._agent_name()}_{skill_name}",
        )
        result = graph.invoke(
            {
                'messages': [
                    {
                        'role': 'user',
                        'content': self.build_input_text(payload),
                    }
                ]
            }
        )
        state = getattr(result, 'value', result)
        structured = state.get('structured_response') if isinstance(state, dict) else getattr(state, 'structured_response', None)
        if structured is None:
            raise ValueError('create_react_agent did not return structured_response')
        if hasattr(structured, 'model_dump'):
            return structured.model_dump()
        if isinstance(structured, dict):
            return structured
        return dict(structured)

    @abstractmethod
    def run(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError
