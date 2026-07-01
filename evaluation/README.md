# 智能客服质量评估系统

听书智能客服系统的离线/在线质量评估工具，基于四层金字塔评估框架，覆盖意图路由、任务执行、回复质量和体验工程四个维度。

## 快速开始

### 1. 启动服务

评估依赖本地运行的客服 API 服务：

```bash
uv run python -m audio_cs.main
```

### 2. 运行离线评估

```bash
uv run python -m evaluation.runner
```

运行后自动遍历 200 条黄金用例，生成两份报告到 `evaluation/reports/` 目录：

- `evaluation_YYYYMMDD_HHMMSS.md` — 可读的 Markdown 报告
- `evaluation_YYYYMMDD_HHMMSS.json` — 结构化 JSON 数据

### 3. 回归检查（CI 可用）

```bash
uv run python -m evaluation.regression_check
```

与 `evaluation/baseline.json` 对比，任一关键指标下降超过 5% 则退出码为 1（CI 失败）。

### 4. LLM-as-Judge 抽样评估

```bash
uv run python -m evaluation.llm_judge
```

从最近一次评估报告中抽样 knowledge 轨道对话，调用 LLM 对回复质量进行三维度打分。

### 5. 可视化仪表盘

```bash
uv run python -m evaluation.visualize
```

生成 `evaluation/reports/dashboard.html`，浏览器打开即可查看多轮评估的交互式趋势图表。

### 6. 查看在线指标

服务运行期间，实时遥测快照：

```bash
curl http://localhost:18082/api/telemetry | python -m json.tool
```

---

## 评估框架：四层金字塔

```
        ┌─────────────┐
        │ 体验与工程    │  ← P50/P95延迟、Token消耗、轨道分布
       ┌┤  Layer 4     ├┐
       │└─────────────┘│
      ┌┤  回复质量     ├┐ ← 相关性/忠实度/完整性 (LLM-as-Judge)
      │└─────────────┘│
     ┌┤  任务执行     ├┐  ← 槽位提取F1、流程完成率
     │└─────────────┘│
    ┌┤  意图与路由   ├┐   ← 轨道准确率、意图识别F1、澄清率
    │└─────────────┘│
    └───────────────┘
```

---

## 黄金测试用例（200 条，7 类）

| 类别 | 数量 | 说明 |
|------|------|------|
| **routing** | 40 条 | 轨道选择准确率 —— 验证消息正确分发到 task/knowledge/chitchat/clarify |
| **slot_filling** | 40 条 | 槽位提取 F1 —— 验证订单号、书名、退款原因等关键信息提取 |
| **knowledge** | 40 条 | 知识意图识别 —— 验证知识查询时的意图分类（会员、平台规则、专辑信息等） |
| **flow_completion** | 20 条 | 完整多轮业务流程 —— 验证退款、工单、订单查询等端到端流程 |
| **anti_interference** | 20 条 | 防历史干扰 —— 验证长对话中不会被历史上下文误导轨道判断 |
| **edge_case** | 20 条 | 边界情况 —— 空文本、特殊字符、中英混合、SQL注入式输入等 |
| **clarify** | 20 条 | 澄清触发 —— 验证模糊/无意义输入正确触发意图澄清 |

测试用例定义在 `test_cases.py`，每个用例包含：
- `id` — 唯一标识
- `category` — 所属类别
- `description` — 用例描述
- `turns` — 单轮或多轮对话，每轮包含 `user_input`、`expected_track`、可选 `expected_intent`、`expected_slots`

---

## 指标详解

### 轨道准确率（Track Accuracy）

```
轨道准确率 = 预测轨道正确的轮次数 / 总轮次数
```

四种轨道：
| 轨道 | 含义 | 示例 |
|------|------|------|
| `task` | 业务流程 | 查订单、申请退款、提交工单 |
| `knowledge` | 知识查询 | 会员权益、退款政策、作品信息 |
| `chitchat` | 闲聊 | 问候、感谢、天气 |
| `clarify` | 意图澄清 | 用户输入模糊，需要反问引导 |

评级标准：A ≥ 90%，B ≥ 80%，C < 80%

### 意图识别 F1（Intent F1）

仅在 knowledge 轨道上计算。对每个知识意图类别（如 `membership_info`、`platform_rule`、`album_info`、`album_content_detail`）计算宏平均 F1。

评级标准：A ≥ 85%，B ≥ 70%，C < 70%

### 槽位提取 F1（Slot F1）

在 task 轨道上计算。按槽位名称（如 `order_number`、`album_title`、`refund_reason`、`ticket_type`）分别计算精确率和召回率，取宏平均。槽位值匹配使用模糊比较（包含即认为正确）。

评级标准：A ≥ 85%，B ≥ 70%，C < 70%

### 澄清率（Clarify Rate）

```
澄清率 = 触发澄清的轮次数 / 总轮次数
```

澄清率过高说明系统对用户意图的理解能力不足；过低可能意味着在模糊输入时仍强行路由导致答非所问。

评级标准：A ≤ 8%，B ≤ 15%，C > 15%

### 流程完成率（Flow Completion Rate）

按流程名称（`order_query`、`refund_apply`、`ticket_submit`、`playback_query`）统计启动次数和完成次数。

### LLM-as-Judge 三维度

| 维度 | 评分范围 | 说明 |
|------|----------|------|
| **相关性** | 1-5 | 回复是否切中用户问题，不偏离主题 |
| **忠实度** | 0-1 | 回复中的断言能否从知识库中找到支撑，检测幻觉 |
| **完整性** | 1-5 | 回复是否覆盖用户需要的所有信息，避免用户追问 |

评级标准：A ≥ 4.0，B ≥ 3.0，C < 3.0

### 在线遥测指标

通过 `GET /api/telemetry` 实时获取：

| 指标 | 说明 |
|------|------|
| `track_distribution` | 各轨道占比 |
| `clarify_rate` | 实时澄清率 |
| `latency_p50/p95/p99` | 请求延迟分位数（最近 1000 条） |
| `flow_completion_rate` | 各流程完成率 |
| `slot_accuracy` | 槽位提取成功率 |

---

## 报告解读

### 终端输出

```text
  轨道准确率: 95.28%  (242/254)
  意图 F1:    30.17%
  槽位 F1:    87.31%
  澄清率:     16.54%
  routing             : 97.50% ███████████████████
  slot_filling        : 90.00% ██████████████████
  knowledge           : 95.00% ███████████████████
  ...
```

### Markdown 报告

包含核心指标表格（含评级）、各类别准确率、轨道判断错误 Top 20 详情。

### JSON 报告

完整的结构化数据，包含每条用例的每轮对话结果、诊断信息，适合接入 CI/CD 管道或自定义分析。

### 可视化仪表盘

将多份评估报告转化为交互式图表，直观对比各轮优化的指标变化：

```bash
uv run python -m evaluation.visualize
```

运行后在 `evaluation/reports/` 下生成 `dashboard.html`，浏览器直接打开即可查看。

**仪表盘内容（4 张图表 + 优化历程）：**

- **概览卡片**：起始/最终准确率、累计提升、槽位 F1、错误数、反干扰精度
- **核心指标趋势折线图**：轨道准确率、槽位 F1、意图 F1、澄清率的逐轮变化，标注关键优化动作（markPoint + markArea）
- **各类别准确率柱状图**：7 个类别 × 每轮的分组对比
- **500 错误下降图**：标注重试机制上线节点
- **准确率增益瀑布图**：每轮净提升百分比，hover 显示该轮详细改动
- **优化历程卡片行**：每轮的改动列表、涉及文件、效果说明

**自动化程度**：静态生成，每次新增评估报告后重新运行脚本即可更新仪表盘。脚本自动扫描 `evaluation/reports/` 下所有 JSON 文件，无需手动指定。

**设计要点**：
- 色标徽章区分优化类型：基线（灰）/ Prompt（蓝）/ Engine（橙）/ 微调（紫）
- 图表使用 ECharts 5.5（CDN），交互式 tooltip 悬停显示每轮具体改动
- 新增报告自动包含，OPTIMIZATION_NOTES 中需手动补充对应的轮次说明

---

## 工作流建议

1. **日常开发**：修改核心逻辑后运行 `runner.py`，确认指标无明显下降
2. **提 PR 前**：运行 `regression_check.py`，确保不引入退化
3. **发版前**：运行 `llm_judge.py`，抽样检查回复质量
4. **线上监控**：通过 `/api/telemetry` 持续观察轨道分布和延迟分位数

### 建立基线

首次运行评估后，将报告中的关键指标手动写入 `evaluation/baseline.json`（或运行一次 `regression_check.py` 自动生成）。后续每次评估都可与基线对比。

### 添加新用例

在 `test_cases.py` 对应类别列表中新增 `GoldenTestCase`，按现有格式填写 `id`、`category`、`description` 和 `turns` 即可。
