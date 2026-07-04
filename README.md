# OPC Development

一个基于 FastAPI + LangGraph 的本地优先多 Agent 开发系统。当前最小主线是：

1. `Director` 接收消息并路由。
2. `PM -> Planner -> Coder -> Debugger -> Reviewer` 按阶段推进。
3. `tools/` 提供本地工具注册、策略和执行。
4. `mcp/` + `tools/providers/mcp/` 提供 MCP 配置、映射和 Provider 接入。
5. `workspace/` 持久化项目、checkpoint 和产物。
6. `wecom_bot_bridge/` 作为企业微信入口桥接进程。

## 目录

- `main.py`：主 FastAPI 应用装配入口。
- `api/`：HTTP 路由和调试页面。
- `director/`：用户入口、会话和消息路由。
- `graph/`：开发流程运行时与状态跳转。
- `agents/`：五类 Agent、skill 装配、运行时策略。
- `tools/`：本地工具注册、provider 路由、沙箱执行。
- `mcp/`：MCP server 配置、逻辑工具映射、健康检查与回退规则。
- `config/`：skills、policy、mcp servers、logical mappings 配置。
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

可选预检查：

```bash
python3 -m scripts.preflight_stack
python3 -m scripts.launch_stack --print-only
```

## 最小架构说明

只保留一份架构文档：[docs/architecture-design.md](docs/architecture-design.md)。

## 推送前说明

- `.env` 和 `opc.db` 属于本地文件，已被 `.gitignore` 忽略。
- 目前未附带开源 `LICENSE`，推送公开仓库前请按你的授权要求补上。
