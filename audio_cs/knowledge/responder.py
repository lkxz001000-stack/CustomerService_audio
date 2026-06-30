"""
知识响应生成器

负责将检索到的知识片段（KnowledgeChunk）与用户消息、对话历史组装成提示词，
调用 LLM 生成自然、友好的客服回复。

工作流程：
1. 准备上下文：格式化用户消息、截取最近10轮对话历史、拼接所有知识片段
2. 构建提示词：加载 knowledge_respond 模板（Jinja2），注入上述上下文
3. 调用 LLM：通过 LangChain 链式调用 LLM，将原始数据转化为客服话术
"""

import logging
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

from audio_cs.domain.messages import BotMessage, UserMessage
from audio_cs.domain.state import Turn
from audio_cs.infrastructure.llm_client import llm_client
from audio_cs.knowledge.providers.base import KnowledgeChunk
from audio_cs.history.builder import ChatHistoryBuilder
from audio_cs.prompts.loader import load_prompt_template

logger = logging.getLogger(__name__)


class KnowledgeResponder:
    """知识响应生成器

    将数据提供者检索到的原始知识片段转化为用户可读的自然语言回复。
    利用 LLM 的理解和生成能力，将结构化的 API 数据或 FAQ 文本重新组织为
    符合对话上下文、语气友好的客服回复。

    依赖的提示词模板：knowledge_respond（定义在 prompts/ 目录下）
    注入变量：user_message（用户消息）、history（对话历史）、knowledge_content（检索知识）
    """

    async def respond(
            self,
            user_message: UserMessage,
            recent_turns: list[Turn],
            chunks: list[KnowledgeChunk],
    ) -> list[BotMessage]:
        """根据检索到的知识生成客服回复

        Args:
            user_message: 当前用户的原始消息对象
            recent_turns: 最近10轮对话历史，用于让 LLM 理解上下文
            chunks: 从各数据提供者检索到的知识片段列表

        Returns:
            包含 LLM 生成文本的 BotMessage 列表（通常只有一条消息）
        """

        # ----- 步骤1：准备提示词所需的上下文变量 -----
        # 将用户消息格式化为提示词可用的文本
        user_message = ChatHistoryBuilder.process_user_message(user_message)
        # 构建最近10轮对话的历史文本
        history = ChatHistoryBuilder.build(recent_turns)
        # 将所有知识片段的内容用双换行拼接为一个文本块
        knowledge_content = "\n\n".join([chunk.content for chunk in chunks])
        logger.debug("知识响应生成: chunks=%d, content_len=%d", len(chunks), len(knowledge_content))

        # ----- 步骤2：构建 LangChain 处理链 -----
        # 加载知识响应提示词模板（Jinja2 格式）
        prompt_text = load_prompt_template("knowledge_respond")
        prompt = PromptTemplate.from_template(
            prompt_text,
            template_format="jinja2"
        )
        # 组装链：提示词 → LLM 调用 → 字符串输出解析
        chain = prompt | llm_client | StrOutputParser()

        # ----- 步骤3：调用 LLM 生成回复 -----
        # 将上下文变量注入提示词，由 LLM 根据知识片段生成客服回复
        response = await chain.ainvoke({
            "user_message": user_message,
            "history": history,
            "knowledge_content": knowledge_content,
        })

        return [BotMessage(text=response)]
