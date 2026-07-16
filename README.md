# OPC Development

一个基于 FastAPI + LangGraph 的本地优先多 Agent 开发系统。当前仓库对应 `v0.2.0`，核心方向是从旧的 MCP 依赖式编排，收敛到“状态 + 工具 + 目标 + 约束”的本地优先 ReAct 架构。

## 当前版本重点

- `Director` 负责自然对话和创意收敛，对系统只提交最小 `state_patch`。
- `PM -> Planner -> Coder -> Debugger -> Reviewer` 按状态驱动流程推进，不再依赖阶段动作语义。
- `tools/` 采用本地工具注册与 provider 路由，弱化外部依赖。
- `workspace/` 负责项目状态、checkpoint、产物和长期可复用信息持久化。
- `wecom_bot_bridge/` 作为企业微信入口桥接进程。

## 目录

- `main.py`：主 FastAPI 应用装配入口。
- `api/`：HTTP 路由和调试页面。
- `director/`：用户入口、会话和消息路由。
- `graph/`：开发流程运行时与状态跳转。
- `agents/`：多类 Agent、skill 装配、运行时策略。
- `tools/`：本地工具注册、provider 路由、沙箱执行。
- `config/`：skills 与 policy 配置。
- `workspace/`：SQLite 状态、项目记录、checkpoint、代码产物。
- `wecom_bot_bridge/`：企业微信桥接服务。
- `tests/`：unit/component/integration/scenario/contract 测试。

## 快速开始

需要 Python `3.11+`。如果只跑测试，不需要真实企业微信凭证。

```bash
python3 -m pip install -e .[dev]
cp .env.example .env
pytest -q
python3 -m uvicorn main:create_app --factory --host 0.0.0.0 --port 8000
python3 -m uvicorn wecom_bot_bridge.app:create_app --factory --host 0.0.0.0 --port 9001
```

默认情况下，应用使用 `OPENAI_API_KEY` 直接访问 OpenAI。只有在你明确需要兼容 OpenAI 风格代理时，才需要额外设置 `OPENAI_BASE_URL`。

## 运行方式

主服务：

```bash
python3 -m uvicorn main:create_app --factory --host 0.0.0.0 --port 8000
```

企业微信桥接：

```bash
python3 -m uvicorn wecom_bot_bridge.app:create_app --factory --host 0.0.0.0 --port 9001
```

## 启用 LangSmith Tracing

项目已接入两层 tracing：

- 所有经由 `OpenAIJSONClient` 的 LLM 调用会自动上报到 LangSmith。
- `WorkflowService`、各 Agent、测试节点和人工 checkpoint 会形成父子 trace。

启用方式：

```bash
python3 -m pip install -e .[dev]
cp .env.example .env
```

在 `.env` 中至少配置：

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=<your-langsmith-api-key>
LANGSMITH_PROJECT=opc-development
```

如果未安装 `langsmith` 或未配置这些变量，应用会自动降级，不会因为 tracing 失败而中断主流程。

## 架构文档

主架构说明见：[docs/architecture-design.md](docs/architecture-design.md)

## 仓库说明

- `.env`、`opc.db`、`new_project/` 属于本地产物，默认不会提交。
- 当前仓库更适合作为本地优先开发系统原型和架构实验基线。
- 如果要公开发布，建议补充 `LICENSE`、发布说明和一份最小演示截图或流程图。
