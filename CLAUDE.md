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

# 运行离线质量评估（200条黄金用例，需先启动服务）
uv run python -m evaluation.runner

# 回归检查（与基线对比，下降 > 5% 则退出码 1）
uv run python -m evaluation.regression_check

# 查看在线指标
curl http://localhost:18082/api/telemetry | python -m json.tool
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
history/      — 历史构建：将 Turn 列表转为 LLM 可读文本或前端结构化数据；summarizer 后台异步生成早期对话摘要
domain/       — 领域模型：DialogueState、Messages、Contexts
config/       — 配置：Pydantic Settings 从 .env 加载
infrastructure/ — 外部集成：LLM 客户端、异步DB、HTTP 客户端
repository/   — MySQL 持久化（SQLAlchemy，UPSERT 模式，状态存为 JSON blob）
model/        — ORM 模型（DialogueStateRecord）
prompts/      — Jinja2 提示词模板
evaluation/   — 质量评估系统：离线数据集、在线指标、LLM-as-Judge
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

audio-data 项目提供模拟听书平台数据（42张表，10个API模块），通过 `AUDIO_API_BASE_URL` 连接。客服系统用 `X-User-Id` 请求头传递用户身份。**启动客服服务时会自动拉起 audio-data 子进程**（`audio_cs/main.py` 中 `subprocess.Popen`），退出时自动关闭。audio-data 项目路径：`D:\05_PythonProject\25_尚硅谷大模型项目实战之掌柜小二实战\audio-data`。

**重要**：audio-data 订单 API `/api/v1/orders/{orderId}` 使用数据库主键（整数 `id`），而用户输入的是 `orderNo`（如 ORD000000000004）。`fetch_order()` 通过两步查找转换：先调列表接口按 `orderNo` 匹配获取 `orderId`，再调详情接口。

### 关键设计要点

- **对话摘要（Summarizer）**：超过 5 轮时，`summarizer.try_generate_summary()` 通过 `asyncio.create_task` 后台异步生成早期对话摘要，存入内存缓存。`TurnPlanner` 仅取最近 5 轮完整历史 + 缓存摘要，避免长对话撑爆上下文窗口。模板：`conversation_summary.jinja2`，超时 30 秒。
- **防历史干扰指令**：`turn_plan.jinja2` 中置入了高优先级规则，强制 LLM 基于当前消息语义判定轨道，不因历史中有任务流程而误判知识咨询为业务轨道。关键词分类："查询+抽象概念=knowledge"，"查询+具体对象=task"。
- **None 文本安全处理**：`history/builder.py` 的 `_render_text_msg` 使用 `(text or "").strip()` 而非 `text.strip()`，防止 text=None 时抛出 AttributeError
- **UPSERT 持久化**：`DialogueRepository.save_dialogue()` 使用 MySQL `INSERT ... ON DUPLICATE KEY UPDATE` 原子写入 DialogueState JSON
- **Action 自动发现**：`task/action/builder.py` 通过 `pkgutil.iter_modules` + `inspect.getmembers` 自动扫描 `audio_cs.task.action.customer` 包下所有 Action 子类
- **条件评估安全性**：`FlowExecutor._eval_condition()` 使用 `eval(condition, {}, data)` 禁用内置函数，仅暴露 `slots` 和 `context` 变量
- **服务依赖**：客服服务（18082）启动时自动拉起 audio-data（8000）子进程，退出时自动关闭。详情见 `audio_cs/main.py`。
- **前端订单面板**：`static/index.html` 右侧"我的订单"面板展示当前用户全部订单卡片，点击卡片发送 OBJECT 消息→引擎设置 `focused_object`→自动填入槽位或触发澄清。后端代理端点：`GET /api/orders?sender_id=xxx`。
- **用户 5 已停用**：audio-data 平台中 `user_id=5` 的账户状态为 muted，API 返回 `USER_NOT_FOUND_OR_DISABLED`，测试应使用 user_id=1~4
- **诊断与遥测**：`ProcessResult.diagnostics`（可选字段）在引擎处理消息时自动填充（预测轨道、意图、槽位、校验结果），通过 `ChatResponse.diagnostics` 透传到 API 响应。`evaluation/telemetry.py` 在 4 个关键分支点注入异步计数（轨道、澄清、延迟、流程），`GET /api/telemetry` 实时暴露快照，诊断和遥测均为零侵入——不影响现有功能。

### 质量评估系统

`evaluation/` 目录实现了四层金字塔评估框架（详见 `develop_log.md`"智能客服质量评价体系分析"）：

**第一层：意图与路由** — 轨道准确率、意图识别 F1、澄清率
**第二层：任务执行** — 槽位提取 F1、流程完成率
**第三层：回复质量** — 相关性/忠实度/完整性（LLM-as-Judge）
**第四层：体验与工程** — P50/P95 延迟、Token 消耗、轨道分布

核心文件：
- `evaluation/test_cases.py` — 200 条黄金测试用例（7 类）
- `evaluation/metrics.py` — 指标计算（轨道准确率、意图 F1、槽位 F1、澄清率）
- `evaluation/runner.py` — 离线评估运行器（遍历用例 → 调 API → 算指标 → 出报告）
- `evaluation/telemetry.py` — 在线指标收集器（内存计数，`GET /api/telemetry` 暴露）
- `evaluation/llm_judge.py` — LLM-as-Judge 三维度评分（相关性/忠实度/完整性）
- `evaluation/regression_check.py` — CI 回归检查（与 baseline.json 对比，下降 > 5% 退出码 1）

ChatResponse 新增可选 `diagnostics` 字段，引擎在 key 分支点注入遥测计数。`GET /api/telemetry` 返回实时的轨道分布、延迟分位数、流程完成率等快照。
