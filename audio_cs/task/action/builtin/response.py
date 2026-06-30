from itertools import chain
from typing import Any

from jinja2 import Template
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from audio_cs.domain.messages import BotMessage
from audio_cs.domain.state import DialogueState
from audio_cs.task.action.base import Action, ActionResult
from audio_cs.infrastructure.llm_client import llm_client
from audio_cs.history.builder import ChatHistoryBuilder


class ActionResponse(Action):
    """回复生成 Action。

    根据流程 YAML 中配置的回复模板，生成最终发送给用户的 BotMessage。
    支持三种工作模式：

    1. static（静态模式）：
       直接使用 Jinja2 模板渲染，将槽位/上下文变量替换后返回。
       适用于回复内容固定、无需 LLM 润色的场景。

    2. rephrase（改写模式）：
       先用 Jinja2 模板渲染基础文本，再调用 LLM 按照 prompt 指令
       对渲染结果进行改写。适用于需要 LLM 润色但保留原始数据语义的场景。

    3. prompt（提示词模式）：
       完全交由 LLM 生成回复，模板中只提供 prompt 指令而不包含
       基础文本。适用于需要 LLM 自由组织语言的场景。

    mode 由 action_args 中的 'mode' 键指定，默认为 'static'。
    """

    name = "action_response"

    async def run(self,
                  state: DialogueState,
                  action_args: dict[str, Any]) -> ActionResult:
        """执行回复生成。

        action_args 预期包含：
        - mode (str)：'static' / 'rephrase' / 'prompt'，默认 'static'
        - text (str)：回复模板文本（static、rephrase 模式下使用）
        - prompt (str)：LLM 改写/生成指令（rephrase、prompt 模式下使用）

        参数：
            state：当前对话状态，提供槽位和上下文数据
            action_args：流程 YAML 中配置的动作参数

        返回：
            包含生成的 BotMessage 的 ActionResult
        """
        action_res_mode = action_args.get('mode', 'static')

        if action_res_mode == "static":
            # ---- 静态模式：模板渲染后直接返回 ----
            text = action_args['text']
            render_text = self._render_text(text, state)
            return ActionResult(messages=[BotMessage(text=render_text)])
        elif action_res_mode == "rephrase":
            # ---- 改写模式：模板渲染 + LLM 改写 ----
            text = action_args['text']
            prompt_text = action_args['prompt']
            render_text = self._render_text(text, state)
            rewritten = await self._call_llm(state, prompt_text, render_text)
            return ActionResult(messages=[BotMessage(text=rewritten)])
        else:
            # ---- 提示词模式（默认 fallback）：完全由 LLM 生成 ----
            prompt_text = action_args['prompt']
            rewritten = await self._call_llm(state, prompt_text)
            return ActionResult(messages=[BotMessage(text=rewritten)])

    def _render_text(self, text: str,
                     state: DialogueState) -> str:
        """使用 Jinja2 渲染回复模板。

        模板中可引用两个变量：
        - slots：当前活跃业务任务的槽位数据
        - context：当前活跃系统任务的上下文对象（如 StartedSystemContext）

        参数：
            text：Jinja2 模板字符串，例如 "你的订单{{slots.order_number}}已发货"
            state：对话状态

        返回：
            渲染后的文本字符串
        """
        template = Template(text)

        return template.render(
            slots=state.active_task.slots if state.active_task else {},
            context=state.active_system_task
        )

    async def _call_llm(self,
                        state: DialogueState,
                        prompt_text: str,
                        render_text: str = "") -> str:
        """调用 LLM 客户端生成或改写回复文本。

        使用 LangChain 的 LCEL 链式调用：
        prompt_template | llm_client | StrOutputParser

        上下文注入：
        - history：最近 10 轮对话历史（ChatHistoryBuilder 构建）
        - user_message：当前轮次的用户消息
        - current_response：待改写的原始文本（仅 rephrase 模式传入）

        参数：
            state：对话状态，提供会话和用户消息
            prompt_text：LLM 的提示词模板
            render_text：待改写的原始文本，默认为空

        返回：
            LLM 生成的最终回复文本
        """
        prompt_template = PromptTemplate.from_template(prompt_text)

        chain = prompt_template | llm_client | StrOutputParser()

        rewritten = await chain.ainvoke({
            "history": ChatHistoryBuilder.build(state.current_session().turns[-10:]),
            "user_message": ChatHistoryBuilder.process_user_message(state.pending_turn.user_message),
            "current_response": render_text
        })

        return rewritten
