"""
闲聊轨道处理器

当 LLM 判断用户输入既不属于业务办理（Task轨道）也不属于知识查询（Knowledge轨道）时，
请求会被路由到闲聊轨道。闲聊处理器负责将用户消息和对话上下文交给 LLM，
生成自然友好的闲聊回复，不涉及任何业务数据查询。

职责：接收对话状态，委托给 ChitChatResponder 生成闲聊回复。
"""

import logging
from audio_cs.chitchat.responder import ChitChatResponder
from audio_cs.domain.messages import BotMessage

logger = logging.getLogger(__name__)


class ChitChatHandler:
    def __init__(self, chitchat_responder: ChitChatResponder):
        self.chitchat_responder = chitchat_responder

    async def hand(self, state) -> list[BotMessage]:
        logger.debug("闲聊轨道: sender_id=%s", state.sender_id)
        return await self.chitchat_responder.respond(state)
