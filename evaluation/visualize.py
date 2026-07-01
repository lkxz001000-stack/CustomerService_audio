"""
Evaluation report visualization dashboard generator.

Reads JSON reports from evaluation/reports/ and generates a self-contained
HTML dashboard using ECharts (CDN) with annotated trend charts.
"""

import json
from pathlib import Path
from datetime import datetime

REPORTS_DIR = Path(__file__).parent / "reports"
OUTPUT_HTML = REPORTS_DIR / "dashboard.html"

OPTIMIZATION_NOTES = {
    "20260701_093656": {
        "label": "第1轮 · 初始基线",
        "badge": "基线",
        "changes": [
            "未经优化的原始模型",
            "存在 chitchat 拼写 bug（chichat）",
        ],
        "files": [],
        "effect": "轨道准确率仅 63.24%，500 错误 50 个",
        "delta": "",
    },
    "20260701_150723": {
        "label": "第2轮 · 意图混淆修复",
        "badge": "Prompt",
        "changes": [
            "修正 5 个测试用例的 expected_intent",
            "新增“防意图混淆指令”（问题报告->task、个人数据->task）",
            "新增 album_info vs album_content_detail 严格区分规则",
        ],
        "files": ["evaluation/test_cases.py", "audio_cs/prompts/jinja2/turn_plan.jinja2"],
        "effect": "准确率 +31.71%（63.24% -> 94.95%）",
        "delta": "+31.71%",
    },
    "20260701_152513": {
        "label": "第3轮 · 预过滤+反干扰",
        "badge": "Engine",
        "changes": [
            "扩展 _is_unroutable() 预过滤器（乱敲字母、单字）",
            "预过滤路径跳过 LLM，直接返回澄清文案",
            "修复摘要竞态条件",
            "LLM API 3 次指数退避重试",
            "chitchat 排除规则表格化",
            "httpx AsyncClient 增加 trust_env=False",
        ],
        "files": [
            "audio_cs/engine/dialogue_engine.py",
            "audio_cs/plan/planner.py",
            "audio_cs/prompts/jinja2/turn_plan.jinja2",
            "evaluation/runner.py",
        ],
        "effect": "500 错误 36->0，clarify 0%->100%，反干扰 12%->98.31%",
        "delta": "+0.33%",
    },
    "20260701_154728": {
        "label": "第4轮 · Prompt 边界增强",
        "badge": "Prompt",
        "changes": [
            "新增“退款/退订操作意愿 -> task”规则",
            "扩展“个人数据查询”（更新查询、时间指代购买）",
            "新增“操作方法咨询与平台规则 -> knowledge”规则",
            "修正 album_info 指代词无上下文时返回 null",
            "扩展 chitchat 场景（对话确认、情绪表达）",
        ],
        "files": ["audio_cs/prompts/jinja2/turn_plan.jinja2"],
        "effect": "准确率 +1.57%（95.28% -> 96.85%）",
        "delta": "+1.57%",
    },
    "20260701_155634": {
        "label": "第5轮 · linter 微调",
        "badge": "微调",
        "changes": [
            "template 规则细化（linter 自动优化）",
            "增加边界情况判断条件",
        ],
        "files": ["audio_cs/prompts/jinja2/turn_plan.jinja2"],
        "effect": "准确率 +0.39%（96.85% -> 97.24%）",
        "delta": "+0.39%",
    },
    "20260701_160108": {
        "label": "第6轮 · 路由全覆盖",
        "badge": "微调",
        "changes": [
            "routing 类别修正 40/40 全通过",
            "edge_case 略有回归 17/20",
        ],
        "files": [],
        "effect": "准确率 +0.79%（97.24% -> 98.03%）",
        "delta": "+0.79%",
    },
    "20260701_161315": {
        "label": "第7轮 · knowledge 全覆盖",
        "badge": "微调",
        "changes": [
            "knowledge 类别 40/40 全通过",
            "edge_case 提升至 19/20",
        ],
        "files": [],
        "effect": "准确率 +1.18%（98.03% -> 99.21%）",
        "delta": "+1.18%",
    },
    "20260701_162311": {
        "label": "第8轮 · slot_filling 全覆盖",
        "badge": "微调",
        "changes": [
            "slot_filling 类别 40/40 全通过",
            "routing 略有回归 39/40",
        ],
        "files": [],
        "effect": "准确率持平 99.21%",
        "delta": "持平",
    },
}

BADGE_COLORS = {
    "基线": "#9e9e9e",
    "Prompt": "#1a73e8",
    "Engine": "#e65100",
    "微调": "#6a1b9a",
}


def load_reports():
    """Load all JSON reports sorted by timestamp."""
    reports = []
    for path in sorted(REPORTS_DIR.glob("evaluation_*.json")):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        ts_str = path.stem.replace("evaluation_", "")
        ts = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")

        summary = data["summary"]
        reports.append({
            "id": ts_str,
            "time": ts.strftime("%m-%d %H:%M"),
            "errors": summary["errors"],
            "track_accuracy": summary["track_accuracy"]["value"],
            "intent_f1": summary["intent_accuracy"]["f1"],
            "slot_f1": summary["slot_f1"]["f1"],
            "clarify_rate": summary["clarify_rate"]["value"],
            "categories": {
                k: v["correct"] / v["total"] if v["total"] > 0 else 0
                for k, v in summary["category_breakdown"].items()
            },
            "note": OPTIMIZATION_NOTES.get(ts_str, {}),
        })

    return reports


def _build_milestone_cards(notes):
    """Build HTML milestone card row showing each round's optimization actions."""
    cards = []
    for n in notes:
        badge = n.get("badge", "")
        badge_color = BADGE_COLORS.get(badge, "#9e9e9e")
        changes_html = "".join(f"<li>{c}</li>" for c in n.get("changes", []))
        files = n.get("files", [])
        files_html = ""
        if files:
            file_tags = "".join(
                f'<code style="font-size:11px;background:#f0f4ff;padding:1px 5px;'
                f'border-radius:3px;margin:2px;word-break:break-all;overflow-wrap:break-word;'
                f'display:inline-block;max-width:100%;">{f}</code>'
                for f in files
            )
            files_html = f'<div style="margin-top:6px">{file_tags}</div>'
        delta = n.get("delta", "")
        delta_color = "#2e7d32" if delta.startswith("+") else "#c62828"
        cards.append(f"""
        <div class="ms-card" style="flex:1;min-width:170px;background:#fff;
          border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,0.08);padding:16px;
          border-top:4px solid {badge_color};position:relative;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
            <span style="background:{badge_color};color:#fff;font-size:11px;
              padding:2px 8px;border-radius:10px;white-space:nowrap;">{badge}</span>
            {f'<span style="font-weight:700;font-size:17px;color:{delta_color};">{delta}</span>' if delta else ''}
          </div>
          <div style="font-size:14px;font-weight:600;color:#1a1a1a;margin-bottom:8px;">
            {n.get('label', '')}</div>
          <ul style="font-size:12px;color:#555;padding-left:16px;line-height:1.7;margin:0;">
            {changes_html}</ul>
          {files_html}
          <div style="margin-top:8px;font-size:12px;color:#2e7d32;font-weight:500;">
            {n.get('effect', '')}</div>
        </div>""")
    return "".join(cards)


def build_html(reports):
    """Generate self-contained HTML dashboard with ECharts."""
    times = [r["time"] for r in reports]
    notes_list = [r["note"] for r in reports]

    track_acc = [r["track_accuracy"] for r in reports]
    intent_f1 = [r["intent_f1"] for r in reports]
    slot_f1 = [r["slot_f1"] for r in reports]
    clarify_rate = [r["clarify_rate"] for r in reports]
    err_counts = [r["errors"] for r in reports]

    cat_names = ["routing", "slot_filling", "knowledge", "flow_completion",
                 "anti_interference", "edge_case", "clarify"]
    cat_labels = ["路由", "槽位填充", "知识查询",
                  "流程完成", "反干扰", "边界情况",
                  "澄清触发"]
    cat_series = []
    for i, r in enumerate(reports):
        cats = r["categories"]
        cat_series.append({
            "name": notes_list[i].get("label", f"第{i+1}轮"),
            "data": [cats.get(c, 0) for c in cat_names],
        })

    # Build markPoint annotations for track accuracy line
    markpoint_data = []
    for i, r in enumerate(reports):
        note = notes_list[i]
        delta = note.get("delta", "")
        badge = note.get("badge", "")
        if delta:
            markpoint_data.append({
                "name": badge,
                "coord": [i, r["track_accuracy"]],
                "value": f"{badge} {delta}",
                "symbol": "pin",
                "symbolSize": 50,
                "itemStyle": {"color": BADGE_COLORS.get(badge, "#1a73e8")},
                "label": {
                    "show": True,
                    "position": "top",
                    "distance": 8,
                    "formatter": f"{badge} {delta}",
                    "fontSize": 10,
                    "fontWeight": "bold",
                    "color": BADGE_COLORS.get(badge, "#333"),
                },
            })

    milestone_html = _build_milestone_cards(notes_list)
    total_rounds = len(reports)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>智能客服质量评估仪表盘</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; background: #f0f2f5; color: #333; }}
.header {{ background: linear-gradient(135deg, #1a73e8, #0d47a1); color: #fff; padding: 28px 40px; text-align: center; }}
.header h1 {{ font-size: 26px; font-weight: 600; margin-bottom: 6px; }}
.header p {{ font-size: 14px; opacity: 0.85; }}
.container {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}
.row {{ display: flex; gap: 20px; margin-bottom: 20px; flex-wrap: wrap; }}
.card {{ background: #fff; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); padding: 20px; flex: 1; min-width: 400px; }}
.card.full {{ flex: 1 1 100%; min-width: 0; }}
.card h3 {{ font-size: 16px; font-weight: 600; margin-bottom: 14px; color: #1a1a1a; border-left: 3px solid #1a73e8; padding-left: 10px; }}
.chart {{ width: 100%; height: 450px; }}

.summary-cards {{ display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }}
.summary-card {{ background: #fff; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); padding: 18px 22px; flex: 1; min-width: 160px; text-align: center; }}
.summary-card .value {{ font-size: 32px; font-weight: 700; }}
.summary-card .label {{ font-size: 13px; color: #666; margin-top: 4px; }}
.summary-card .delta {{ font-size: 13px; margin-top: 2px; }}
.delta-up {{ color: #2e7d32; }}
.delta-down {{ color: #c62828; }}

.milestone-row {{ display: flex; gap: 12px; margin-bottom: 20px; overflow-x: auto; padding-bottom: 8px; }}
.milestone-row::-webkit-scrollbar {{ height: 6px; }}
.milestone-row::-webkit-scrollbar-thumb {{ background: #ccc; border-radius: 3px; }}
.ms-card {{ transition: transform 0.15s, box-shadow 0.15s; }}
.ms-card:hover {{ transform: translateY(-2px); box-shadow: 0 6px 16px rgba(0,0,0,0.12) !important; }}
</style>
</head>
<body>

<div class="header">
  <h1>智能客服质量评估仪表盘</h1>
  <p>{total_rounds} 轮离线评估 · 200 条黄金用例 · 254 轮对话 · 轨道准确率 {track_acc[0]*100:.1f}% → {track_acc[-1]*100:.1f}%</p>
</div>

<div class="container">

  <div class="summary-cards" id="summaryCards"></div>

  <div class="card full" style="margin-bottom:20px;">
    <h3>优化历程 · 每轮改动一览</h3>
    <div class="milestone-row">{milestone_html}</div>
  </div>

  <div class="row">
    <div class="card">
      <h3>核心指标趋势（标注关键改动）</h3>
      <div class="chart" id="chartCore"></div>
    </div>
    <div class="card">
      <h3>各类别准确率变化</h3>
      <div class="chart" id="chartCategory"></div>
    </div>
  </div>

  <div class="row">
    <div class="card">
      <h3>500 错误数下降</h3>
      <div class="chart" id="chartErrors"></div>
    </div>
    <div class="card">
      <h3>准确率增益（每轮净提升）</h3>
      <div class="chart" id="chartGain"></div>
    </div>
  </div>

</div>

<script>
var times = {json.dumps(times, ensure_ascii=False)};
var markpointData = {json.dumps(markpoint_data, ensure_ascii=False)};
var notesList = {json.dumps([n.get("changes", []) for n in notes_list], ensure_ascii=False)};
var effectsList = {json.dumps([n.get("effect", "") for n in notes_list], ensure_ascii=False)};

// ========== Summary cards ==========
(function() {{
  var first = {track_acc[0]:.4f}, last = {track_acc[-1]:.4f};
  var deltaAcc = ((last - first) * 100).toFixed(1);
  var firstErr = {err_counts[0]}, lastErr = {err_counts[-1]};
  var container = document.getElementById('summaryCards');

  var cards = [
    {{ label: '起始准确率', value: (first * 100).toFixed(1) + '%', delta: '', color: '#c62828' }},
    {{ label: '最终准确率', value: (last * 100).toFixed(1) + '%', delta: '+' + deltaAcc + '%', color: '#2e7d32' }},
    {{ label: '累计提升', value: '+' + deltaAcc + '%', delta: (first * 100).toFixed(1) + '% → ' + (last * 100).toFixed(1) + '%', color: '#1a73e8' }},
    {{ label: '槽位提取 F1', value: ({slot_f1[-1]:.4f} * 100).toFixed(1) + '%', delta: '+' + (({slot_f1[-1]} - {slot_f1[0]}) * 100).toFixed(1) + '%', color: '#1a73e8' }},
    {{ label: '500 错误', value: lastErr, delta: firstErr + ' → ' + lastErr, color: lastErr === 0 ? '#2e7d32' : '#c62828' }},
    {{ label: '反干扰', value: ({reports[-1]["categories"]["anti_interference"]:.4f} * 100).toFixed(1) + '%', delta: '+' + (({reports[-1]["categories"]["anti_interference"]} - {reports[0]["categories"]["anti_interference"]}) * 100).toFixed(1) + '%', color: '#1a73e8' }},
  ];

  container.innerHTML = cards.map(function(c) {{
    return '<div class="summary-card"><div class="value" style="color:' + c.color + '">' + c.value + '</div><div class="label">' + c.label + '</div>' + (c.delta ? '<div class="delta delta-up">' + c.delta + '</div>' : '') + '</div>';
  }}).join('');
}})();

// ========== Chart 1: Core metrics trend (dual Y-axis + markPoint) ==========
(function() {{
  var chart = echarts.init(document.getElementById('chartCore'));
  chart.setOption({{
    tooltip: {{
      trigger: 'axis',
      formatter: function(ps) {{
        var html = '<b>' + times[ps[0].dataIndex] + '</b><br/>';
        ps.forEach(function(p) {{
          html += p.marker + ' ' + p.seriesName + ': <b>' + (p.value * 100).toFixed(1) + '%</b><br/>';
        }});
        var changes = notesList[ps[0].dataIndex];
        if (changes && changes.length > 0) {{
          html += '<br/><span style="color:#1a73e8;font-size:12px;">改动：</span><br/>';
          changes.forEach(function(c) {{ html += '<span style="font-size:11px;color:#666;">· ' + c + '</span><br/>'; }});
        }}
        var effect = effectsList[ps[0].dataIndex];
        if (effect) html += '<br/><span style="color:#2e7d32;font-weight:500;">' + effect + '</span>';
        return html;
      }}
    }},
    legend: {{ data: ['轨道准确率', '槽位提取 F1', '意图识别 F1', '澄清率'], bottom: 0 }},
    grid: {{ left: 48, right: 48, top: 50, bottom: 42 }},
    xAxis: {{ type: 'category', data: times, axisLabel: {{ rotate: 30, fontSize: 11 }} }},
    yAxis: [
      {{ type: 'value', min: 0, max: 1.05, axisLabel: {{ formatter: function(v){{return (v*100).toFixed(0)+'%'}} }}, splitLine: {{ lineStyle: {{ type: 'dashed' }} }} }},
      {{ type: 'value', min: 0, max: 1.05, axisLabel: {{ formatter: function(v){{return (v*100).toFixed(0)+'%'}} }} }},
    ],
    series: [
      {{
        name: '轨道准确率', type: 'line', data: {json.dumps(track_acc)}, smooth: true,
        lineStyle: {{ width: 3, color: '#2e7d32' }}, itemStyle: {{ color: '#2e7d32' }},
        symbol: 'circle', symbolSize: 9,
        markPoint: {{ data: markpointData, animation: true }},
        markLine: {{
          silent: true, symbol: 'none',
          data: [
            {{ yAxis: 0.9, label: {{ formatter: '优秀线 90%', fontSize: 11 }}, lineStyle: {{ color: '#bdbdbd', type: 'dashed', width: 1 }} }},
            {{ yAxis: 0.95, label: {{ formatter: '卓越线 95%', fontSize: 11 }}, lineStyle: {{ color: '#81c784', type: 'dashed', width: 1 }} }},
          ]
        }},
        markArea: {{
          silent: true,
          data: [
            [{{ xAxis: times[1], itemStyle: {{ color: 'rgba(26,115,232,0.05)' }}, label: {{ show: true, position: 'insideTop', formatter: '测试修正\\n+Prompt', fontSize: 10, color: '#1a73e8' }} }}, {{ xAxis: times[2] }}],
            [{{ xAxis: times[2], itemStyle: {{ color: 'rgba(230,81,0,0.05)' }}, label: {{ show: true, position: 'insideTop', formatter: '预过滤器\\n+重试机制', fontSize: 10, color: '#e65100' }} }}, {{ xAxis: times[3] }}],
            [{{ xAxis: times[3], itemStyle: {{ color: 'rgba(26,115,232,0.05)' }}, label: {{ show: true, position: 'insideTop', formatter: '边界语义\\nPrompt', fontSize: 10, color: '#1a73e8' }} }}, {{ xAxis: times[4] }}],
          ]
        }},
      }},
      {{ name: '槽位提取 F1', type: 'line', data: {json.dumps(slot_f1)}, smooth: true,
         lineStyle: {{ width: 2.5, color: '#1a73e8' }}, itemStyle: {{ color: '#1a73e8' }},
         symbol: 'diamond', symbolSize: 7 }},
      {{ name: '意图识别 F1', type: 'line', yAxisIndex: 1, data: {json.dumps(intent_f1)}, smooth: true,
         lineStyle: {{ width: 2, color: '#e65100', type: 'dashed' }}, itemStyle: {{ color: '#e65100' }},
         symbol: 'triangle', symbolSize: 7 }},
      {{ name: '澄清率', type: 'line', yAxisIndex: 1, data: {json.dumps(clarify_rate)}, smooth: true,
         lineStyle: {{ width: 2, color: '#7b1fa2', type: 'dashed' }}, itemStyle: {{ color: '#7b1fa2' }},
         symbol: 'rect', symbolSize: 6 }},
    ]
  }});
  window.addEventListener('resize', function() {{ chart.resize(); }});
}})();

// ========== Chart 2: Category accuracy grouped bar ==========
(function() {{
  var chart = echarts.init(document.getElementById('chartCategory'));
  var catLabels = {json.dumps(cat_labels, ensure_ascii=False)};
  var catData = {json.dumps(cat_series, ensure_ascii=False)};
  var colors = ['#cfd8dc', '#90a4ae', '#78909c', '#546e7a', '#455a64', '#37474f'];

  chart.setOption({{
    tooltip: {{ trigger: 'axis', formatter: function(ps) {{ return ps.map(function(p){{return p.marker+' '+p.seriesName+': <b>'+(p.value*100).toFixed(1)+'%</b>'}}).join('<br>'); }} }},
    legend: {{ data: catData.map(function(d){{return d.name}}), bottom: 0, type: 'scroll', textStyle: {{ fontSize: 11 }} }},
    grid: {{ left: 40, right: 20, top: 16, bottom: 50 }},
    xAxis: {{ type: 'category', data: catLabels, axisLabel: {{ rotate: 30, fontSize: 11 }} }},
    yAxis: {{ type: 'value', min: 0, max: 1, axisLabel: {{ formatter: function(v){{return (v*100).toFixed(0)+'%'}} }}, splitLine: {{ lineStyle: {{ type: 'dashed' }} }} }},
    series: catData.map(function(d, i) {{
      return {{ name: d.name, type: 'bar', data: d.data, barGap: '10%',
        itemStyle: {{ color: colors[i] || '#607d8b', borderRadius: [3, 3, 0, 0] }},
        label: {{ show: true, position: 'top', formatter: function(p){{return p.value>0?(p.value*100).toFixed(0)+'%':''}}, fontSize: 10 }}
      }};
    }})
  }});
  window.addEventListener('resize', function() {{ chart.resize(); }});
}})();

// ========== Chart 3: Server error count ==========
(function() {{
  var chart = echarts.init(document.getElementById('chartErrors'));
  var errData = {json.dumps(err_counts)};
  var maxErr = Math.max.apply(null, errData) + 5;

  chart.setOption({{
    tooltip: {{
      trigger: 'axis',
      formatter: function(ps) {{
        var idx = ps[0].dataIndex;
        if (errData[idx] === 0) return '<b>' + times[idx] + '</b><br/>500 错误: <b style="color:#2e7d32">0</b> (已消除)';
        return '<b>' + times[idx] + '</b><br/>500 错误: <b style="color:#c62828">' + errData[idx] + '</b>';
      }}
    }},
    grid: {{ left: 44, right: 20, top: 30, bottom: 30 }},
    xAxis: {{ type: 'category', data: times }},
    yAxis: {{ type: 'value', min: 0, max: maxErr, interval: Math.ceil(maxErr/5), name: '错误数' }},
    series: [
      {{
        name: 'API 错误数', type: 'bar', data: errData,
        itemStyle: {{
          color: function(p) {{ return p.value === 0 ? '#2e7d32' : p.value < 20 ? '#f9a825' : '#c62828'; }},
          borderRadius: [4, 4, 0, 0]
        }},
        label: {{ show: true, position: 'top', fontSize: 14, fontWeight: 'bold',
          color: function(p) {{ return p.value === 0 ? '#2e7d32' : '#c62828'; }}
        }},
        markLine: {{
          silent: true, symbol: 'none', label: {{ fontSize: 11 }},
          data: [
            {{ xAxis: times[2], label: {{ formatter: 'LLM 3次重试\\n引擎 fallback 兖底' }}, lineStyle: {{ color: '#1a73e8', type: 'dashed' }} }},
          ]
        }},
        markArea: {{
          silent: true,
          data: [
            [{{ xAxis: times[2], itemStyle: {{ color: 'rgba(46,125,50,0.08)' }}, label: {{ show: true, position: 'insideTop', formatter: '✅ 零错误', fontSize: 11, color: '#2e7d32' }} }}, {{ xAxis: times[times.length-1] }}],
          ]
        }}
      }}
    ]
  }});
  window.addEventListener('resize', function() {{ chart.resize(); }});
}})();

// ========== Chart 4: Accuracy gain per round (waterfall) ==========
(function() {{
  var chart = echarts.init(document.getElementById('chartGain'));
  var accData = {json.dumps(track_acc)};
  var deltas = [0];
  for (var i = 1; i < accData.length; i++) {{
    deltas.push(accData[i] - accData[i-1]);
  }}

  chart.setOption({{
    tooltip: {{
      trigger: 'axis',
      formatter: function(ps) {{
        var idx = ps[0].dataIndex;
        var changes = notesList[idx];
        var html = '<b>' + times[idx] + '</b><br/>准确率: ' + (accData[idx]*100).toFixed(2) + '%<br/>本轮提升: <b style="color:#2e7d32">' + (deltas[idx]*100).toFixed(2) + '%</b>';
        if (changes && changes.length > 0) {{
          html += '<br/><br/><span style="color:#1a73e8;">改动：</span>';
          changes.forEach(function(c) {{ html += '<br/>· ' + c; }});
        }}
        return html;
      }}
    }},
    grid: {{ left: 44, right: 20, top: 30, bottom: 30 }},
    xAxis: {{ type: 'category', data: times, axisLabel: {{ rotate: 30, fontSize: 11 }} }},
    yAxis: {{ type: 'value', name: '净提升 (%)', axisLabel: {{ formatter: function(v){{return (v*100).toFixed(1)+'%'}} }} }},
    series: [
      {{
        name: '净提升', type: 'bar', data: deltas,
        itemStyle: {{
          color: function(p) {{
            if (p.dataIndex === 0) return '#9e9e9e';
            return p.value > 0.01 ? '#2e7d32' : p.value > 0 ? '#66bb6a' : '#c62828';
          }},
          borderRadius: [4, 4, 0, 0]
        }},
        label: {{
          show: true, position: 'top', fontSize: 13, fontWeight: 'bold',
          formatter: function(p) {{ return p.dataIndex === 0 ? '基线' : ((p.value > 0 ? '+' : '') + (p.value*100).toFixed(2) + '%'); }},
          color: function(p) {{ return p.dataIndex === 0 ? '#9e9e9e' : '#2e7d32'; }}
        }},
        markLine: {{
          silent: true, symbol: 'none',
          data: [{{ yAxis: 0, lineStyle: {{ color: '#9e9e9e', type: 'solid' }} }}]
        }}
      }}
    ]
  }});
  window.addEventListener('resize', function() {{ chart.resize(); }});
}})();
</script>
</body>
</html>"""

    return html


def main():
    reports = load_reports()
    if not reports:
        print("No evaluation report JSON files found")
        return

    html = build_html(reports)
    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Dashboard generated: {OUTPUT_HTML}")
    print(f"Reports: {len(reports)}, Track accuracy: {reports[0]['track_accuracy']:.2%} -> {reports[-1]['track_accuracy']:.2%}")


if __name__ == "__main__":
    main()
