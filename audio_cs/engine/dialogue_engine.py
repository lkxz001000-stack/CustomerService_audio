"""
核心对话引擎，管理会话生命周期和消息路由

本模块是客服系统的大脑，负责：
1. 管理用户会话的创建、复用、超时关闭（60分钟会话超时）
2. 接收用户消息后，根据消息类型（TEXT/OBJECT）路由到不同处理逻辑
3. 对文本消息，调用 LLM 做意图规划，按三条处理轨道路由到对应处理器
4. 对卡片点击消息，解析为槽位命令或触发意图澄清
5. 管理每个轮次（turn）的完整生命周期
"""

import logging
import time
import asyncio
from typing import Any, Coroutine

from audio_cs.domain.state import DialogueState
from audio_cs.domain.messages import ProcessResult, BotMessage, UserMessage, MessageType, FocusedObject
from audio_cs.knowledge.intents import KnowledgeIntent
from audio_cs.plan.planner import TurnPlanner
from audio_cs.task.handler import TaskHandler
from audio_cs.knowledge.handler import KnowledgeHandler
from audio_cs.chitchat.handler import ChitChatHandler
from audio_cs.task.flow.flows import FlowsList
from audio_cs.plan.validator import TurnPlanValidator
from audio_cs.clarify.responder import ClarifyResponser
from audio_cs.task.command.commands import Command, SetSlotsCommand, StartedFlowCommand
from audio_cs.task.flow.steps import CollectFlowStep
from audio_cs.plan.turn_plan import ClarifyReason
from audio_cs.history.summarizer import try_generate_summary
from evaluation.telemetry import telemetry

logger = logging.getLogger(__name__)


class DialogueEngine:
    """
    核心对话引擎

    职责：
    - 管理会话（Session）的创建、复用与超时关闭
    - 管理对话轮次（Turn）的完整生命周期
    - 根据消息类型分支处理：
        * 文本消息（TEXT）→ 调用 LLM 规划路由 → 三条轨道分发
        * 对象消息（OBJECT / 卡片点击）→ 解析为槽位命令，继续流程或澄清意图

    三条处理轨道：
    1. Task 轨道（业务轨道）：执行业务流程（订单查询、退款、工单等）
    2. Knowledge 轨道（知识轨道）：检索平台知识库回答用户问题
    3. ChitChat 轨道（闲聊轨道）：LLM 直接生成闲聊回复

    依赖（构造函数注入）：
    - planner：调用 LLM 生成 TurnPlan，决定走哪条轨道
    - turn_plan_validator：校验 LLM 输出的合法性
    - task_handler：业务流程处理器
    - knowledge_handler：知识查询处理器
    - chitchat_handler：闲聊处理器
    - clarify_responder：意图澄清器（LLM 输出不合法或用户意图模糊时介入）
    """

    def __init__(self,
                 planner: TurnPlanner,
                 turn_plan_validator: TurnPlanValidator,
                 task_handler: TaskHandler,
                 knowledge_handler: KnowledgeHandler,
                 chitchat_handler: ChitChatHandler,
                 clarify_responder: ClarifyResponser

                 ):
        self.planner = planner
        self.task_handler = task_handler
        self.turn_plan_validator = turn_plan_validator

        self.knowledge_handler = knowledge_handler
        self.chitchat_handler = chitchat_handler
        self.clarify_responder = clarify_responder

    async def hand_message(self,
                           user_message: UserMessage,
                           state: DialogueState) -> ProcessResult:
        """
        引擎处理消息的主入口

        完整处理流程（6步）：
        1. 准备会话（Session）—— 创建、复用或超时重建
        2. 创建新的对话轮次（Turn）
        3. 根据消息类型分支：
           3.1 TEXT 文本消息 → 调用 LLM 做意图规划，按三条轨道路由
           3.2 OBJECT 对象消息 → 解析卡片内容，生成槽位命令或澄清意图
        4. 将生成的机器人消息写入 pending_turn
        5. 提交当前轮次（pending_turn 转为已完成的 turn）
        6. 返回 ProcessResult（包含 sender_id、message_id 和机器人回复列表）

        :param user_message: 用户发送的消息（领域对象）
        :param state: 对话状态（含会话历史、当前流程等上下文）
        :return: ProcessResult，包含机器人回复消息列表
        """
        t_start = time.time()

        # 1. 准备session对象（创建/复用/重建会话）
        self._prepare_session(state)

        # 2. 创建新的对话轮次（turn）
        self._begin_turn(user_message, state)

        diagnostics = {}

        # 3. 判断消息类型，分两条路处理
        # 3.1 文本消息类型 —— 需要调用 LLM 做意图识别和轨道路由
        if user_message.type is MessageType.TEXT:
            logger.info("处理文本消息: sender_id=%s, msg_id=%s", user_message.sender_id, user_message.message_id)
            bot_msgs, diag = await self._hand_text_msg(user_message,
                                                 state=state,
                                                 flow_list=self.task_handler.flow_list,
                                                 intents=self.knowledge_handler.knowledge_intents)

        # 3.2 对象消息类型 —— 卡片点击，语义明确，无需 LLM 即可路由
        else:
            logger.info("处理卡片点击: sender_id=%s, object_type=%s, object_id=%s",
                        user_message.sender_id, user_message.object.type, user_message.object.id)
            state.set_focused_object(user_message.object)
            bot_msgs = await self._hand_obj_msg(user_message.object, state, self.task_handler.flow_list)
            diag = {"track": "task", "message_type": "object",
                    "object_type": user_message.object.type}

        # 4. 将机器人回复消息写入 pending_turn（当前轮次的暂存区）
        state.pending_turn.bot_messages = bot_msgs

        # 5. 提交 pending_turn —— 将暂存轮次归档到 session 的 turns 列表中
        state.commit_pending_turn()

        # 6. 在线指标记录
        elapsed = time.time() - t_start
        await telemetry.record_request(elapsed)

        # 7. 组装返回结果
        return ProcessResult(
            sender_id=user_message.sender_id,
            message_id=user_message.message_id,
            messages=bot_msgs,
            diagnostics=diag,
        )

    def _prepare_session(self, state: DialogueState):
        """
        准备会话（Session），确保新消息到来时有一个有效的会话上下文

        会话生命周期管理逻辑：
        1. 获取当前活跃会话
        2. 如果当前没有会话 → 创建新会话
        3. 如果当前会话存在：
           3.1 超过 60 分钟未活动 → 关闭旧会话、重置运行状态、创建新会话
           3.2 未超时 → 仅更新 last_activity_at，继续复用当前会话

        :param state: 对话状态对象
        :return: None
        """

        # 1. 获取当前活跃会话（可能为 None）
        current_session = state.current_session()

        # 2. 当前会话不存在 → 创建新会话
        if current_session is None:
            state.start_session()
            logger.debug("创建新会话: sender_id=%s", state.sender_id)
            return

        # 3. 当前会话存在，判断是否超时（60分钟 = 3600秒）
        now = time.time()
        if now - current_session.last_activity_at > 60 * 60:
            # a) 关闭过期的session
            state.close_session()
            logger.info("会话超时重建: sender_id=%s", state.sender_id)
            # b) 重置过期信息
            state.reset_running_state_for_new_session()
            # c) 创建新的session
            state.start_session()
        else:
            current_session.last_activity_at = now

        return

    def _begin_turn(self,
                    user_message: UserMessage,
                    state: DialogueState):
        """
        开始一个新的对话轮次（Turn）

        每个用户消息对应一个 turn，turn 包含了用户消息和后续的机器人回复。
        如果存在 pending_turn（上一轮未提交的轮次），会被覆盖。

        :param user_message: 用户消息对象
        :param state: 对话状态
        """
        state.start_turn(user_message)

    async def _hand_text_msg(self,
                             user_message: UserMessage,
                             *,
                             state: DialogueState,
                             flow_list: FlowsList,
                             intents: dict[str, KnowledgeIntent]
                             ) -> tuple[list[BotMessage], dict]:
        """
        处理文本类型消息 —— 完整的 LLM 规划 + 轨道路由流程

        处理步骤：
        1. 调用 LLM（TurnPlanner）进行意图规划和轨道路由分析
        2. 利用 TurnPlanValidator 校验 LLM 输出的合法性
        3. 根据校验结果分支：
           3.1 校验失败 → 触发意图澄清（ClarifyResponder），生成引导性回复
           3.2 校验通过 → 按规划结果路由到对应轨道：
                - turn_plan.task 非空 → Task 轨道（业务流程）
                - turn_plan.knowledge 非空 → Knowledge 轨道（知识查询）
                - 否则 → ChitChat 轨道（闲聊）

        :param user_message: 用户文本消息
        :param state: 对话状态（含上下文历史）
        :param flow_list: 所有已注册的业务流程和系统流程
        :param intents: 已注册的知识查询意图字典
        :return: (机器人回复消息列表, 诊断信息字典)
        """
        diagnostics: dict = {}

        # 1. 调用 LLM 进行路由分析，得到规划结果 TurnPlan
        logger.debug("调用 LLM 进行意图规划...")

        # 后台异步生成对话摘要（超过 5 轮时），不阻塞当前请求
        asyncio.create_task(try_generate_summary(state))

        turn_plan = await self.planner.predict(user_message, state=state, flow_list=flow_list, intents=intents)

        # 记录 TurnPlan 信息
        tracks = turn_plan.activated_tracks()
        diagnostics["predicted_tracks"] = tracks
        if turn_plan.knowledge is not None:
            diagnostics["knowledge_intents"] = turn_plan.knowledge.intents
        if turn_plan.task is not None:
            diagnostics["task_commands"] = [c.command for c in turn_plan.task.commands]

        # 2. 利用校验器校验 LLM 输出的 TurnPlan 是否合法
        validated = self.turn_plan_validator.validate(turn_plan, state, flow_list, intents)
        diagnostics["validation_passed"] = validated.valid
        if not validated.valid:
            diagnostics["clarify_reason"] = validated.reason.value

        logger.debug("TurnPlan 校验结果: valid=%s, tracks=%s",
                     validated.valid, turn_plan.activated_tracks())

        # 3. 判断校验结果 —— 校验失败则走意图澄清
        if not validated.valid:
            logger.info("意图澄清: reason=%s, sender_id=%s", validated.reason.value, state.sender_id)
            await telemetry.record_clarify()
            await telemetry.record_track("clarify")
            return await self.clarify_responder.respond(validated.reason, state), diagnostics

        # 4. 校验通过，根据 TurnPlan 路由到对应的处理轨道
        if turn_plan.task is not None:
            logger.info("路由到 Task 轨道: sender_id=%s, commands=%s",
                        state.sender_id, [c.command for c in turn_plan.task.commands])
            await telemetry.record_track("task")

            # 记录流程启动和槽位
            for cmd in turn_plan.task.commands:
                if isinstance(cmd, StartedFlowCommand):
                    await telemetry.record_flow_start(cmd.flow)
                elif isinstance(cmd, SetSlotsCommand):
                    diagnostics["slots_filled"] = cmd.slots
                    for slot_name in cmd.slots:
                        await telemetry.record_slot(True)

            # 记录当前流程状态
            if state.active_task is not None:
                diagnostics["flow_name"] = state.active_task.flow_id
                diagnostics["flow_step"] = state.active_task.step_id

            return await self.task_handler.hand(state, turn_plan.task.commands), diagnostics
        elif turn_plan.knowledge is not None:
            logger.info("路由到 Knowledge 轨道: sender_id=%s, intents=%s",
                        state.sender_id, turn_plan.knowledge.intents)
            await telemetry.record_track("knowledge")
            return await self.knowledge_handler.hand(state, turn_plan.knowledge.intents), diagnostics
        else:
            logger.info("路由到 ChitChat 轨道: sender_id=%s", state.sender_id)
            await telemetry.record_track("chitchat")
            return await self.chitchat_handler.hand(state), diagnostics

    async def _hand_obj_msg(self,
                            obj_msg: FocusedObject,
                            state: DialogueState,
                            flow_list: FlowsList) -> list[BotMessage]:
        """
        处理对象消息（卡片点击消息）

        卡片点击的三种处理场景：
        1. 卡片恰好对应流程当前正在收集的槽位
           → 构造 SetSlotsCommand，将卡片数据填入槽位，继续推进流程后续步骤
        2. 卡片与槽位不匹配，但存在活跃流程
           → 不生成槽位命令，继续处理流程的当前 step（例如重新收集当前槽位）
        3. 没有活跃流程，用户随意点击卡片
           → 触发意图澄清，询问用户想做什么

        :param obj_msg: 卡片点击产生的焦点对象（如订单卡片、专辑卡片）
        :param state: 对话状态
        :param flow_list: 所有已注册的流程
        :return: 机器人回复消息列表
        """

        # 1. 尝试将卡片对象解析为槽位命令（SetSlotsCommand）
        #    根据卡片类型（order/album）映射到对应的槽位字段（order_number/album_id）
        command = self._resolve_object_command(
            obj_message=obj_msg,
            state=state,
            flows=flow_list,
        )

        # 2. 如果能构建成功槽位命令 → 推进流程，填入槽位后继续下一步
        if command:
            return  await self.task_handler.hand(state, commands=[command])

        # 3. 无法构建槽位命令，需要进一步判断
        # 3.1 存在活跃流程（但卡片不匹配当前槽位）→ 继续处理流程的当前 step
        if state.active_task is not None:
            return await self.task_handler.hand(state, commands=[])

        # 3.2 没有活跃流程 → 用户随意点击了卡片，触发意图澄清
        return await self.clarify_responder.respond(reason=ClarifyReason.MISSING_FOCUSED_OBJECT, state=state)

    def _resolve_object_command(self,
                                obj_message: FocusedObject,
                                state: DialogueState,
                                flows: FlowsList) -> Command | None:
        """
        根据卡片类型将焦点对象解析为槽位填充命令

        卡片类型到槽位字段的映射：
        - 类型 "order"（订单卡片） → 映射到槽位 "order_number"
        - 类型 "album"（专辑卡片） → 映射到槽位 "album_id"

        只有在以下条件全部满足时才会生成命令：
        1. 存在活跃的业务流程
        2. 该流程定义中包含对应槽位字段
        3. 该槽位尚未被填充（防止重复填充）
        4. 当前步骤正在收集该槽位

        :param obj_message: 卡片焦点对象（含 type 和 id）
        :param state: 对话状态（获取当前活跃流程）
        :param flows: 所有流程定义
        :return: SetSlotsCommand 或 None（无法构建时）
        """

        # 1. 根据卡片类型映射到对应槽位

        # 1.1 订单类型卡片 → 映射到 order_number 槽位
        if obj_message.type == "order":

            if self._try_build_slots_command(state, flows, "order_number"):
                return SetSlotsCommand(command="set_slots", slots={"order_number": obj_message.id})

            return None

        # 1.2 专辑类型卡片 → 映射到 album_id 槽位
        if obj_message.type == "album":
            if self._try_build_slots_command(state, flows, "album_id"):
                return SetSlotsCommand(command="set_slots", slots={"album_id": obj_message.id})
            return None

        # 1.3 不支持的其他卡片类型 → 无法构建命令
        return None

    def _try_build_slots_command(self,
                                 state: DialogueState,
                                 flows: FlowsList,
                                 slot_name: str) -> bool:
        """
        防御性检查：判断能否为指定槽位构建填充命令

        四层防御检查：
        1. 是否存在活跃的业务流程（active_task 不为 None）
        2. 是否能在流程注册表中找到对应的流程定义（防止 flow_id 指向了不存在的流程）
        3. 该槽位是否已经填写过（幂等性校验，防止重复填充同一个槽位）
        4. 当前流程的步骤中是否有一个 CollectFlowStep 正在收集该槽位
           （确保用户点击的卡片正好是系统当前正在等待的字段）

        :param state: 对话状态
        :param flows: 所有流程定义
        :param slot_name: 待填充的槽位名（如 "order_number"、"album_id"）
        :return: True 表示可以构建槽位命令，False 表示不满足条件
        """

        # 1. 判断当前是否有活跃的业务流程
        activated_task = state.active_task
        if activated_task is None:
            return False

        # 2. 防御性代码：确保 flow_id 指向的流程定义确实存在
        flow = flows.get_flow_by_id(activated_task.flow_id)
        if flow is None:
            return False

        # 3. 槽位幂等性校验 —— 已填过的槽位不再重复填充
        if activated_task.slots.get(slot_name):
            return False

        # 4. 判断用户点击的卡片是否对应到当前步骤正在收集的槽位
        #    遍历流程的所有步骤，查找是否有 CollectFlowStep 的 slot_name 与当前卡片匹配
        for step in flow.steps:
            if isinstance(step, CollectFlowStep) and step.slot_name == slot_name:
                return True

        return False
