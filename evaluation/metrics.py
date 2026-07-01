"""离线评估指标计算"""

from collections import defaultdict
from evaluation.test_cases import GoldenTestCase, GoldenTurn


def compute_track_accuracy(predictions: list[str], expected: list[str]) -> dict:
    """轨道准确率"""
    correct = sum(1 for p, e in zip(predictions, expected) if p == e)
    return {
        "metric": "track_accuracy",
        "value": round(correct / len(predictions), 4) if predictions else 0,
        "correct": correct,
        "total": len(predictions),
        "errors": [
            {"idx": i, "predicted": p, "expected": e}
            for i, (p, e) in enumerate(zip(predictions, expected)) if p != e
        ],
    }


def compute_intent_metrics(predictions: list[str | None], expected: list[str | None]) -> dict:
    """意图识别 Precision / Recall / F1（仅 knowledge 轨道）"""
    # 过滤掉 expected 为 None 的（非 knowledge 轨道用例）
    pairs = [(p, e) for p, e in zip(predictions, expected) if e is not None]
    if not pairs:
        return {"metric": "intent_accuracy", "precision": 0, "recall": 0, "f1": 0, "total": 0}

    # 按 intent 分组计算
    intent_preds: dict[str, set[int]] = defaultdict(set)
    intent_gold: dict[str, set[int]] = defaultdict(set)
    for idx, (p, e) in enumerate(pairs):
        intent_gold[e].add(idx)
        if p:
            intent_preds[p].add(idx)

    all_intents = set(intent_gold.keys()) | set(intent_preds.keys())
    if not all_intents:
        return {"metric": "intent_accuracy", "precision": 1.0, "recall": 1.0, "f1": 1.0, "total": len(pairs)}

    precisions, recalls = [], []
    for intent in all_intents:
        tp = len(intent_preds.get(intent, set()) & intent_gold.get(intent, set()))
        fp = len(intent_preds.get(intent, set()) - intent_gold.get(intent, set()))
        fn = len(intent_gold.get(intent, set()) - intent_preds.get(intent, set()))
        p = tp / (tp + fp) if (tp + fp) > 0 else 0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0
        precisions.append(p)
        recalls.append(r)

    macro_p = sum(precisions) / len(precisions)
    macro_r = sum(recalls) / len(recalls)
    macro_f1 = 2 * macro_p * macro_r / (macro_p + macro_r) if (macro_p + macro_r) > 0 else 0

    return {
        "metric": "intent_accuracy",
        "precision": round(macro_p, 4),
        "recall": round(macro_r, 4),
        "f1": round(macro_f1, 4),
        "total": len(pairs),
    }


def _fuzzy_match(predicted: str | None, expected: str) -> bool:
    """模糊匹配槽位值：包含即认为正确"""
    if not predicted:
        return False
    predicted_clean = predicted.strip("《》\"\"''（）").lower()
    expected_clean = expected.strip("《》\"\"''（）").lower()
    return expected_clean in predicted_clean or predicted_clean in expected_clean


def compute_slot_f1(predictions: list[dict | None], expected: list[dict | None]) -> dict:
    """槽位提取 F1（按槽位名计算）"""
    slot_tp: dict[str, int] = defaultdict(int)
    slot_fp: dict[str, int] = defaultdict(int)
    slot_fn: dict[str, int] = defaultdict(int)
    errors: list[dict] = []

    for idx, (pred, gold) in enumerate(zip(predictions, expected)):
        if not gold:
            continue
        for slot_name, expected_val in gold.items():
            if pred and slot_name in pred:
                if _fuzzy_match(pred[slot_name], expected_val):
                    slot_tp[slot_name] += 1
                else:
                    slot_fp[slot_name] += 1
                    slot_fn[slot_name] += 1
                    errors.append({
                        "idx": idx, "slot": slot_name,
                        "predicted": pred[slot_name], "expected": expected_val,
                    })
            else:
                slot_fn[slot_name] += 1
                errors.append({
                    "idx": idx, "slot": slot_name,
                    "predicted": None, "expected": expected_val,
                })

    all_slot_names = set(slot_tp.keys()) | set(slot_fp.keys()) | set(slot_fn.keys())
    if not all_slot_names:
        return {"metric": "slot_f1", "precision": 1.0, "recall": 1.0, "f1": 1.0, "errors": []}

    precisions, recalls = [], []
    for name in all_slot_names:
        tp = slot_tp[name]
        fp = slot_fp[name]
        fn = slot_fn[name]
        p = tp / (tp + fp) if (tp + fp) > 0 else 0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0
        precisions.append(p)
        recalls.append(r)

    macro_p = sum(precisions) / len(precisions)
    macro_r = sum(recalls) / len(recalls)
    macro_f1 = 2 * macro_p * macro_r / (macro_p + macro_r) if (macro_p + macro_r) > 0 else 0

    return {
        "metric": "slot_f1",
        "precision": round(macro_p, 4),
        "recall": round(macro_r, 4),
        "f1": round(macro_f1, 4),
        "errors": errors,
    }


def compute_flow_completion_rate(flow_starts: dict[str, int], flow_completions: dict[str, int]) -> dict:
    """流程完成率"""
    per_flow = {}
    for flow_name in flow_starts:
        started = flow_starts[flow_name]
        completed = flow_completions.get(flow_name, 0)
        per_flow[flow_name] = {
            "started": started,
            "completed": completed,
            "rate": round(completed / started, 4) if started > 0 else 0,
        }

    total_started = sum(flow_starts.values())
    total_completed = sum(flow_completions.values())
    overall_rate = round(total_completed / total_started, 4) if total_started > 0 else 0

    return {
        "metric": "flow_completion_rate",
        "overall": overall_rate,
        "total_started": total_started,
        "total_completed": total_completed,
        "per_flow": per_flow,
    }


def compute_clarify_rate(clarify_count: int, total: int) -> dict:
    """澄清率"""
    return {
        "metric": "clarify_rate",
        "value": round(clarify_count / total, 4) if total > 0 else 0,
        "clarify_count": clarify_count,
        "total": total,
    }


def compute_category_breakdown(
    cases: list[GoldenTestCase],
    predictions: list[str],
) -> dict:
    """按类别的指标细分"""
    breakdown: dict[str, dict] = {}
    idx = 0
    for case in cases:
        cat = case.category
        if cat not in breakdown:
            breakdown[cat] = {"correct": 0, "total": 0, "track_errors": []}
        for turn in case.turns:
            if idx < len(predictions):
                breakdown[cat]["total"] += 1
                if predictions[idx] == turn.expected_track:
                    breakdown[cat]["correct"] += 1
                else:
                    breakdown[cat]["track_errors"].append({
                        "user_input": turn.user_input[:40],
                        "predicted": predictions[idx],
                        "expected": turn.expected_track,
                    })
            idx += 1

    for cat, data in breakdown.items():
        data["accuracy"] = round(data["correct"] / data["total"], 4) if data["total"] > 0 else 0

    return breakdown
