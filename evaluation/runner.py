"""离线评估运行器 —— 遍历 200 条黄金用例，调用 API，计算指标，输出报告"""

import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

from evaluation.test_cases import ALL_TEST_CASES, TEST_CASES_BY_CATEGORY, GoldenTestCase
from evaluation.metrics import (
    compute_track_accuracy,
    compute_intent_metrics,
    compute_slot_f1,
    compute_flow_completion_rate,
    compute_clarify_rate,
    compute_category_breakdown,
)

API_BASE = "http://localhost:18082"
CHAT_URL = f"{API_BASE}/api/chat"
EVAL_DIR = Path(__file__).parent
REPORTS_DIR = EVAL_DIR / "reports"


async def send_message(session: httpx.AsyncClient, sender_id: int, text: str) -> dict:
    """发送一条消息并返回完整响应 JSON"""
    resp = await session.post(CHAT_URL, json={
        "sender_id": str(sender_id),
        "text": text,
    }, timeout=120.0)
    resp.raise_for_status()
    return resp.json()


async def evaluate_all(cases: list[GoldenTestCase]) -> dict:
    """运行全部评估用例"""
    async with httpx.AsyncClient(timeout=120.0, trust_env=False) as session:
        # 每次评估前初始化新会话（通过不同 user_id 后缀）
        # 收集所有 turn 的预测和期望
        track_predictions: list[str] = []
        track_expected: list[str] = []
        intent_predictions: list[str | None] = []
        intent_expected: list[str | None] = []
        slot_predictions: list[dict | None] = []
        slot_expected: list[dict | None] = []
        flow_starts: dict[str, int] = {}
        flow_completions: dict[str, int] = {}
        clarify_count = 0
        total_turns = 0

        results: list[dict] = []
        errors: list[dict] = []

        for case_idx, case in enumerate(cases):
            # 每个 case 使用独立的 user_id，避免会话污染
            user_id = 10000 + case_idx
            case_result = {
                "id": case.id,
                "category": case.category,
                "description": case.description,
                "turns": [],
            }

            for turn_idx, turn in enumerate(case.turns):
                total_turns += 1
                try:
                    resp = await send_message(session, user_id, turn.user_input)
                except Exception as e:
                    errors.append({
                        "case_id": case.id,
                        "turn_idx": turn_idx,
                        "user_input": turn.user_input[:50],
                        "error": str(e),
                    })
                    continue

                diag = resp.get("diagnostics") or {}
                predicted_track = _resolve_track_from_diagnostics(diag)

                track_predictions.append(predicted_track)
                track_expected.append(turn.expected_track)

                if turn.expected_intent is not None:
                    predicted_intents = diag.get("knowledge_intents") or []
                    predicted_intent = predicted_intents[0] if predicted_intents else None
                    intent_predictions.append(predicted_intent)
                    intent_expected.append(turn.expected_intent)

                if turn.expected_slots is not None:
                    predicted_slots = diag.get("slots_filled") or {}
                    slot_predictions.append(predicted_slots)
                    slot_expected.append(turn.expected_slots)

                if predicted_track == "clarify":
                    clarify_count += 1

                case_result["turns"].append({
                    "user_input": turn.user_input[:60],
                    "predicted_track": predicted_track,
                    "expected_track": turn.expected_track,
                    "correct": predicted_track == turn.expected_track,
                    "diagnostics": diag,
                })

                print(f"  [{case.id}] turn {turn_idx}: pred={predicted_track}, exp={turn.expected_track}, "
                      f"{'✓' if predicted_track == turn.expected_track else '✗'} "
                      f"\"{turn.user_input[:40]}\"")

            results.append(case_result)

        # ---- 计算各维度指标 ----
        track_metrics = compute_track_accuracy(track_predictions, track_expected)
        intent_metrics = compute_intent_metrics(intent_predictions, intent_expected)
        slot_metrics = compute_slot_f1(slot_predictions, slot_expected)
        clarify_metrics = compute_clarify_rate(clarify_count, total_turns)
        category_breakdown = compute_category_breakdown(cases, track_predictions)

        return {
            "summary": {
                "total_cases": len(cases),
                "total_turns": total_turns,
                "errors": len(errors),
                "track_accuracy": track_metrics,
                "intent_accuracy": intent_metrics,
                "slot_f1": slot_metrics,
                "clarify_rate": clarify_metrics,
                "category_breakdown": category_breakdown,
            },
            "detail": results,
            "errors": errors,
        }


def _resolve_track_from_diagnostics(diag: dict) -> str:
    """从诊断信息中解析预测轨道"""
    tracks = diag.get("predicted_tracks") or diag.get("track", [])
    if isinstance(tracks, str):
        tracks = [tracks]
    if not diag.get("validation_passed", True):
        return "clarify"
    if tracks:
        return tracks[0]
    return "chitchat"


def print_summary(report: dict):
    """打印摘要到终端"""
    s = report["summary"]
    print("\n" + "=" * 60)
    print("  评估摘要")
    print("=" * 60)
    print(f"  总用例数: {s['total_cases']}  |  总轮次: {s['total_turns']}  |  错误: {s['errors']}")
    print(f"  轨道准确率: {s['track_accuracy']['value']:.2%}  ({s['track_accuracy']['correct']}/{s['track_accuracy']['total']})")
    print(f"  意图 F1:    {s['intent_accuracy']['f1']:.2%}")
    print(f"  槽位 F1:    {s['slot_f1']['f1']:.2%}")
    print(f"  澄清率:     {s['clarify_rate']['value']:.2%}")
    print("-" * 60)
    print("  各类别准确率:")
    for cat, data in s["category_breakdown"].items():
        bar = "█" * int(data["accuracy"] * 20)
        print(f"    {cat:<20s}: {data['accuracy']:.2%} {bar}")
    print("=" * 60)


def generate_markdown_report(report: dict) -> str:
    """生成 Markdown 格式报告"""
    s = report["summary"]
    lines = [
        "# 智能客服质量评估报告",
        "",
        f"**评估时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**总用例数**: {s['total_cases']}  |  **总轮次**: {s['total_turns']}  |  **错误**: {s['errors']}",
        "",
        "## 核心指标",
        "",
        f"| 指标 | 数值 | 评级 |",
        f"|------|------|------|",
        f"| 轨道准确率 | {s['track_accuracy']['value']:.2%} | {_grade(s['track_accuracy']['value'], 0.90, 0.80)} |",
        f"| 意图识别 F1 | {s['intent_accuracy']['f1']:.2%} | {_grade(s['intent_accuracy']['f1'], 0.85, 0.70)} |",
        f"| 槽位提取 F1 | {s['slot_f1']['f1']:.2%} | {_grade(s['slot_f1']['f1'], 0.85, 0.70)} |",
        f"| 澄清率 | {s['clarify_rate']['value']:.2%} | {_clarify_grade(s['clarify_rate']['value'])} |",
        "",
        "## 各类别准确率",
        "",
        "| 类别 | 准确率 | 正确/总数 |",
        "|------|--------|----------|",
    ]
    for cat, data in s["category_breakdown"].items():
        lines.append(f"| {cat} | {data['accuracy']:.2%} | {data['correct']}/{data['total']} |")

    # 轨道错误详情
    track_errors = s["track_accuracy"].get("errors", [])
    if track_errors:
        lines.append("")
        lines.append("## 轨道判断错误（Top 20）")
        lines.append("")
        lines.append("| # | 预测 | 期望 | 用户输入 |")
        lines.append("|---|---|---|---|")
        for err in track_errors[:20]:
            case_id = report["detail"][err["idx"]] if err["idx"] < len(report["detail"]) else {"turns": []}
            turns = case_id.get("turns", [{}])
            turn_err = turns[0] if turns else {}
            ui = turn_err.get("user_input", "?") if isinstance(turn_err, dict) else "?"
            lines.append(f"| {err['idx']} | {err['predicted']} | {err['expected']} | {ui[:50]} |")

    return "\n".join(lines)


def _grade(value: float, a_threshold: float, b_threshold: float) -> str:
    if value >= a_threshold:
        return "A 🟢"
    elif value >= b_threshold:
        return "B 🟡"
    else:
        return "C 🔴"


def _clarify_grade(rate: float) -> str:
    if rate <= 0.08:
        return "A 🟢"
    elif rate <= 0.15:
        return "B 🟡"
    else:
        return "C 🔴"


async def main():
    print(f"开始评估: {len(ALL_TEST_CASES)} 个用例, 共 {sum(len(c.turns) for c in ALL_TEST_CASES)} 轮")
    print(f"API 地址: {CHAT_URL}")
    print("-" * 60)

    # 先检查 API 是否可用
    try:
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            resp = await client.get(f"{API_BASE}/hello")
            resp.raise_for_status()
            print("✓ API 服务可用")
    except Exception as e:
        print(f"✗ API 服务不可用: {e}")
        print("请先启动服务: uv run python -m audio_cs.main")
        sys.exit(1)

    report = await evaluate_all(ALL_TEST_CASES)

    print_summary(report)

    # 输出报告文件
    REPORTS_DIR.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")

    md_path = REPORTS_DIR / f"evaluation_{ts}.md"
    md_path.write_text(generate_markdown_report(report), encoding="utf-8")
    print(f"\nMarkdown 报告: {md_path}")

    json_path = REPORTS_DIR / f"evaluation_{ts}.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"JSON 报告:   {json_path}")


if __name__ == "__main__":
    asyncio.run(main())
