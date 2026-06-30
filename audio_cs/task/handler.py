"""
任务轨道处理器（TaskHandler）模块。

职责：作为任务轨道的编排层，串联"命令处理"和"流程执行"两个阶段，
将 LLM 规划的命令列表转化为实际的 Bot 回复消息。

在整个架构中的位置：
  DialogueEngine → TurnPlanner → TurnPlanValidator → TaskHandler → BotMessage[]
                                                       ├── CommandProcessor（命令应用）
                                                       └── FlowExecutor（流程推进）
"""

import logging
from audio_cs.domain.messages import BotMessage
from audio_cs.domain.state import DialogueState
from audio_cs.task.action.runner import ActionRunner
from audio_cs.task.command.commands import Command
from audio_cs.task.flow.flows import FlowsList
from audio_cs.task.command.processor import CommandProcessor
from audio_cs.task.flow.executor import FlowExecutor

logger = logging.getLogger(__name__)


class TaskHandler:
    """
    任务轨道处理器（编排层）。

    职责：接收 LLM 生成的命令列表，执行两阶段处理流水线：

    阶段1 —— 命令应用（command_processor.run）：
      将命令逐条应用到 DialogueState，完成业务流程的状态迁移
      （启动/恢复/取消流程、填充槽位、激活系统流程开场白上下文）

    阶段2 —— 流程推进（flow_executor.execute_flow）：
      遍历活跃的业务流程和系统流程，执行当前步骤的动作（Action），
      推进到下一步骤，收集所有步骤产出的 Bot 回复消息

    依赖注入：
      - flow_list: 所有业务流程定义（从 YAML 加载）
      - command_processor: 命令处理器（CommandProcessor 单例）
      - executor: 流程执行器（FlowExecutor 单例）
      - action_runner: 动作执行器（ActionRunner，执行 HTTP 调用等）
    """

    def __init__(self,
                 flow_list: FlowsList,
                 command_processor: CommandProcessor,
                 executor: FlowExecutor,
                 action_runner: ActionRunner
                 ):
        """
        初始化任务轨道处理器。

        :param flow_list: 系统中所有业务流程定义
        :param command_processor: 命令处理器实例
        :param executor: 流程执行器实例
        :param action_runner: 动作执行器实例
        """
        self.flow_list = flow_list
        self.command_processor = command_processor
        self.flow_executor = executor
        self.action_runner = action_runner

    async def hand(self,
                   state: DialogueState,
                   commands: list[Command]) -> list[BotMessage]:
        """
        任务轨道入口方法。

        两阶段处理流水线：
          阶段1 —— 命令应用：将 LLM 的命令列表应用到对话状态
            command_processor.run() 依次处理 commands 中的每条命令，
            修改 state 中的 active_task / active_system_task / interrupted_active_tasks 等字段

          阶段2 —— 流程推进：执行活跃流程的当前步骤，收集 Bot 回复
            flow_executor.execute_flow() 遍历业务流程和系统流程的当前步骤，
            通过 action_runner 执行步骤中的 Action（如 HTTP 查询），
            返回所有步骤产出的 BotMessage 列表

        :param state: 当前对话状态（会被 command_processor 修改）
        :param commands: LLM 生成的命令列表
        :return: Bot 回复消息列表（业务流程和系统流程的步骤回复）
        """
        # ===== 阶段1：命令应用 —— 将命令写入对话状态 =====
        self.command_processor.run(state, self.flow_list, commands)
        logger.debug("命令应用完成: active_task=%s, active_system_task=%s",
                     state.active_task.flow_id if state.active_task else None,
                     state.active_system_task.flow_id if state.active_system_task else None)

        # ===== 阶段2：流程推进 —— 执行活跃流程步骤，收集回复 =====
        bot_msgs: list[BotMessage] = await self.flow_executor.execute_flow(state, self.flow_list, self.action_runner)
        logger.debug("流程推进完成: 产出 %d 条回复消息", len(bot_msgs))

        return bot_msgs
