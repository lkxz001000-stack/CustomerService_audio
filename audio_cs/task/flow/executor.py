"""
流程执行引擎。

核心职责：沿着 YAML 定义的流程步骤图推进执行，直到遇到 action_listen 时暂停。

设计要点：
1. 双层循环结构：
   - 外层（execute_flow）：循环执行 action 步骤，遇到 action_listen 时退出
   - 内层（_advance_flow_util_action）：沿 Link 遍历非 action 步骤，直到找到下一个 action
2. CollectFlowStep 双入口：
   - 第一次进入：触发 system_collect_information 系统流程（询问用户）
   - 第二次进入：验证用户填写的槽位值
3. 条件评估：使用 Python eval() 在受限命名空间中计算条件表达式
"""

import logging
from dataclasses import asdict

from audio_cs.domain.messages import BotMessage
from audio_cs.domain.state import DialogueState
from audio_cs.task.action.base import ActionCall, ActionResult
from audio_cs.task.action.runner import ActionRunner
from audio_cs.task.flow.flows import FlowsList
from audio_cs.task.flow.links import FlowStepStaticLink, FlowStepFallbackLink, FlowStepConditionLink
from audio_cs.task.flow.steps import FlowStep, StartFlowStep, EndFlowStep, ActionFlowStep, CollectFlowStep
from audio_cs.domain.contexts import CollectedSystemContext

logger = logging.getLogger(__name__)


class FlowExecutor:
    """流程执行器：推进业务/系统流程，直到需要用户输入时暂停。"""

    async def execute_flow(self,
                           state: DialogueState,
                           flow_list: FlowsList,
                           action_runner: ActionRunner) -> list[BotMessage]:
        """
        执行流程主循环。

        外层循环：不断推进流程，执行遇到的每个 Action 步骤。
        当遇到 action_listen 时退出循环，将控制权交还给用户。
        其他 Action（action_response、action_xxx）会立即执行并继续推进。

        参数:
            state: 当前对话状态
            flow_list: 全部流程定义
            action_runner: 动作执行器

        返回:
            list[BotMessage]: 本轮产生的所有回复消息
        """
        final_messages = []
        # 外层循环：持续执行 action 步骤，直到遇到 action_listen
        while True:
            # 1. 推进流程，定位到下一个 Action 步骤
            action_call: ActionCall = self._advance_flow_util_action(state, flow_list)
            logger.debug("流程步骤: action=%s, flow_id=%s, step_id=%s",
                         action_call.action_name,
                         state.current_activating_task().flow_id if state.current_activating_task() else None,
                         state.current_activating_task().step_id if state.current_activating_task() else None)

            # 2. 判断 action 类型
            if action_call.action_name == "action_listen":
                logger.debug("流程暂停等待用户输入")
                break
            else:
                # 执行 action（action_response 或 action_xxx）
                action_result: ActionResult = await action_runner.run(action_call, state)
                final_messages.extend(action_result.messages)  # 收集回复消息
                state.set_slots(action_result.slot_updates)  # 更新槽位值
        return final_messages

    def _advance_flow_util_action(self,
                                  state: DialogueState,
                                  flow_list: FlowsList) -> ActionCall:
        """
        推进流程直到找到下一个 Action 步骤（内层循环）。

        沿步骤图遍历：StartFlowStep → EndFlowStep → 沿 Link 跳转，
        直到遇到 ActionFlowStep（返回其 ActionCall）或 CollectFlowStep（可能返回 ActionCall）。

        如果当前没有激活的任务，返回 action_listen（无任务可执行）。

        参数:
            state: 当前对话状态
            flow_list: 全部流程定义

        返回:
            ActionCall: 下一个要执行的动作
        """
        while True:
            # 1. 获取当前激活的任务（系统流程优先）
            current_activating_task = state.current_activating_task()
            if current_activating_task is None:
                # 没有任何激活的流程，返回暂停信号
                return ActionCall(action_name="action_listen")

            # 2. 获取当前任务所在的流程对象
            flow_id = current_activating_task.flow_id
            flow = flow_list.get_flow_by_id(flow_id)

            # 3. 获取当前步骤对象
            step = flow.get_step_by_id(current_activating_task.step_id)

            # 4. 执行该步骤
            action_call: ActionCall | None = self._run_step(state, step, flow_list)

            # 5. 如果步骤返回了 ActionCall，交给外层循环执行
            if action_call is not None:
                return action_call
            # 否则（步骤返回 None），继续内层循环遍历下一步

    def _run_step(self,
                  state: DialogueState,
                  step: FlowStep,
                  flow_list: FlowsList) -> ActionCall | None:
        """
        根据步骤类型分发执行。

        返回:
            ActionCall | None: Action 步骤返回 ActionCall；Start/End/Collect 可能返回 None
        """
        if isinstance(step, StartFlowStep):
            return self._run_start_step(state, step)
        elif isinstance(step, EndFlowStep):
            return self._run_end_step(state)
        elif isinstance(step, ActionFlowStep):
            return self._run_action_step(state, step)
        elif isinstance(step, CollectFlowStep):
            return self._run_collect_step(state, step, flow_list)
        else:
            pass

    def _run_start_step(self,
                        state: DialogueState,
                        step: StartFlowStep) -> None:
        """执行起始步骤：仅推进到下一步（无业务逻辑）。"""
        self._advance_flow_step(state, step)
        return None

    def _advance_flow_step(self, state: DialogueState, step: FlowStep):
        """
        沿 Link 推进步骤：选择下一个 step_id 并更新到当前任务上下文。

        这样内层循环会自动流向下一步骤。
        """
        step_id: str = self._select_step_id(state, step)
        state.current_activating_task().step_id = step_id

    def _select_step_id(self, state: DialogueState, step: FlowStep) -> str:
        """
        根据 Link 类型选择下一个步骤 ID。

        优先级：StaticLink > ConditionLink > FallbackLink
        遍历所有 Link，静态链接直接返回，条件链接评估通过后返回。

        参数:
            state: 当前对话状态
            step: 当前步骤

        返回:
            str: 下一个步骤的 ID
        """
        for link in step.next:
            if isinstance(link, FlowStepStaticLink):
                return link.target  # 无条件跳转

            if isinstance(link, FlowStepFallbackLink):
                return link.target  # 兜底跳转

            if isinstance(link, FlowStepConditionLink):
                # 条件链接：评估 Python 表达式决定是否走此分支
                if self._eval_condition(state, link.condition):
                    return link.target

        return "not exist link"  # 正常情况不会到达此处

    def _eval_condition(self,
                        state: DialogueState,
                        condition: str) -> bool:
        """
        在受限命名空间中计算条件表达式。

        eval 的安全说明：此处 eval 的 __builtins__ 被禁用（空字典），
        只能访问显式传入的 slots 和 context 变量，无法执行任意代码。

        参数:
            state: 当前对话状态
            condition: Python 条件表达式（如 "slots.get('order_status') == 'paid'"）

        返回:
            bool: 条件是否成立
        """
        data = {
            "slots": state.active_task.slots,  # 槽位值（供条件表达式使用）
            "context": asdict(state.active_system_task) if state.active_system_task else {}
        }
        # eval(expression, globals={}, locals=data)：禁用内置函数，仅暴露 data 中的变量
        return eval(condition, {}, data)

    def _run_end_step(self, state: DialogueState) -> None:
        """
        执行结束步骤：清理当前任务。

        优先结束系统流程（如果有），否则结束业务流程。
        """
        if state.active_system_task:
            state.end_activating_system_task()
        elif state.active_task:
            state.end_activating_task()
        else:
            pass
        return None

    def _run_action_step(self,
                         state: DialogueState,
                         step: ActionFlowStep) -> ActionCall:
        """执行动作步骤：推进到下一步，然后构建并返回 ActionCall。"""
        # 1. 先推进步骤（流程继续前进）
        self._advance_flow_step(state, step)
        # 2. 构建 ActionCall 交给外层循环执行
        return self._build_action_call(state, step)

    def _build_action_call(self, state, step):
        """
        构建 ActionCall 对象。

        如果 action_kwargs 是字符串（如 "context.response"），
        则从当前系统任务上下文中提取对应的值。
        """
        action_name = step.action
        action_kwargs = step.args

        if isinstance(action_kwargs, str):
            # 字符串格式说明需要从上下文中提取（如 "context.response" → 系统任务上下文的 response 字段）
            action_kwargs = asdict(state.active_system_task)[action_kwargs.split(".")[1]]

        return ActionCall(action_name=action_name, action_kwargs=action_kwargs)

    def _run_collect_step(self,
                          state: DialogueState,
                          step: CollectFlowStep,
                          flow_list: FlowsList):
        """
        执行信息收集步骤（双入口机制）。

        第一次进入（槽位未填写）：
            → 激活 system_collect_information 系统流程，等待用户输入
            → 返回 None（内层循环继续，系统流程开始执行）

        第二次进入（槽位已有值）：
            → 如果配置了校验规则且校验失败，移除槽位值并要求重新填写
            → 如果校验通过或无校验，推进到下一步

        参数:
            state: 当前对话状态
            step: Collect 步骤
            flow_list: 流程定义列表

        返回:
            ActionCall | None: 校验失败时返回 action_response；否则返回 None
        """
        # 预处理：尝试从卡片消息（focused_object）自动填充槽位
        self._try_to_fill_slot_from_focused_object(state, step)

        if state.active_task.slots.get(step.slot_name):
            # === 第二次进入：槽位已有值，进行校验 ===
            if step.validate:
                # 执行校验条件
                if self._eval_condition(state, step.validate.condition):
                    # 校验通过 → 推进流程
                    self._advance_flow_step(state, step)
                    return None
                else:
                    # 校验失败 → 移除错误值，返回错误提示
                    state.remove_slot(step.slot_name)
                    if step.validate.failure_response:
                        return ActionCall(
                            action_name="action_response",
                            action_kwargs=asdict(step.validate.failure_response)
                        )
                    else:
                        return ActionCall(
                            action_name="action_response",
                            action_kwargs={"text": "你填写的信息有误，请您重新输入！"}
                        )
            else:
                # 无校验规则 → 直接推进
                self._advance_flow_step(state, step)
                return None
        else:
            # === 第一次进入：槽位为空，激活收集信息的系统流程 ===
            state.start_active_system_task(CollectedSystemContext(
                flow_id="system_collect_information",
                step_id=flow_list.get_flow_by_id("system_collect_information").get_start_step().id,
                response=asdict(step.response),
                slot_name=step.slot_name
            ))
            return None

    def _try_to_fill_slot_from_focused_object(self, state: DialogueState, step: CollectFlowStep):
        """
        尝试从用户点击的卡片消息中自动填充槽位。

        如果当前收集的槽位是 order_number 且用户刚点击了订单卡片，
        或者收集 album_id 且用户刚点击了专辑卡片，则自动将卡片 ID 填入槽位。
        """
        if state.focused_object is None:
            return
        if step.slot_name == 'order_number' and state.focused_object.type == "order":
            state.set_slots({step.slot_name: state.focused_object.id})
        if step.slot_name == "album_id" and state.focused_object.type == "album":
            state.set_slots({step.slot_name: state.focused_object.id})


if __name__ == '__main__':
    condtion_str = "context.get('reason') == 'clarification_rejected'"
    data = {
        "context": {
            "reason": "clarification_rejected"
        },
        "slots": {
            "order_number": "A10001"
        }
    }
    print(eval(condtion_str, {}, data))
