"""
对话轮次规划器（TurnPlanner）模块

职责：将用户消息与对话上下文组合，构建提示词输入，调用 LLM 生成 TurnPlan，
从而决定本轮对话应该走哪条处理轨道（任务轨道 / 知识检索轨道 / 闲聊轨道）。

核心流程：
  1. _prepare_prompt_inputs: 从对话状态中提取并序列化 JSON 片段
  2. predict_from_prompt_inputs: 加载 Jinja2 模板，构建 LangChain 链，调用 LLM 并解析 JSON 结果
  3. predict: 对外统一入口，组合上述两步
"""

import json
import logging
from typing import Any
from dataclasses import asdict

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from audio_cs.plan.turn_plan import TurnPlan
from audio_cs.domain.messages import UserMessage
from audio_cs.domain.state import DialogueState
from audio_cs.prompts.loader import load_prompt_template
from audio_cs.infrastructure.llm_client import llm_client
from audio_cs.history.builder import ChatHistoryBuilder
from audio_cs.task.flow.flows import FlowsList
from audio_cs.knowledge.intents import KnowledgeIntent

logger = logging.getLogger(__name__)


class TurnPlanner:
    """
    对话轮次规划器

    核心职责：
    - 收集对话上下文（当前轮用户消息、最近10轮历史、活跃任务、中断任务、可用业务流程、知识意图清单）
    - 构建提示词输入字典，委托 LangChain 链调用 LLM
    - 解析 LLM 输出的 JSON，构建 TurnPlan 领域对象

    LLM 在此扮演"路由器"角色：根据用户意图，选择 task / knowledge / chitchat 三条轨道之一。

    注意：本类不负责校验 TurnPlan 的合法性，校验由 TurnPlanValidator 完成。
    """

    async def predict(self,
                      user_message: UserMessage,
                      *,
                      state: DialogueState,
                      flow_list: FlowsList,
                      intents: dict[str, KnowledgeIntent]
                      ) -> TurnPlan:
        """
        对外统一的规划入口。

        步骤：
        1. 从对话状态和领域对象中提取提示词所需的所有 JSON 片段
        2. 调用支持 Jinja2 模板的 LangChain 链，由 LLM 输出 TurnPlan 字典
        3. 将字典反序列化为 TurnPlan 领域对象并返回

        :param user_message: 用户当前轮输入消息
        :param state: 当前对话的完整状态（含历史、活跃任务、中断任务、聚焦对象等）
        :param flow_list: 系统中定义的所有业务流程（用户流程+系统流程）
        :param intents: 知识检索意图注册表（意图ID → KnowledgeIntent）
        :return: LLM 生成的轮次规划结果
        """
        # 1. 构建提示词模版要的内容（不需要构建提示词模版）

        prompt_inputs: dict[str, Any] = self._prepare_prompt_inputs(user_message, state=state, flow_list=flow_list,
                                                                    intents=intents)

        # 2. 调用大语言模型
        turn_plan = await self.predict_from_prompt_inputs(prompt_inputs)

        return turn_plan

    def _prepare_prompt_inputs(self,
                               user_message: UserMessage,
                               state: DialogueState,
                               flow_list: FlowsList,
                               intents: dict[str, KnowledgeIntent]
                               ) -> dict[str, Any]:
        """
        构建 LLM 提示词所需的所有输入数据。

        从对话状态中提取以下七个维度的信息并序列化为 JSON 字符串，
        作为 Jinja2 模板的渲染变量：

        1. user_message          — 当前轮用户消息（经聊天历史构建器加工）
        2. current_conversation  — 最近10轮对话历史
        3. focused_object_json   — 用户当前聚焦的界面对象（如点击的卡片），null 表示无聚焦
        4. interrupted_tasks_json— 中断栈中暂存的业务流程（等待恢复）
        5. active_task_json      — 当前正在执行的活跃业务流程，null 表示无活跃任务
        6. available_flows_json  — 可用的用户业务流程清单（排除系统流程，不含 steps 细节）
        7. knowledge_intents_json— 知识检索意图清单（ID + 描述）
        8. available_slots_json  — 全局可用槽位清单（名称 + 描述），供 set_slots 命令参考

        :return: 可直接传给 Jinja2 PromptTemplate 的变量字典
        """
        # ---- 用户消息与对话历史 ----
        user_message = ChatHistoryBuilder.process_user_message(user_message)
        current_conversation = ChatHistoryBuilder.build(state.current_session().turns[-10:])

        # ---- 聚焦对象：用户当前点击的界面卡片/按钮，用于判断是否需要先澄清意图 ----
        focused_object_json = json.dumps(state.focused_object.to_dict(),
                                         ensure_ascii=False) if state.focused_object else "null"

        # ---- 中断任务栈：保存被中断的业务流程，供后续恢复使用 ----
        interrupted_tasks_json = json.dumps([paused_task.to_dict() for paused_task in state.interrupted_active_tasks],
                                            ensure_ascii=False)

        # ---- 当前活跃业务流程：用户正在执行中的业务（如订单查询、退款申请） ----
        active_task_json = json.dumps(state.active_task.to_dict(),
                                      ensure_ascii=False) if state.active_task else "null"

        # ---- 可用业务流程清单：仅提供用户业务流程（过滤掉 system_ 前缀的系统流程），
        #      且不包含 steps 细节，避免提示词过长干扰 LLM 判断 ----
        available_flows_json = json.dumps({
            "flows": [
                {
                    k: v for k, v in asdict(flow).items() if k != "steps"
                } for flow in flow_list.flows if not flow.flow_id.startswith("system_")
            ]
        }, ensure_ascii=False)

        # ---- 全局可用槽位清单：告知 LLM 所有可用的槽位名称和用途，
        #      使其能在 set_slots 命令中提取用户消息中的关键信息 ----
        available_slots_json = json.dumps(
            [{"name": slot.name, "description": slot.description} for slot in flow_list.slots.values()],
            ensure_ascii=False
        )

        # ---- 知识检索意图清单：告知 LLM 系统支持哪些知识查询场景 ----
        knowledge_intents_json = json.dumps(
            [{"id": intent.id, "description": intent.description} for intent in intents.values()],
            ensure_ascii=False
        )

        return {
            "user_message": user_message,
            "current_conversation": current_conversation,

            "focused_object_json": focused_object_json,

            "interrupted_tasks_json": interrupted_tasks_json,
            "active_task_json": active_task_json,

            "available_flows_json": available_flows_json,
            "knowledge_intents_json": knowledge_intents_json,
            "available_slots_json": available_slots_json,

        }

    async def predict_from_prompt_inputs(self, prompt_inputs: dict[str, Any]) -> TurnPlan:
        """
        采用 LangChain 链式调用 LLM 并解析结果。

        链结构：PromptTemplate | llm_client | JsonOutputParser
          1. PromptTemplate.invoke(prompt_inputs)  → 格式化的提示词文本
          2. llm_client.invoke(格式化提示词)        → LLM 原始响应
          3. JsonOutputParser.invoke(LLM响应)      → dict（Python 字典）

        :param prompt_inputs: _prepare_prompt_inputs 产出的变量字典
        :return: 反序列化后的 TurnPlan 领域对象
        """
        # 1. 加载 Jinja2 提示词模板（prompts/turn_plan.j2）
        task_prompt_template = load_prompt_template("turn_plan")

        # 2. 创建 LangChain PromptTemplate 对象，指定 Jinja2 模板引擎
        prompt_template = PromptTemplate.from_template(template=task_prompt_template, template_format="jinja2")

        # 3. 构建链：模板 → LLM → JSON解析器（LangChain LCEL 管道语法）
        chain = prompt_template | llm_client | JsonOutputParser()

        # 4. 执行链调用：原始输入依次经过三阶段处理，最终得到 dict
        turn_plan_dict = await chain.ainvoke(prompt_inputs)
        logger.debug("LLM 规划输出: %s", json.dumps(turn_plan_dict, ensure_ascii=False)[:200])

        # 5. 将 LLM 输出的字典反序列化为类型安全的 TurnPlan 领域对象
        return TurnPlan.from_dict(turn_plan_dict)
