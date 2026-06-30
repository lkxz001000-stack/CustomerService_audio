"""
意图澄清响应器

当 LLM 规划层无法确定用户意图时（TurnPlan 返回 ClarifyReason），
系统进入澄清轨道。本模块负责根据具体的澄清原因，生成恰当的引导性回复，
帮助用户明确自己的需求，以便系统能够正确路由到对应的处理轨道。

澄清工作流程：
1. 构建提示词上下文：收集澄清原因、基础引导脚本、用户消息、对话历史、焦点对象
2. LLM 润色：调用 LLM 将基础引导脚本改写为更自然、符合对话语境的客服话术
3. 返回澄清消息：将 LLM 生成的澄清文本返回给用户

澄清原因（ClarifyReason）与引导脚本的对应关系：
- MULTIPLE_TRACKS: 用户同时提到了多个方向（业务+知识），让用户选择优先处理哪个
- MISSING_FOCUSED_OBJECT: 用户缺少焦点对象（如没说具体是哪张专辑/哪个订单）
- MISSING_KNOWLEDGE_INTENT: 用户想咨询但没说明具体想了解什么
- MISSING_TRACK: 无法判断用户意图属于业务轨道还是知识轨道
- MISSING_TASK_COMMANDS: 用户想办业务但没说具体办什么
- OBJECT_REQUIRES_INTENT: 用户提供了焦点对象但没说明意图（如发了订单但没说查什么）
"""

import asyncio
import json
import logging
from typing import Any
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

from audio_cs.infrastructure.llm_client import llm_client
from audio_cs.plan.turn_plan import ClarifyReason
from audio_cs.domain.state import DialogueState
from audio_cs.domain.messages import BotMessage
from audio_cs.prompts.loader import load_prompt_template
from audio_cs.history.builder import ChatHistoryBuilder

logger = logging.getLogger(__name__)


class ClarifyResponser:
    """
    意图澄清响应器（把响应内容给用户展示）

    职责：当 LLM 规划层输出 ClarifyReason 时，根据具体原因生成引导性回复，
    帮助用户明确意图，以便系统能够继续后续处理。

    内部流程：
    (1) _build_clarify_prompt_inputs: 收集所有提示词所需的上下文变量
    (2) _build_base_script: 根据 ClarifyReason 生成基础引导脚本
    (3) _invoke_respond: 调用 LLM 对基础脚本进行润色，生成自然的客服话术
    """

    async def respond(self,
                      reason: ClarifyReason,
                      state: DialogueState
                      ) -> list[BotMessage]:
        """根据澄清原因生成引导性回复

        主入口方法，执行完整的澄清响应生成流程：
        (1) 构建提示词上下文（包含澄清原因、引导脚本、对话信息等）
        (2) 调用 LLM 生成润色后的澄清回复

        Args:
            reason: 澄清原因枚举，说明为什么 LLM 无法确定用户意图
            state: 对话状态对象，包含用户消息、对话历史、焦点对象等上下文

        Returns:
            包含 LLM 生成的澄清/引导文本的 BotMessage 列表
        """
        # 步骤1：构建意图澄清提示词所需的全部上下文变量
        prompt_inputs: dict[str, Any] = self._build_clarify_prompt_inputs(reason, state)
        logger.debug("意图澄清: reason=%s, sender_id=%s", reason.value, state.sender_id)

        # 步骤2：调用 LLM 将基础引导脚本润色为自然的客服话术
        return await self._invoke_respond(prompt_inputs)

    async def _invoke_respond(self, prompt_inputs: dict[str, Any]) -> list[BotMessage]:
        """调用 LLM 生成润色后的澄清回复

        加载 clarify_respond 提示词模板，组装 LangChain 链，
        将已准备好的上下文变量注入模板并调用 LLM。

        Args:
            prompt_inputs: _build_clarify_prompt_inputs 返回的上下文字典，
                          包含 reason, clarify_message, focused_object, history, user_message

        Returns:
            包含 LLM 润色后的澄清回复文本的 BotMessage 列表
        """
        # 加载澄清回复提示词模板
        clarify_prompt_template = load_prompt_template("clarify_respond")

        prompt_template = PromptTemplate.from_template(template=clarify_prompt_template, template_format="jinja2")

        # 组装链：提示词 → LLM → 字符串输出
        chain = prompt_template | llm_client | StrOutputParser()

        # 注入上下文变量并调用 LLM 生成润色后的引导话术
        rewritten_result = await chain.ainvoke(prompt_inputs)

        return [BotMessage(text=rewritten_result)]

    def _build_clarify_prompt_inputs(self,
                                     reason: ClarifyReason,
                                     state: DialogueState) -> dict[str, Any]:
        """构建澄清提示词所需的所有上下文变量

        从多个来源收集信息，组装为 LLM 提示词所需的完整输入字典：
        - reason: 澄清原因枚举值（字符串形式）
        - clarify_message: 基于 reason 生成的基础引导脚本
        - focused_object: 用户当前关注的焦点对象（如订单、专辑），序列化为 JSON
        - history: 最近10轮对话历史的文本表示
        - user_message: 当前用户消息的文本

        Args:
            reason: 澄清原因枚举
            state: 对话状态对象

        Returns:
            包含所有提示词输入变量的字典
        """
        # 格式化用户消息文本
        user_message_str = ChatHistoryBuilder.process_user_message(state.pending_turn.user_message)
        # 构建对话历史文本（最近10轮）
        history_str = ChatHistoryBuilder.build(state.current_session().turns[-10:])
        # 序列化焦点对象为 JSON 字符串（如 {"type": "order", "id": "12345"}）
        focused_object_str = json.dumps(state.focused_object.to_dict(),
                                        ensure_ascii=False) if state.focused_object else "null"
        # 根据澄清原因生成基础引导脚本
        clarify_message = self._build_base_script(reason, state)
        return {
            "reason": reason.value,  # 枚举的字符串内容，如 "missing_knowledge_intent"
            "clarify_message": clarify_message,
            "focused_object": focused_object_str,
            "history": history_str,
            "user_message": user_message_str

        }

    def _build_base_script(self, reason: ClarifyReason, state: DialogueState) -> str:
        """根据澄清原因生成基础引导脚本

        针对每种 ClarifyReason 枚举值，返回预设的引导话术。
        这些是"基础脚本"，后续会由 LLM 进行润色，使其更自然地融入对话上下文。

        Args:
            reason: 澄清原因枚举
            state: 对话状态（某些 reason 需要从中提取额外信息，如 focused_object.type）

        Returns:
            对应澄清原因的基础引导话术文本
        """

        # ----- 多轨道冲突：用户消息同时匹配了多个处理轨道 -----
        # 例如用户说"帮我查一下订单，顺便问问这个专辑怎么样"
        if reason is ClarifyReason.MULTIPLE_TRACKS:
            return "你这次同时提到了多个方向。我们先处理一个，你想先办业务还是先咨询信息呢？"

        # ----- 缺少焦点对象：知识查询需要用户指定具体对象（如哪个专辑、哪个订单）-----
        # 例如用户说"帮我看看这个的详情"但没有发送具体对象卡片
        if reason is ClarifyReason.MISSING_FOCUSED_OBJECT:
            return "请先发送你想咨询的对象，我再继续帮你看。"

        # ----- 缺少知识意图：用户想咨询信息但没说具体想了解什么 -----
        # 例如用户说"我想了解下"但没有说明具体咨询方向
        if reason is ClarifyReason.MISSING_KNOWLEDGE_INTENT:
            return "你是想了解商品信息、订单信息，还是售后配送规则呢？"

        # ----- 缺少轨道判定：LLM 无法确定用户意图属于业务还是知识咨询 -----
        # 这是比 MISSING_TASK_COMMANDS 和 MISSING_KNOWLEDGE_INTENT 更上层的模糊
        if reason is ClarifyReason.MISSING_TRACK:
            return "你是想先处理业务问题，还是先咨询信息呢？"

        # ----- 缺少任务命令：用户想办业务但没说具体办什么 -----
        # 例如用户说"帮我处理一下"但没有明确业务类型
        if reason is ClarifyReason.MISSING_TASK_COMMANDS:
            return "你这次是想办理什么业务呢？比如查订单、查物流，或者申请退款。"

        # ----- 有对象缺意图：用户提供了焦点对象（如发了订单），但没说想做什么 -----
        # 根据焦点对象的类型，给出针对性的引导选项
        if reason is ClarifyReason.OBJECT_REQUIRES_INTENT:
            focused_object = state.focused_object
            # 焦点对象是订单：引导用户选择查订单状态还是申请退款
            if focused_object is not None and focused_object.type == "order":
                return "我已经收到这个订单了。你想查订单状态，还是申请退款呢？"
            # 焦点对象是专辑：引导用户选择查专辑详情还是收听进度
            if focused_object is not None and focused_object.type == "album":
                return "我已经收到这个专辑了。你想了解它的详细信息，还是查看你的收听进度呢？"

        # ----- 兜底：无法归类到上述任何一种情况 -----
        # 返回通用引导话术，让用户换个方式表达需求
        return "我还需要再确认一下你的意思，你可以换个更具体的说法告诉我。"
