# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

听书智能客服系统，基于尚硅谷电商智能客服框架改造，将业务实体和流程替换为听书平台场景。

## 开发命令

```bash
# 安装依赖
uv sync

# 启动服务（从 .env 读取配置）
python -m audio_cs.main
# 或
uv run python -m audio_cs.main

# 运行自动化测试（22个用例，覆盖全部API和场景）
uv run python test_log/run_tests.py
```

`.env` 配置项（项目根目录）：
```
LLM_MODEL=qwen-plus
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=sk-...
AUDIO_API_BASE_URL=http://localhost:8000
DATABASE_URL=mysql+aiomysql://root:hzk686868@192.168.200.200:3306/audio_cs?charset=utf8mb4
APP_HOST=0.0.0.0
APP_PORT=18082
```

`test_log/` 目录为测试日志输出（已加入 .gitignore）。测试脚本 `test_log/run_tests.py` 为独立异步脚本（非 pytest），使用 httpx 调用本地 API，每次运行自动生成 `.log` 和 `.json` 两种格式报告。测试用例按分类组织：健康检查、闲聊场景、业务流程、知识查询、多轮对话、边界情况、历史记录。

## 架构

### 分层 DDD 设计

```
api/          — FastAPI 层：路由、应用生命周期、依赖注入
services/     — 编排层：加载/保存 DialogueState，委托给引擎
engine/       — 核心对话引擎：会话管理、消息路由、轮次生命周期
plan/         — LLM 规划层：TurnPlanner 调用 LLM → TurnPlan → 轨道路由
task/         — 业务流程子系统：命令、流程定义/加载/执行、动作
knowledge/    — 知识查询轨道
chitchat/     — 闲聊轨道
clarify/      — 意图澄清：规划校验失败时生成引导性反问
history/      — 历史构建：将 Turn 列表转为 LLM 可读文本或前端结构化数据
domain/       — 领域模型：DialogueState、Messages、Contexts
config/       — 配置：Pydantic Settings 从 .env 加载
infrastructure/ — 外部集成：LLM 客户端、异步DB、HTTP 客户端
repository/   — MySQL 持久化（SQLAlchemy，UPSERT 模式，状态存为 JSON blob）
model/        — ORM 模型（DialogueStateRecord）
prompts/      — Jinja2 提示词模板
```

### 请求流程

1. `POST /api/chat` → `ChatRequest` (Pydantic) → `UserMessage` (领域对象)
2. `DialogueService` 从 MySQL 加载 `DialogueState`，调用 `DialogueEngine.hand_message()`，保存状态
3. `DialogueEngine` 验证/创建会话（60分钟超时），开始轮次，按消息类型分支：
   - **TEXT**：`TurnPlanner` 调用 LLM → `TurnPlan` → 校验 → 路由到三条轨道之一
   - **OBJECT**（卡片点击）：解析为槽位命令，继续流程或澄清意图

### 三条处理轨道

1. **Task 轨道**（业务轨道）：LLM 输出命令（start_flow、resume_flow、cancel_flow、set_slots），由 `CommandProcessor` 处理
2. **Knowledge 轨道**（知识轨道）：匹配 `KnowledgeIntent`，调用 `KnowledgeProvider` 检索数据，LLM 生成回复
3. **ChitChat 轨道**（闲聊轨道）：LLM 直接生成闲聊回复

### 业务流程

业务逻辑在 YAML 中声明式定义（`flow_config/`）：
- **`user_flows.yml`**：5个业务流程 — 欢迎引导、订单查询、播放记录查询、退款申请、工单提交
- **`system_flows.yml`**：6个系统流程 — started、resumed、interrupted、canceled、collect_info、cannot_handle

### 数据后台

audio-data 项目提供模拟听书平台数据（42张表，10个API模块），通过 `AUDIO_API_BASE_URL` 连接。客服系统用 `X-User-Id` 请求头传递用户身份。

**重要**：audio-data 订单 API `/api/v1/orders/{orderId}` 使用数据库主键（整数 `id`），而用户输入的是 `orderNo`（如 ORD000000000004）。`fetch_order()` 通过两步查找转换：先调列表接口按 `orderNo` 匹配获取 `orderId`，再调详情接口。

### 关键设计要点

- **None 文本安全处理**：`history/builder.py` 的 `_render_text_msg` 使用 `(text or "").strip()` 而非 `text.strip()`，防止 text=None 时抛出 AttributeError
- **UPSERT 持久化**：`DialogueRepository.save_dialogue()` 使用 MySQL `INSERT ... ON DUPLICATE KEY UPDATE` 原子写入 DialogueState JSON
- **Action 自动发现**：`task/action/builder.py` 通过 `pkgutil.iter_modules` + `inspect.getmembers` 自动扫描 `audio_cs.task.action.customer` 包下所有 Action 子类
- **条件评估安全性**：`FlowExecutor._eval_condition()` 使用 `eval(condition, {}, data)` 禁用内置函数，仅暴露 `slots` 和 `context` 变量
- **服务依赖**：客服服务（18082）依赖 audio-data 后端（8000）提供数据，缺失时订单查询等业务流程无法正常工作
- **用户 5 已停用**：audio-data 平台中 `user_id=5` 的账户状态为 muted，API 返回 `USER_NOT_FOUND_OR_DISABLED`，测试应使用 user_id=1~4
