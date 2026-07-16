# OPC Development 架构说明

这个仓库现在只保留一份最小架构文档，用来说明真实运行骨架，不再堆叠历史方案、交付说明和实施计划。

## 目标

系统目标是提供一条可验证的多 Agent 开发主线：

`Director -> PM -> Planner -> Coder -> Debugger -> Reviewer`

并通过 `workspace`、`tools`、`wecom_bot_bridge` 把状态、工具和外部接入串起来。

## 运行入口

- `main.py`
  - 负责创建 FastAPI 应用。
  - 装配 `WorkspaceManager`、`ToolRegistry`、`SkillRegistry`、`WorkflowService`、`WechatMessageService`。
  - 在 lifespan 中启动和关闭 tool registry。
- `wecom_bot_bridge/app.py`
  - 作为企业微信桥接进程。
  - 负责文本消息转发、通知回推和健康检查。

## 分层

### 1. 接口层

- `api/`
  - HTTP API、调试页、健康检查、项目/反馈入口。
- `director/`
  - 用户消息路由、会话状态、启动项目和聊天入口。
- `wecom_bot_bridge/`
  - 企业微信 WebSocket/SDK 适配层。

### 2. 工作流层

- `graph/`
  - `builder.py` 负责图组装。
  - `runtime.py` 负责项目启动、checkpoint 流转和反馈应用。
  - `nodes.py`、`edges.py` 封装阶段逻辑和回退策略。

主成功路径保持为：

`DISCOVERY -> WAIT_HUMAN_REQUIREMENT -> PLANNING -> WAIT_HUMAN_PLAN -> CODING -> TESTING -> WAIT_HUMAN_CODE -> REVIEW -> WAIT_HUMAN_FINAL -> DONE`

### 3. Agent 层

- `agents/`
  - 五类 Agent 实现。
  - `factory.py` 统一装配 LLM、skills、tools、role instructions。
  - `profiles.py` 定义每类 Agent 的允许 skill 和 tool tag。

### 4. Skill 层

- `agents/skills/`
  - 内置 skill 定义、外部 skill source、registry、loader。
- `agents/runtime/skill_resolver.py`
  - 根据 profile 和 registry 在运行时解析 skill。

当前原则：

- skill 是可替换的指令资产，不直接承载业务状态。
- Agent 通过 profile 决定允许使用哪些 skill。
- 新 skill 先接入 `config/skills/` 或 `agents/skills/builtin/`，再进入运行时。

### 5. Tool 层

- `tools/`
  - 本地工具注册、策略控制、provider 路由、沙箱测试执行。

这里保留两层不是重复：


### 6. 状态层

- `workspace/`
  - 管理项目、checkpoint、代码文件、会话绑定和持久化。
  - 当前默认数据库为 SQLite。

## 配置边界

- `config/mappings/`：逻辑工具到 provider 的映射
- `config/policies/`：tool policy
- `config/skills/`：skill source 配置

默认装配入口在 `tools/defaults.py` 和 `agents/skills/registry.py`。

## 保留原则

清理后仓库只保留这些长期有效内容：

- 真实运行代码
- 当前测试
- 一份 README
- 一份架构文档

历史实施计划、废弃方案、缓存和打包生成物不再保留在主仓结构里。
