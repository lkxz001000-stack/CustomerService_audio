"""
专用 LLM 槽位提取器。

提供聚焦单一任务的槽位提取能力：给定候选列表和用户消息，
让 LLM 专注做"候选匹配"而非开放提取，比通用 TurnPlanner 中的
多任务 set_slots 更可靠。当前支持专辑名提取，后续可扩展其他槽位类型。
"""

import logging

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

from audio_cs.infrastructure.llm_client import llm_client

logger = logging.getLogger(__name__)

_EXTRACT_PROMPT = PromptTemplate.from_template(
    template="""用户消息：\"\"\"{{ user_text }}\"\"\"

候选专辑列表：
{% for c in candidates %}
- {{ c }}
{% endfor %}

请判断用户消息指的是候选列表中的哪张专辑。
如果匹配，请**原样**返回候选列表中的专辑名称（一字不差）；
如果不确定或没有匹配，请返回 <none>。

只返回专辑名或 <none>，不要输出其他任何内容。""",
    template_format="jinja2",
)


async def extract_album_name(user_text: str, candidates: list[str]) -> str | None:
    """调用 LLM 从候选列表中匹配用户所指的专辑名。

    与 TurnPlanner 中多任务 set_slots 不同，此函数让 LLM 聚焦单一任务：
    给定用户消息和有限候选集，选出最佳匹配。候选集来自播放记录或搜索结果，
    大幅降低 LLM 幻觉风险。

    Args:
        user_text: 用户原始消息文本
        candidates: 候选专辑名列表（去重后），最多传入 50 条以避免 prompt 过长

    Returns:
        匹配到的专辑名（与候选列表中完全一致），无匹配时返回 None
    """
    if not user_text or not candidates:
        return None

    # 去重并限制数量，避免 prompt 过长
    unique = list(dict.fromkeys(candidates))[:50]

    try:
        chain = _EXTRACT_PROMPT | llm_client | StrOutputParser()
        result = await chain.ainvoke({"user_text": user_text, "candidates": unique})
        matched = result.strip()

        if not matched or matched == "<none>":
            return None

        # 校验 LLM 返回值是否在候选列表中（防止幻觉）
        if matched in unique:
            return matched

        # 若不完全一致，尝试大小写不敏感匹配
        matched_lower = matched.lower()
        for name in unique:
            if name.lower() == matched_lower:
                return name

        logger.warning("LLM 返回的专辑名不在候选列表中: matched=%s", matched)
        return None
    except Exception:
        logger.exception("extract_album_name LLM 调用异常")
        return None
