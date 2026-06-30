"""
播放记录查询 Action。

从音频平台的 /api/v1/listening-progress 接口获取用户最近的
收听进度记录，格式化为人类可读的摘要文本后写入槽位。
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from audio_cs.domain.state import DialogueState
from audio_cs.task.action.base import Action, ActionResult
from audio_cs.task.action.customer.shared import fetch_playback_history
from audio_cs.task.action.customer.slot_extractor import extract_album_name

logger = logging.getLogger(__name__)

# 匹配中文书名号《》中的内容
_BOOK_NAME_PATTERN = re.compile(r"《(.+?)》")


def _parse_datetime(value: Any) -> datetime | None:
    """尝试多种格式解析日期时间字符串，统一转为 UTC 时区感知，失败返回 None。"""
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    # 尝试常见格式
    formats = [
        # ISO 8601 变体
        lambda v: datetime.fromisoformat(v.replace("Z", "+00:00")),
        lambda v: datetime.fromisoformat(v.replace("Z", "")),
        lambda v: datetime.fromisoformat(v),
        # 常见日期时间格式
        lambda v: datetime.strptime(v, "%Y-%m-%d %H:%M:%S"),
        lambda v: datetime.strptime(v, "%Y-%m-%dT%H:%M:%S"),
        lambda v: datetime.strptime(v, "%Y-%m-%d"),
    ]
    for fmt in formats:
        try:
            dt = fmt(s)
            # 统一转为 UTC 时区感知，避免与 offset-aware 的 cutoff 比较时出错
            if dt.tzinfo is None or dt.utcoffset() is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError, AttributeError):
            continue
    return None


class QueryPlaybackAction(Action):
    """播放记录查询动作。

    获取用户最近的播放记录，按专辑名过滤（如有），按10天窗口分组。
    """

    name = "action_query_playback"

    async def run(self, state: DialogueState, action_args: dict[str, Any]) -> ActionResult:
        try:
            payload = await fetch_playback_history(state.sender_id)
        except Exception:
            logger.exception("fetch_playback_history 调用失败")
            return ActionResult(slot_updates={
                "album_title": "暂时无法获取播放记录，请稍后重试。",
            })

        if payload is None or not payload.get("list"):
            return ActionResult(slot_updates={
                "album_title": "暂无播放记录。快去听听喜欢的作品吧！",
            })

        items = payload["list"]

        # 按专辑名过滤：LLM槽位 → 《》正则 → 专用 LLM 候选匹配
        album_filter = (state.active_task.slots.get("album_title") or "").strip()
        if not album_filter:
            user_text = (state.pending_turn.user_message.text or "") if state.pending_turn and state.pending_turn.user_message else ""
            m = _BOOK_NAME_PATTERN.search(user_text)
            if m:
                album_filter = m.group(1).strip()
            else:
                candidates = list(dict.fromkeys(
                    (item.get("albumTitle") or "").strip() for item in items
                ))
                album_filter = await extract_album_name(user_text, candidates) or ""
        # 统一剥离 LLM 可能带入的书名号
        album_filter = album_filter.strip("《》").strip()
        if album_filter:
            # 过滤时用简单子串匹配，因为 extract_album_name 已做了语义匹配
            items = [
                item for item in items
                if album_filter.lower() in (item.get("albumTitle") or "").lower()
            ]
            if not items:
                return ActionResult(slot_updates={
                    "album_title": f"在最近播放记录中未找到与「{album_filter}」相关的作品。",
                })

        lines = []

        if album_filter:
            # 指定了书名：精确返回该书的播放进度，无视时间窗口
            lines.append(f"《{album_filter}》的播放记录：")
            for item in items[:5]:
                track = item.get("trackTitle", "未知章节")
                try:
                    position = int(item.get("positionSeconds", 0) or 0)
                except (ValueError, TypeError):
                    position = 0
                progress = f"{position // 60}分{position % 60}秒" if position else "未播放"
                last_time = item.get("lastPlayedAt", "未知时间")
                lines.append(f"- {track}（进度{progress}，最近收听{last_time}）")
        else:
            # 未指定书名：按10天窗口分组展示
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(days=10)
            recent_items = []
            old_items = []

            for item in items:
                last_time = _parse_datetime(item.get("lastPlayedAt"))
                if last_time is None:
                    recent_items.append(item)
                elif last_time >= cutoff:
                    recent_items.append(item)
                else:
                    old_items.append(item)

            if recent_items:
                lines.append("你最近的播放记录：")
                for item in recent_items[:5]:
                    album = item.get("albumTitle", "未知专辑")
                    track = item.get("trackTitle", "未知章节")
                    try:
                        position = int(item.get("positionSeconds", 0) or 0)
                    except (ValueError, TypeError):
                        position = 0
                    progress = f"{position // 60}分{position % 60}秒" if position else "未播放"
                    last_time = item.get("lastPlayedAt", "未知时间")
                    lines.append(f"- {album} > {track}（进度{progress}，最近收听{last_time}）")
            else:
                lines.append("你最近10天内没有播放记录。")

            # 超过10天的提示
            old_albums: set[str] = set()
            for item in old_items:
                album = item.get("albumTitle", "")
                if album and album not in old_albums:
                    old_albums.add(album)
            if old_albums:
                lines.append("---")
                for album in old_albums:
                    lines.append(f"《{album}》")
                lines.append(f"包括以上内容在内的共{len(old_albums)}本有声书已超过10天没有听过啦~")

        return ActionResult(slot_updates={
            "album_title": "\n".join(lines),
})
