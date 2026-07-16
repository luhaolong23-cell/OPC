# OPC Development

一个基于 FastAPI + LangGraph 的本地优先多 Agent 开发系统。当前最小主线是：

1. `Director` 接收消息并路由。
2. `PM -> Planner -> Coder -> Debugger -> Reviewer` 按阶段推进。
3. `tools/` 提供本地工具注册、策略和执行。
5. `workspace/` 持久化项目、checkpoint 和产物。
6. `wecom_bot_bridge/` 作为企业微信入口桥接进程。

## 目录

- `main.py`：主 FastAPI 应用装配入口。
- `api/`：HTTP 路由和调试页面。
- `director/`：用户入口、会话和消息路由。
- `graph/`：开发流程运行时与状态跳转。
- `agents/`：五类 Agent、skill 装配、运行时策略。
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

## 启用 LangSmith Tracing

项目已接入两层 tracing：

- 所有经由 `OpenAIJSONClient` 的 LLM 调用会自动上报到 LangSmith
- `WorkflowService`、各 Agent、测试节点和人工 checkpoint 会形成父子 trace

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

## 最小架构说明

只保留一份架构文档：[docs/architecture-design.md](docs/architecture-design.md)。

## 推送前说明

- `.env` 和 `opc.db` 属于本地文件，已被 `.gitignore` 忽略。
- 目前未附带开源 `LICENSE`，推送公开仓库前请按你的授权要求补上。
