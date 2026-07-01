"""在线指标收集器 —— 内存计数 + HTTP 端点暴露"""

import time
import asyncio
from collections import defaultdict


class Telemetry:
    """线程安全（asyncio 单线程）的在线指标收集器"""

    def __init__(self):
        self._lock = asyncio.Lock()

        # 轨道分布
        self.track_distribution: dict[str, int] = defaultdict(int)

        # 澄清计数
        self.clarify_count: int = 0

        # 总请求数
        self.total_requests: int = 0

        # 延迟（最近 1000 条）
        self.latencies: list[float] = []

        # 流程启动/完成
        self.flow_starts: dict[str, int] = defaultdict(int)
        self.flow_completions: dict[str, int] = defaultdict(int)

        # 槽位提取记录
        self.slot_extractions: int = 0
        self.slot_successes: int = 0

    async def record_track(self, track: str):
        async with self._lock:
            self.track_distribution[track] += 1

    async def record_clarify(self):
        async with self._lock:
            self.clarify_count += 1

    async def record_request(self, latency: float):
        async with self._lock:
            self.total_requests += 1
            self.latencies.append(latency)
            if len(self.latencies) > 1000:
                self.latencies = self.latencies[-1000:]

    async def record_flow_start(self, flow_name: str):
        async with self._lock:
            self.flow_starts[flow_name] += 1

    async def record_flow_complete(self, flow_name: str):
        async with self._lock:
            self.flow_completions[flow_name] += 1

    async def record_slot(self, success: bool):
        async with self._lock:
            self.slot_extractions += 1
            if success:
                self.slot_successes += 1

    def _percentile(self, p: float) -> float:
        if not self.latencies:
            return 0.0
        sorted_lat = sorted(self.latencies)
        idx = int(len(sorted_lat) * p / 100)
        return sorted_lat[min(idx, len(sorted_lat) - 1)]

    async def snapshot(self) -> dict:
        async with self._lock:
            total = self.total_requests or 1
            return {
                "total_requests": self.total_requests,
                "track_distribution": {
                    k: round(v / total, 3)
                    for k, v in self.track_distribution.items()
                },
                "track_distribution_raw": dict(self.track_distribution),
                "clarify_rate": round(self.clarify_count / total, 4),
                "clarify_count": self.clarify_count,
                "latency_p50": round(self._percentile(50), 3),
                "latency_p95": round(self._percentile(95), 3),
                "latency_p99": round(self._percentile(99), 3),
                "flow_completion_rate": {
                    name: round(self.flow_completions.get(name, 0) / started, 4)
                    for name, started in self.flow_starts.items()
                    if started > 0
                },
                "flow_starts": dict(self.flow_starts),
                "flow_completions": dict(self.flow_completions),
                "slot_accuracy": round(self.slot_successes / max(self.slot_extractions, 1), 4),
                "slot_extractions": self.slot_extractions,
            }

    async def reset(self):
        async with self._lock:
            self.track_distribution.clear()
            self.clarify_count = 0
            self.total_requests = 0
            self.latencies.clear()
            self.flow_starts.clear()
            self.flow_completions.clear()
            self.slot_extractions = 0
            self.slot_successes = 0


telemetry = Telemetry()