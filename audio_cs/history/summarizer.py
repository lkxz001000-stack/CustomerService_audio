"""对话摘要服务 — 超过 5 轮的部分后台异步生成摘要"""

import asyncio
import logging
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from audio_cs.infrastructure.llm_client import llm_client
from audio_cs.prompts.loader import load_prompt_template
from audio_cs.history.builder import ChatHistoryBuilder

logger = logging.getLogger(__name__)

SUMMARY_THRESHOLD = 5

# 内存缓存：session_id → summary
_summary_cache: dict[str, str] = {}


def get_cached_summary(session_id: str) -> str | None:
    return _summary_cache.get(session_id)


async def try_generate_summary(state):
    """如果会话轮数超过阈值，生成早期对话的摘要并缓存"""
    session = state.current_session()
    if not session or len(session.turns) <= SUMMARY_THRESHOLD:
        return

    older_turns = session.turns[:-SUMMARY_THRESHOLD]
    if not older_turns:
        return

    history_text = ChatHistoryBuilder.build(older_turns)
    template = load_prompt_template("conversation_summary")
    prompt = PromptTemplate.from_template(template=template, template_format="jinja2")
    chain = prompt | llm_client | StrOutputParser()

    try:
        summary = await asyncio.wait_for(
            chain.ainvoke({"conversation": history_text}),
            timeout=30.0,
        )
        _summary_cache[session.session_id] = summary
        logger.info("对话摘要已生成: session=%s, 摘要%d轮 → %d字符",
                    session.session_id, len(older_turns), len(summary))
    except Exception as e:
        logger.warning("对话摘要生成失败: %s", e)
