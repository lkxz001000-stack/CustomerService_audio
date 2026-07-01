"""LLM-as-Judge 抽样评估 —— 三维度评分（相关性/忠实度/完整性）"""

import asyncio
import json
import logging
import random
import time
from pathlib import Path

import httpx
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

from audio_cs.infrastructure.llm_client import llm_client

logger = logging.getLogger(__name__)

EVAL_DIR = Path(__file__).parent
PROMPTS_DIR = EVAL_DIR / "prompts"
REPORTS_DIR = EVAL_DIR / "reports"

API_BASE = "http://localhost:18082"
CHAT_URL = f"{API_BASE}/api/chat"


def _load_template(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.jinja2"
    if path.exists():
        return path.read_text(encoding="utf-8")
    # 退一步：从 audio_cs/prompts 加载（兼容）
    alt_path = Path("audio_cs/prompts/jinja2") / f"{name}.jinja2"
    if alt_path.exists():
        return alt_path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"模板不存在: {path}")


async def _judge_dimension(template_name: str, **kwargs) -> int:
    """调用 LLM 对单个维度评分（1-5）"""
    template_str = _load_template(template_name)
    prompt = PromptTemplate.from_template(template=template_str, template_format="jinja2")
    chain = prompt | llm_client | StrOutputParser()

    try:
        result = await asyncio.wait_for(chain.ainvoke(kwargs), timeout=30.0)
        return int(result.strip()[0]) if result.strip() and result.strip()[0].isdigit() else 0
    except Exception as e:
        logger.warning("评分失败 [%s]: %s", template_name, e)
        return 0


async def _judge_faithfulness(bot_reply: str, knowledge_chunks: list[str]) -> dict:
    """检查回复中的幻觉（各断言是否能从知识库中找到支撑）"""
    template_str = _load_template("faithfulness")
    prompt = PromptTemplate.from_template(template=template_str, template_format="jinja2")
    chain = prompt | llm_client | StrOutputParser()

    try:
        result = await asyncio.wait_for(
            chain.ainvoke({"bot_reply": bot_reply, "knowledge_chunks": knowledge_chunks}),
            timeout=30.0,
        )
        # 尝试解析 JSON
        # 可能被 markdown ```json ... ``` 包裹
        result_clean = result.strip()
        if result_clean.startswith("```"):
            lines = result_clean.split("\n")
            result_clean = "\n".join(lines[1:-1])
        statements = json.loads(result_clean)
        total = len(statements)
        supported = sum(1 for s in statements if s.get("supported"))
        unsupported = [s for s in statements if not s.get("supported")]
        return {
            "total_statements": total,
            "supported": supported,
            "unsupported_count": total - supported,
            "faithfulness_score": round(supported / max(total, 1), 4),
            "hallucinations": [s["statement"] for s in unsupported],
            "detail": statements,
        }
    except Exception as e:
        logger.warning("忠实度检测失败: %s", e)
        return {
            "total_statements": 0,
            "supported": 0,
            "unsupported_count": 0,
            "faithfulness_score": 0,
            "hallucinations": [],
            "error": str(e),
        }


async def evaluate_sample(samples: list[dict]) -> dict:
    """对抽样对话进行三维度评估"""
    results = []
    relevance_scores = []
    completeness_scores = []
    faithfulness_scores = []
    hallucination_count = 0

    for i, sample in enumerate(samples):
        user_msg = sample.get("user_message", "")
        bot_reply = sample.get("bot_reply", "")
        chunks = sample.get("knowledge_chunks", [])

        print(f"  抽样评估 [{i+1}/{len(samples)}]: \"{user_msg[:50]}\"")

        relevance = await _judge_dimension("relevance", user_message=user_msg, bot_reply=bot_reply)
        completeness = await _judge_dimension("completeness", user_message=user_msg, bot_reply=bot_reply)

        faith_result = {"faithfulness_score": 0, "hallucinations": []}
        if chunks:
            faith_result = await _judge_faithfulness(bot_reply, chunks)

        relevance_scores.append(relevance)
        completeness_scores.append(completeness)
        faithfulness_scores.append(faith_result["faithfulness_score"])
        hallucination_count += faith_result.get("unsupported_count", 0)

        results.append({
            "user_message": user_msg,
            "bot_reply": bot_reply[:200],
            "relevance": relevance,
            "completeness": completeness,
            "faithfulness": faith_result,
        })

    n = max(len(results), 1)
    return {
        "sample_count": n,
        "avg_relevance": round(sum(relevance_scores) / n, 2),
        "avg_completeness": round(sum(completeness_scores) / n, 2),
        "avg_faithfulness": round(sum(faithfulness_scores) / max(n, 1), 2),
        "total_hallucinations": hallucination_count,
        "hallucination_rate": round(hallucination_count / max(n, 1), 4),
        "details": results,
    }


def generate_markdown_report(judge_report: dict) -> str:
    """生成 LLM-as-Judge 评估报告"""
    lines = [
        "# LLM-as-Judge 抽样评估报告",
        "",
        f"**评估时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**抽样数量**: {judge_report['sample_count']}",
        "",
        "## 三维度评分",
        "",
        "| 维度 | 平均分 | 评级 |",
        "|------|--------|------|",
        f"| 相关性 | {judge_report['avg_relevance']:.1f}/5 | {_score_grade(judge_report['avg_relevance'])} |",
        f"| 完整性 | {judge_report['avg_completeness']:.1f}/5 | {_score_grade(judge_report['avg_completeness'])} |",
        f"| 忠实度 | {judge_report['avg_faithfulness']:.1f}/5 | {_score_grade(judge_report['avg_faithfulness'])} |",
        "",
        f"**幻觉检测**: 共 {judge_report['total_hallucinations']} 处幻觉, "
        f"幻觉率 {judge_report['hallucination_rate']:.2%}",
        "",
    ]

    # 列出有幻觉的样本
    for d in judge_report.get("details", []):
        faith = d.get("faithfulness", {})
        if faith.get("hallucinations"):
            lines.append(f"### 幻觉样本: \"{d['user_message'][:60]}\"")
            for h in faith["hallucinations"]:
                lines.append(f"- ❌ {h}")
            lines.append("")

    return "\n".join(lines)


def _score_grade(score: float) -> str:
    if score >= 4.0:
        return "A 🟢"
    elif score >= 3.0:
        return "B 🟡"
    else:
        return "C 🔴"


def load_sample_logs(log_dir: str = "", n: int = 20) -> list[dict]:
    """从日志文件中加载抽样对话（简化版：返回空列表，实际从 API 获取）"""
    # 实际使用时，可从生产日志或测试运行中获取
    # 这里提供一个接口定义
    return []


async def main():
    print("LLM-as-Judge 抽样评估")
    print("=" * 60)

    # 检查 API
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(f"{API_BASE}/hello")
            resp.raise_for_status()
            print("✓ API 服务可用")
        except Exception as e:
            print(f"✗ API 服务不可用: {e}")
            return

    # 从日志目录加载最近评估结果作为抽样数据
    # 实际使用时建议从生产日志流中抽取
    if not REPORTS_DIR.exists():
        print("无评估报告目录，跳过抽样评估")
        return

    json_files = sorted(REPORTS_DIR.glob("evaluation_*.json"), reverse=True)
    if not json_files:
        print("无历史评估数据，跳过抽样评估")
        return

    latest = json.loads(json_files[0].read_text(encoding="utf-8"))
    details = latest.get("detail", [])

    # 随机抽样 20 条
    samples = []
    for case in details:
        for turn in case.get("turns", []):
            if turn.get("diagnostics") and turn["diagnostics"].get("knowledge_intents"):
                samples.append({
                    "user_message": turn.get("user_input", ""),
                    "bot_reply": "（需从完整响应获取）",
                    "knowledge_chunks": [],
                })
    if len(samples) > 20:
        samples = random.sample(samples, 20)

    if not samples:
        print("无可抽样的 knowledge 轨道对话")
        return

    judge_report = await evaluate_sample(samples)

    ts = time.strftime("%Y%m%d_%H%M%S")
    md_path = REPORTS_DIR / f"judge_{ts}.md"
    md_path.write_text(generate_markdown_report(judge_report), encoding="utf-8")
    print(f"\n报告: {md_path}")

    json_path = REPORTS_DIR / f"judge_{ts}.json"
    json_path.write_text(json.dumps(judge_report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON:  {json_path}")


if __name__ == "__main__":
    asyncio.run(main())
