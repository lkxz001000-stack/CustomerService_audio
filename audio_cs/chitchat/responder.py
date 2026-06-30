"""
闲聊响应生成器

负责将用户消息和对话历史组装为提示词，调用 LLM 生成自然友好的闲聊回复。

与 KnowledgeResponder 的区别：
- KnowledgeResponder 需要注入检索到的知识片段作为参考素材
- ChitChatResponder 仅依赖用户消息和对话历史，不涉及外部数据

工作流程：
1. 格式化用户消息和最近10轮对话历史
2. 加载 chitchat_respond 提示词模板（Jinja2）
3. 组装 LangChain 链并调用 LLM 生成回复
"""

import logging
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

from audio_cs.domain.messages import BotMessage
from audio_cs.domain.state import DialogueState
from audio_cs.history.builder import ChatHistoryBuilder
from audio_cs.prompts.loader import load_prompt_template
from audio_cs.infrastructure.llm_client import llm_client

logger = logging.getLogger(__name__)


class ChitChatResponder:
    """闲聊响应生成器

    调用 LLM 生成类人闲聊回复。不使用任何外部知识或业务数据，
    仅基于用户消息和对话历史让 LLM 自由发挥。提示词模板（chitchat_respond）
    通常会让 LLM 扮演一个友好的听书平台客服角色进行自然对话。

    注入变量：
    - user_message: 当前用户消息文本
    - history: 最近10轮对话历史
    """

    async def respond(self, state: DialogueState) -> list[BotMessage]:
        """根据对话状态生成闲聊回复

        从对话状态中提取用户消息和对话历史，组装提示词后调用 LLM。

        Args:
            state: 对话状态对象，包含 pending_turn.user_message（当前用户消息）
                   和 current_session().turns（完整对话轮次历史）

        Returns:
            包含 LLM 生成的闲聊回复的 BotMessage 列表
        """
        # 格式化用户消息
        user_message = ChatHistoryBuilder.process_user_message(state.pending_turn.user_message)
        # 截取最近10轮对话历史
        history = ChatHistoryBuilder.build(state.current_session().turns[-10:])

        # 加载闲聊回复提示词模板
        prompt_text = load_prompt_template("chitchat_respond")
        prompt = PromptTemplate.from_template(prompt_text, template_format="jinja2")
        # 组装 LangChain 处理链：提示词 → LLM → 字符串解析
        chain = prompt | llm_client | StrOutputParser()
        # 注入上下文变量并调用 LLM
        logger.debug("生成闲聊回复...")
        response = await chain.ainvoke({
            "user_message": user_message,
            "history": history,
        })
        return [BotMessage(text=response)]
