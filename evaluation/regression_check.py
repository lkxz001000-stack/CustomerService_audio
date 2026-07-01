"""回归检查 —— 与基线对比，任一指标下降 > 5% 时退出码 1"""

import json
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).parent
REPORTS_DIR = EVAL_DIR / "reports"
BASELINE_PATH = EVAL_DIR / "baseline.json"

# 关键指标列表（路径：summary.<key>.<subkey>）
CHECK_METRICS = [
    ("track_accuracy", "value"),
    ("intent_accuracy", "f1"),
    ("slot_f1", "f1"),
]


def load_baseline() -> dict | None:
    if not BASELINE_PATH.exists():
        return None
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def save_baseline(report: dict):
    baseline = {
        "date": report.get("date", ""),
        "model": report.get("model", "unknown"),
        "metrics": {
            "track_accuracy": report["summary"]["track_accuracy"]["value"],
            "intent_f1": report["summary"]["intent_accuracy"]["f1"],
            "slot_f1": report["summary"]["slot_f1"]["f1"],
        },
    }
    BASELINE_PATH.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"基线已保存: {BASELINE_PATH}")


def check_regression(report: dict):
    """检查是否退化"""
    baseline = load_baseline()
    if baseline is None:
        print("无基线数据，将当前评估结果保存为基线")
        save_baseline(report)
        return True

    bm = baseline["metrics"]
    sm = report["summary"]
    regressions = []

    for key, subkey in CHECK_METRICS:
        current = sm[key][subkey]
        previous = bm.get(key, bm.get(f"{key}_{subkey}", 0))
        if previous == 0:
            continue
        delta = (current - previous) / previous
        status = "✓" if delta >= -0.05 else "✗ REGRESSION"
        print(f"  {key}.{subkey}: {previous:.4f} → {current:.4f} ({delta:+.2%}) {status}")
        if delta < -0.05:
            regressions.append((key, subkey, previous, current, delta))

    if regressions:
        print(f"\n⚠ 检测到 {len(regressions)} 个指标退化超过 5%:")
        for key, subkey, prev, cur, delta in regressions:
            print(f"  - {key}.{subkey}: {prev:.4f} → {cur:.4f} ({delta:.1%})")
        return False

    print("\n✓ 所有指标稳定（变化 < 5%）")
    return True


def main():
    # 寻找最新的评估报告
    if not REPORTS_DIR.exists():
        print("无评估报告目录")
        sys.exit(1)

    json_files = sorted(REPORTS_DIR.glob("evaluation_*.json"), reverse=True)
    if not json_files:
        print("无评估报告文件，请先运行 runner.py")
        sys.exit(1)

    latest = json.loads(json_files[0].read_text(encoding="utf-8"))
    report = {
        "date": json_files[0].stem,
        "model": "qwen-plus",
        "summary": latest["summary"],
    }

    print(f"回归检查: 对比基线 {BASELINE_PATH} vs {json_files[0].name}")
    print("-" * 50)

    ok = check_regression(report)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
