"""
专辑详情查询 Action。

按专辑名称查询音频平台的专辑详情 API，获取章节数、主播、
时长等信息，格式化为可读文本后写入槽位。
"""

import logging
from typing import Any

from audio_cs.config.settings import settings
from audio_cs.domain.state import DialogueState
from audio_cs.infrastructure import http_client
from audio_cs.task.action.base import Action, ActionResult
from audio_cs.task.action.customer.shared import fetch_album_by_name
from audio_cs.task.action.customer.slot_extractor import extract_album_name

logger = logging.getLogger(__name__)


async def _search_album_candidates(keyword: str) -> list[str]:
    """搜索专辑获取候选名称列表，供 LLM 匹配使用。"""
    try:
        base_url = settings.audio_api_base_url.rstrip("/")
        r = await http_client.http_client.get(
            f"{base_url}/api/v1/albums",
            params={"keyword": keyword, "pageSize": 10},
        )
        r.raise_for_status()
        data = r.json().get("data", {})
        items = data.get("list", []) if isinstance(data, dict) else []
        return [item.get("title", "") for item in items if item.get("title")]
    except Exception:
        logger.exception("_search_album_candidates 异常: keyword=%s", keyword)
        return []


class QueryAlbumDetailAction(Action):
    """专辑详情查询动作。

    从当前流程的 slots 中读取 album_name，
    调用音频平台接口按名称查询专辑详情，
    将格式化后的详情文本写入 album_info 槽位。
    """

    name = "action_query_album_detail"

    async def run(self, state: DialogueState, action_args: dict[str, Any]) -> ActionResult:
        album_name = state.active_task.slots.get("album_name", "").strip()
        if not album_name:
            return ActionResult(slot_updates={
                "album_info": "请告诉我你想了解的作品名称。",
            })

        payload = await fetch_album_by_name(album_name)

        # 精确查找失败时，用搜索 API 获取候选列表，让 LLM 做语义匹配
        if payload is None:
            candidates = await _search_album_candidates(album_name)
            if candidates:
                matched = await extract_album_name(album_name, candidates)
                if matched:
                    payload = await fetch_album_by_name(matched)

        if payload is None:
            return ActionResult(slot_updates={
                "album_info": f"未找到「{album_name}」的相关信息，请确认作品名称是否正确。",
            })

        # 提取专辑信息
        album = payload.get("album", payload)
        parts = [f"《{album.get('title', album_name)}》"]

        # 作者/主播
        author = album.get("author") or album.get("narrator") or ""
        if author:
            parts.append(f"主播：{author}")

        # 章节数
        total_chapters = album.get("totalChapters") or album.get("chapterCount") or album.get("total_chapters")
        if total_chapters is not None:
            parts.append(f"总集数：{total_chapters}集")

        # 已更新章节
        updated = album.get("updatedChapters") or album.get("updated_chapters")
        if updated is not None:
            parts.append(f"已更新：{updated}集")

        # 时长
        duration = album.get("duration") or album.get("totalDuration") or ""
        if duration:
            parts.append(f"时长：{duration}")

        # 评分
        rating = album.get("rating") or album.get("score")
        if rating is not None:
            parts.append(f"评分：{rating}")

        # 简介
        description = album.get("description") or album.get("intro") or ""
        if description:
            parts.append(f"简介：{description}")

        # 章节列表（简要）
        chapters = album.get("chapters") or payload.get("chapters") or []
        if chapters:
            chapter_names = [
                ch.get("title") or ch.get("chapterTitle") or ""
                for ch in chapters[:5]
            ]
            chapter_names = [n for n in chapter_names if n]
            if chapter_names:
                parts.append("章节列表（前5集）：" + "、".join(chapter_names))

        return ActionResult(slot_updates={
            "album_info": "\n".join(parts),
        })
