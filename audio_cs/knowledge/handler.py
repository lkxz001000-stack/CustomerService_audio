"""
知识轨道处理器

负责知识查询轨道的完整处理流程：
1. 意图匹配阶段：根据 LLM 输出的知识意图 ID，查找对应的数据提供者
2. 数据检索阶段：调用各数据提供者（API/FAQ/RAG）检索知识片段
3. 响应生成阶段：将检索结果交给 LLM 生成最终回复

设计意图：将意图解析、数据获取、响应生成三个关注点分离，
Handler 只负责编排流程，具体工作委托给各子组件。
"""

import logging
from audio_cs.domain.messages import BotMessage
from audio_cs.domain.state import DialogueState
from audio_cs.knowledge.intents import KnowledgeIntent
from audio_cs.knowledge.providers.registry import KnowledgeProviderRegistry
from audio_cs.knowledge.responder import KnowledgeResponder

logger = logging.getLogger(__name__)


class KnowledgeHandler:
    """知识轨道处理器

    编排知识查询的三阶段流程：
    阶段1 - 意图→提供者映射：根据 LLM 输出的意图 ID，查找对应的数据提供者 ID
    阶段2 - 数据检索：调用各数据提供者获取知识片段（KnowledgeChunk）
    阶段3 - LLM 响应生成：将知识片段作为上下文，由 LLM 生成用户友好的回复

    Attributes:
        knowledge_intents: 知识意图注册表，key=意图ID, value=KnowledgeIntent 对象
        knowledge_register: 知识提供者注册表，按 provider_id 查找具体提供者实例
        knowledge_responder: 知识响应生成器，调用 LLM 将检索数据转化为自然语言回复
    """

    def __init__(self,
                 knowledge_intents: dict[str, KnowledgeIntent],
                 knowledge_register: KnowledgeProviderRegistry,
                 knowledge_responder: KnowledgeResponder
                 ):
        """初始化知识处理器

        Args:
            knowledge_intents: 知识意图字典，将意图名称映射到意图配置（包含所需提供者列表）
            knowledge_register: 提供者注册表，用于按 ID 获取具体的数据提供者实例
            knowledge_responder: 响应生成器，负责调用 LLM 将知识片段合成最终回复
        """
        self.knowledge_intents = knowledge_intents
        self.knowledge_register = knowledge_register
        self.knowledge_responder = knowledge_responder

    async def hand(self,
                   state: DialogueState,
                   intents: list[str]) -> list[BotMessage]:
        """执行知识轨道的完整处理流程

        三阶段处理流水线：
        (1) 意图匹配：将 LLM 输出的意图 ID 列表映射为数据提供者 ID 列表
        (2) 数据检索：遍历每个提供者，调用 retrieve() 获取知识片段并汇总
        (3) 响应生成：将汇总的知识片段、用户消息、对话历史交给 LLM 生成回复

        Args:
            state: 对话状态对象，包含当前用户消息、对话历史、焦点对象等上下文
            intents: LLM 输出的知识意图 ID 列表，例如 ["product_info", "order_info"]

        Returns:
            BotMessage 列表，包含 LLM 基于检索知识生成的回复
        """

        # ===== 阶段1：意图匹配 —— 将意图 ID 映射为数据提供者 ID =====
        provider_ids = self._fetch_provider_ids_by_intents(intents)
        logger.debug("意图匹配: intents=%s -> providers=%s", intents, provider_ids)

        # ===== 阶段2：数据检索 —— 调用各提供者收集知识片段 =====
        final_chunks = []
        for provider_id in provider_ids:
            provider = self.knowledge_register.get(provider_id)
            knowledge_chunks = await provider.retrieve(state)
            logger.debug("知识检索: provider=%s, chunks=%d", provider_id, len(knowledge_chunks))
            final_chunks.extend(knowledge_chunks)

        # ===== 阶段3：响应生成 —— LLM 根据知识片段生成自然语言回复 =====
        logger.debug("生成知识回复: chunks_count=%d", len(final_chunks))
        return await self.knowledge_responder.respond(user_message=state.pending_turn.user_message,
                                                      recent_turns=state.current_session().turns[-10:],
                                                      chunks=final_chunks
                                                      )

    def _fetch_provider_ids_by_intents(self, intents: list[str]) -> list[str]:
        """根据意图 ID 列表查找对应的数据提供者 ID 列表

        遍历每个意图，从知识意图配置中提取其依赖的 provider_ids，
        汇总后去重返回。一个意图可能对应多个提供者（如会员权益需要
        同时查询 API 和 FAQ）。

        Args:
            intents: 意图 ID 列表，如 ["membership_info", "refund_policy"]

        Returns:
            去重后的数据提供者 ID 列表，如 ["api.membership", "faq.default"]
        """
        final_provider_ids = []
        for intent_id in intents:
            knowledge_intent = self.knowledge_intents[intent_id]
            final_provider_ids.extend(knowledge_intent.provider_ids)

        return list(set(final_provider_ids))  # 去重，避免同一提供者被多次调用
