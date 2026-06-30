"""
命令处理器（CommandProcessor）模块。

职责：将 LLM 生成的命令列表逐条应用到对话状态上，驱动业务流程的状态机变更。

命令与对话状态的交互关系：
  StartedFlowCommand  → 激活业务流程 + 激活"开始"系统流程开场白
  ResumedFlowCommand  → 从中断栈恢复业务流程 + 激活"恢复"系统流程开场白
  CancelFlowCommand   → 清空所有流程 + 激活"取消"系统流程开场白
  SetSlotsCommand     → 将 LLM 提取的槽位值写入当前业务流程上下文

核心设计要点：
  - 中断栈：当用户从流程A切换到流程B时，流程A不丢失，而是压入中断栈等待恢复
  - 系统流程：每个业务操作都伴随一个"系统流程"用于生成开场白（如"好的，正在为您查询订单..."）
  - 双轨并行：业务流程（用户可见的业务逻辑）+ 系统流程（客服开场白），两者独立推进
"""

import logging
from audio_cs.domain.state import DialogueState
from audio_cs.task.flow.flows import FlowsList
from audio_cs.task.command.commands import Command, StartedFlowCommand, ResumedFlowCommand, CancelFlowCommand, \
    SetSlotsCommand
from audio_cs.domain.contexts import StartedSystemContext, InterruptedSystemContext, CanceledSystemContext, \
    ResumedSystemContext, TaskContext

logger = logging.getLogger(__name__)


class CommandProcessor:
    """
    命令处理器。

    核心职责：将 TaskTurnPlan 中的命令列表逐条应用到 DialogueState 上，
    驱动业务流程的生命周期（启动/恢复/取消/槽位填充）以及对应的系统流程开场白。

    命令分发机制（_apply 方法）：
      通过 isinstance 检查命令类型，分派到四个处理方法：
        - StartedFlowCommand  → _process_start_flow()
        - SetSlotsCommand     → _process_slots_fill()
        - ResumedFlowCommand  → _process_resume_flow()
        - CancelFlowCommand   → _process_cancel_flow()

    关键状态变量（均在 DialogueState 中）：
      - active_task              — 当前活跃的业务流程上下文（TaskContext）
      - active_system_task       — 当前活跃的系统流程上下文（StartedSystemContext 等）
      - interrupted_active_tasks — 中断的业务流程栈（列表，后进先出）
    """

    def run(self,
            state: DialogueState,
            flow_list: FlowsList,
            commands: list[Command]):
        """
        命令列表执行入口。

        遍历 LLM 生成的命令列表，逐条应用到对话状态。
        命令按 TurnPlan 中的数组顺序执行，前一条命令的状态变更会影响后续命令。

        :param state: 当前对话状态（会被修改）
        :param flow_list: 系统中所有业务流程
        :param commands: LLM 生成的命令列表
        """
        for command in commands:
            logger.debug("执行命令: %s", command.command)
            self._apply(command, state, flow_list)

    def _apply(self,
               command: Command,
               state: DialogueState,
               flow_list: FlowsList
               ):
        """
        命令分发器。

        根据命令的具体类型（isinstance 检查），分派到对应的处理方法。
        未识别的命令类型静默忽略（pass）。

        :param command: 待执行的命令
        :param state: 当前对话状态
        :param flow_list: 系统中所有业务流程
        """
        if isinstance(command, StartedFlowCommand):
            self._process_start_flow(command, state, flow_list)
        elif isinstance(command, SetSlotsCommand):
            self._process_slots_fill(command, state)
        elif isinstance(command, ResumedFlowCommand):
            self._process_resume_flow(command, state, flow_list)
        elif isinstance(command, CancelFlowCommand):
            self._process_cancel_flow(state, flow_list)
        else:
            pass

    def _process_slots_fill(self,
                            command: SetSlotsCommand,
                            state: DialogueState):
        """
        处理槽位填充命令。

        职责：将 LLM 从用户消息中提取的槽位键值对写入当前业务流程上下文。
        例如：用户说"订单号是 A10001" → LLM 提取 slots={"order_id": "A10001"} → 写入 state.active_task.slots

        实现极简：直接委托 state.set_slots() 完成写入。

        :param command: 包含 slots 字典的 SetSlotsCommand
        :param state: 当前对话状态
        """
        state.set_slots(command.slots)  # 将槽位写入当前活跃业务流程上下文
        logger.debug("槽位填充: %s", command.slots)

    def _process_cancel_flow(self,
                             state: DialogueState,
                             flow_list: FlowsList):
        """
        处理取消流程命令。

        三阶段处理流程：
          阶段1 —— 获取取消系统流程：从 FlowList 中查找 "system_task_canceled" 流程及其起始步骤
          阶段2 —— 记录被取消的业务流程信息：保存当前活跃业务流程的 ID 和名称（用于开场白）
          阶段3 —— 清空 + 激活：
            a) 调用 state.end_activating_task() 清空所有流程（业务流程+系统流程）
            b) 激活取消系统流程（CanceledSystemContext），带上被取消流程的信息用于生成开场白

        典型开场白："已为您取消【订单查询】，还有什么可以帮您的？"

        :param state: 当前对话状态
        :param flow_list: 系统中所有业务流程
        """
        # ===== 阶段1：获取取消系统流程对象及其起始步骤 =====
        cancel_system_flow = flow_list.get_flow_by_id("system_task_canceled")
        start_step_id = cancel_system_flow.get_start_step().id

        # ===== 阶段2：保存被取消的业务流程信息（供系统流程开场白使用） =====
        active_task = state.active_task
        canceled_flow_id = active_task.flow_id
        canceled_flow_name = flow_list.get_flow_by_id(canceled_flow_id).flow_name

        # ===== 阶段3：清空所有流程，激活取消系统流程 =====
        # a) 清空业务流程和系统流程
        state.end_activating_task()

        # b) 激活取消系统流程，生成取消开场白
        state.start_active_system_task(CanceledSystemContext(
            flow_id="system_task_canceled",
            step_id=start_step_id,
            canceled_flow_id=canceled_flow_id,  # 被取消的业务流程ID
            canceled_flow_name=canceled_flow_name  # 被取消的业务流程名称
        ))

    def _process_start_flow(self,
                            command: StartedFlowCommand,
                            state: DialogueState,
                            flow_list: FlowsList):
        """
        处理启动流程命令（最复杂的业务逻辑方法）。

        五阶段处理流程：

        阶段1 —— 准备阶段：清空旧的系统流程（终结上一个开场白），获取要开启的业务流程对象

        阶段2 —— 分流判断：检查当前是否存在活跃的业务流程
          - 如果存在 → 进入阶段3（有活跃流程分支）
          - 如果不存在 → 进入阶段4（无活跃流程分支）

        阶段3 —— 有活跃业务流程时的处理（中断-切换场景）：
          a) 如果要开启的流程就是当前流程 → 不做任何操作（幂等处理）
          b) 如果不同 → 中断当前流程（压入中断栈），激活中断系统流程开场白
          c) 从中断栈查找要开启的流程，若找到则恢复，否则创建新的业务流程上下文

        阶段4 —— 无活跃业务流程时的处理（首次启动或恢复场景）：
          a) 从中断栈查找要开启的流程
          b) 若找到 → 恢复流程 + 激活"恢复"系统流程开场白（不重复说"开始"）
          c) 若未找到 → 创建新业务流程 + 激活"开始"系统流程开场白

        阶段5 —— 最终返回（隐式）：通过修改 state 对象产生副作用

        :param command: 包含要启动的流程 ID 的 StartedFlowCommand
        :param state: 当前对话状态（会被修改）
        :param flow_list: 系统中所有业务流程
        """
        # ============================================================
        # 阶段1：准备阶段
        # ============================================================
        # 1.1 清空当前系统流程（终结上一个系统流程的开场白）
        state.end_activating_system_task()

        # 1.2 获取要开启的业务流程对象
        start_flow_id = command.flow
        start_business_flow = flow_list.get_flow_by_id(start_flow_id)

        # ============================================================
        # 阶段2：分流判断 —— 当前是否有正在运行的业务流程？
        # ============================================================
        active_task = state.active_task

        # ============================================================
        # 阶段3：有活跃业务流程（中断-切换场景）
        # ============================================================
        if active_task is not None:

            # --- 情况A：幂等处理 —— 当前流程就是用户要开启的流程 ---
            if active_task.flow_id == start_flow_id:
                return  # 什么都不做，避免重复激活

            # --- 情况B：流程切换 —— 中断当前流程，跳转到新流程 ---
            # b1) 记录当前流程信息（供中断开场白使用）
            interrupted_flow_id = active_task.flow_id
            interrupted_flow_name = flow_list.get_flow_by_id(interrupted_flow_id).flow_name
            # b2) 将当前流程压入中断栈
            state.interrupted_activating_task()

            # b3) 从中断栈查找目标流程：如果之前已经中断过，直接恢复而不重新创建
            if not state.resumed_interrupted_business_task(flow_id=start_flow_id):
                # 栈中未找到，创建新的业务流程上下文
                state.start_active_business_task(TaskContext(
                    flow_id=start_flow_id,
                    step_id=start_business_flow.get_start_step().id
                ))

            # b4) 激活中断系统流程（告知用户：流程已切换）
            # 注意：无论是否创建新业务流程，都需要激活中断开场白
            interrupted_system_flow = flow_list.get_flow_by_id("system_task_interrupted")
            state.start_active_system_task(InterruptedSystemContext(
                flow_id="system_task_interrupted",
                step_id=interrupted_system_flow.get_start_step().id,
                interrupted_flow_id=interrupted_flow_id,        # 被中断的流程ID
                interrupted_flow_name=interrupted_flow_name,    # 被中断的流程名称
                started_flow_id=start_flow_id,                  # 新开启的流程ID
                started_flow_name=start_business_flow.flow_name # 新开启的流程名称
            ))

        # ============================================================
        # 阶段4：无活跃业务流程（首次启动 或 从空状态恢复）
        # ============================================================
        else:
            # --- 情况A：从中断栈中找到目标流程 → 恢复而非重新开始 ---
            # 优点：保留之前的槽位填充进度，避免用户重复填写信息
            if state.resumed_interrupted_business_task(flow_id=start_flow_id):
                resumed_system_flow = flow_list.get_flow_by_id("system_task_resumed")
                active_task = state.active_task
                # 激活"恢复"系统流程（开场白：继续之前的流程，而非从头开始）
                state.start_active_system_task(ResumedSystemContext(
                    flow_id="system_task_resumed",
                    step_id=resumed_system_flow.get_start_step().id,
                    resumed_flow_id=active_task.flow_id,
                    resumed_flow_name=flow_list.get_flow_by_id(active_task.flow_id).flow_name
                ))
                return

            # --- 情况B：栈中未找到 → 创建全新业务流程 + 激活"开始"系统流程 ---
            # 1) 创建新的业务流程上下文（从流程第一步开始）
            state.start_active_business_task(TaskContext(
                flow_id=start_flow_id,
                step_id=start_business_flow.get_start_step().id
            ))
            # 2) 激活"开始"系统流程（开场白："好的，正在为您查询订单..."）
            start_system_flow = flow_list.get_flow_by_id("system_task_started")
            state.start_active_system_task(
                StartedSystemContext(
                    flow_id="system_task_started",
                    step_id=start_system_flow.get_start_step().id,
                    started_flow_id=start_flow_id,
                    started_flow_name=start_business_flow.flow_name
                )
            )

    def _process_resume_flow(self,
                             command: ResumedFlowCommand,
                             state: DialogueState,
                             flow_list: FlowsList):
        """
        处理恢复流程命令。

        职责：从中断栈中恢复之前被中断的业务流程。

        两种使用场景：
          场景1：指定恢复 —— command.flow = "order_status"
            用户说"我想继续查订单状态" → LLM 输出指定流程ID
          场景2：自动恢复 —— command.flow = None
            用户说"我想继续之前的" → LLM 不指定流程ID，从栈顶恢复最近中断的流程

        处理流程：
          1. 获取要恢复的流程 ID（None 时取栈顶）
          2. 如果 flow 为 None 且栈为空 → 无从恢复，直接返回
          3. 如果当前有活跃流程 → 中断当前流程，恢复目标流程，激活中断系统流程
          4. 如果当前无活跃流程 → 直接恢复目标流程，激活恢复系统流程

        :param command: 包含可选流程 ID 的 ResumedFlowCommand
        :param state: 当前对话状态
        :param flow_list: 系统中所有业务流程
        """
        # ===== 步骤1：获取要恢复的业务流程 ID =====
        resumed_flow_id = command.flow

        # ===== 步骤2：边界检查 —— flow 为 None 且栈为空，无从恢复 =====
        if resumed_flow_id is None and not state.interrupted_active_tasks:
            return

        # ===== 步骤3：分流处理 —— 当前是否有活跃流程？ =====
        active_task = state.active_task

        # ----- 分支A：当前有活跃业务流程（需要先中断再恢复） -----
        if active_task is not None:
            # a) 确定要恢复的流程 ID：优先用命令中指定的，否则取栈顶（最近中断的）
            resumed_flow_id = resumed_flow_id or state.interrupted_active_tasks[-1].flow_id

            # b) 如果要恢复的流程就是当前流程 → 无需操作
            if active_task.flow_id == resumed_flow_id:
                return

            # c) 当前流程与目标流程不同 → 中断当前流程
            interrupted_flow_id = active_task.flow_id
            interrupted_flow_name = flow_list.get_flow_by_id(interrupted_flow_id).flow_name
            state.interrupted_activating_task()  # 当前流程压入中断栈

            # d) 从中断栈恢复目标流程
            if not state.resumed_interrupted_business_task(flow_id=resumed_flow_id):
                # 栈中未找到目标流程 → 撤销刚才的中断操作，放弃恢复
                state.resumed_interrupted_business_task()
                return

            # e) 激活中断系统流程（告知用户已从旧流程切换到恢复的流程）
            interrupted_system_flow = flow_list.get_flow_by_id("system_task_interrupted")
            state.start_active_system_task(InterruptedSystemContext(
                flow_id="system_task_interrupted",
                step_id=interrupted_system_flow.get_start_step().id,
                interrupted_flow_id=interrupted_flow_id,        # 被中断的旧流程ID
                interrupted_flow_name=interrupted_flow_name,    # 被中断的旧流程名称
                started_flow_id=resumed_flow_id,                # 恢复后的新流程ID
                started_flow_name=flow_list.get_flow_by_id(resumed_flow_id).flow_name
            ))

        # ----- 分支B：当前无活跃业务流程（直接从栈恢复） -----
        else:
            # a) 从中断栈恢复目标流程
            if not state.resumed_interrupted_business_task(flow_id=resumed_flow_id):
                return  # 栈中未找到，放弃

            # b) 激活"恢复"系统流程（开场白："好的，继续为您处理..."）
            resumed_system_flow = flow_list.get_flow_by_id("system_task_resumed")
            resumed_task = state.active_task
            state.start_active_system_task(ResumedSystemContext(
                flow_id="system_task_resumed",
                step_id=resumed_system_flow.get_start_step().id,
                resumed_flow_id=resumed_task.flow_id,                                              # 恢复的业务流程ID
                resumed_flow_name=flow_list.get_flow_by_id(resumed_task.flow_id).flow_name         # 恢复的业务流程名称
            ))
