"""
TurnPlan 校验器模块。

职责：对 LLM 输出的 TurnPlan 进行两阶段校验，确保 Plan 在语义和结构上合法可执行。

两阶段校验流程：
  第一阶段 — 轨道层级校验（validate 方法）
    1. 检查 LLM 是否命中了至少一条轨道（未命中 → MISSING_TRACK）
    2. 检查是否命中了多条轨道（多选 → MULTIPLE_TRACKS，三条轨道互斥）
    3. 唯一轨道通过后，进入第二阶段

  第二阶段 — 轨道内部校验
    - 任务轨道：四重校验（commands 是否存在、类型白名单、防止多流程启动、流程 ID 合法性）
    - 知识轨道：校验意图 ID 合法性、校验所需聚焦对象是否存在且类型匹配
    - 闲聊轨道：无需校验，直接放行
"""

import logging
from audio_cs.plan.turn_plan import TurnPlanValidateResult, TurnPlan, ClarifyReason
from audio_cs.domain.state import DialogueState
from audio_cs.task.flow.flows import FlowsList
from audio_cs.task.command.commands import StartedFlowCommand, CancelFlowCommand, ResumedFlowCommand, SetSlotsCommand
from audio_cs.knowledge.intents import KnowledgeIntent

logger = logging.getLogger(__name__)


class TurnPlanValidator:
    """
    TurnPlan 校验器。

    对 LLM 输出的 TurnPlan 执行两阶段校验：

    第一阶段 —— 轨道层级校验（validate 方法主流程）：
      1. 通过 activated_tracks() 获取 LLM 激活的轨道列表
      2. 轨道为空 → MISSING_TRACK：LLM 无法判断用户意图，需要澄清
      3. 轨道 >1 → MULTIPLE_TRACKS：三条轨道必须互斥，LLM 不能同时选多条
      4. 唯一轨道 → 进入第二阶段

    第二阶段 —— 轨道内部校验：
      - task 轨道 → _validate_task_track（四重校验）
      - knowledge 轨道 → _validate_knowledge_track（意图+聚焦对象校验）
      - chitchat 轨道 → 直接放行

    所有校验方法返回 TurnPlanValidateResult（valid + reason）。
    """

    def validate(self,
                 turn_plan: TurnPlan,
                 state: DialogueState,
                 flow_list: FlowsList,
                 intents: dict[str, KnowledgeIntent]
                 ) -> TurnPlanValidateResult:
        """
        TurnPlan 校验入口。

        两阶段校验：
          第一阶段（轨道层级）：检查轨道激活数量是否合法（1 条且仅 1 条）
          第二阶段（轨道内部）：根据轨道类型委派到对应的内部校验方法

        :param turn_plan: LLM 输出的轮次规划结果
        :param state: 当前对话状态（用于聚焦对象校验）
        :param flow_list: 系统中所有业务流程（用于流程 ID 合法性校验）
        :param intents: 知识意图注册表（用于意图 ID 合法性校验）
        :return: 校验结果（valid=True 可执行 / valid=False 需澄清）
        """
        # ===== 第一阶段：轨道层级校验 =====
        # 获取 turn_plan 中激活的轨道列表
        selected_tracks = turn_plan.activated_tracks()

        # 校验 1：轨道是否未命中（三条轨道全部为空）
        if not selected_tracks:
            logger.warning("TurnPlan 校验失败: 未命中任何轨道")
            return self.reject(reason=ClarifyReason.MISSING_TRACK)

        # 校验 2：轨道是否命中了多条（违反互斥约束）
        if len(selected_tracks) > 1:
            logger.warning("TurnPlan 校验失败: 多轨道冲突 tracks=%s", selected_tracks)
            return self.reject(reason=ClarifyReason.MULTIPLE_TRACKS)

        # ===== 第二阶段：轨道内部校验 =====
        # 此时确保只有唯一一条轨道，根据轨道类型委派
        selected_track = selected_tracks[0]

        # 子校验 1：任务轨道（业务轨道）—— 四重校验
        if selected_track == "task":
            return self._validate_task_track(turn_plan, flow_list)

        # 子校验 2：知识检索轨道 —— 意图 + 聚焦对象校验
        elif selected_track == "knowledge":
            return self._validate_knowledge_track(turn_plan, state, intents)

        # 子校验 3：闲聊轨道 —— 无需校验，直接放行
        return TurnPlanValidateResult(valid=True)

    def reject(self, reason: ClarifyReason) -> TurnPlanValidateResult:
        """
        构建校验失败的快捷方法。

        :param reason: ClarifyReason 枚举值，标明具体失败原因
        :return: valid=False 且附带 reason 的校验结果
        """
        return TurnPlanValidateResult(valid=False, reason=reason)

    def _validate_task_track(self,
                             turn_plan: TurnPlan,
                             flow_list: FlowsList) -> TurnPlanValidateResult:
        """
        任务轨道四重校验。

        校验 1 —— 命令存在性：commands 列表不能为空
          失败原因：MISSING_TASK_COMMANDS
          含义：LLM 激活了任务轨道但未生成任何命令，属于无效输出

        校验 2 —— 命令类型白名单：每条 command 必须是以下四种类型之一
          - StartedFlowCommand   (start_flow)
          - CancelFlowCommand    (cancel_flow)
          - ResumedFlowCommand   (resume_flow)
          - SetSlotsCommand      (set_slots)
          失败原因：INVALID_TASK_COMMANDS
          含义：LLM 输出了不被支持的命令类型，防止非法指令注入

        校验 3 —— 防止多流程启动：StartedFlowCommand 最多只能有一条
          失败原因：MULTIPLE_TASK_FLOWS
          含义：系统同时只能执行一个业务流程，LLM 不能在同轮启动多个

        校验 4 —— 流程 ID 合法性：如果有 StartedFlowCommand，其 flow 值必须在 FlowList 中存在
          失败原因：UNKNOWN_TASK_FLOW
          含义：LLM 可能产生了幻觉，指定了不存在的流程 ID
          注：如果没有 StartedFlowCommand（仅 SetSlots / CancelFlow / ResumeFlow），跳过此校验

        :param turn_plan: LLM 输出的 TurnPlan
        :param flow_list: 系统中所有业务流程
        :return: 校验结果
        """
        task_track = turn_plan.task

        # === 校验 1：命令存在性 —— commands 列表不能为空 ===
        if not task_track.commands:
            return self.reject(reason=ClarifyReason.MISSING_TASK_COMMANDS)

        # === 校验 2：命令类型白名单 —— 每条 command 必须是允许的四种类型之一 ===
        allowed_command = (StartedFlowCommand, CancelFlowCommand, ResumedFlowCommand, SetSlotsCommand)
        if not all(isinstance(command, allowed_command) for command in task_track.commands):
            return self.reject(reason=ClarifyReason.INVALID_TASK_COMMANDS)

        # === 校验 3：防止多流程启动 —— StartedFlowCommand 最多一条 ===
        started_flow_cmd = [start_cmd for start_cmd in task_track.commands if isinstance(start_cmd, StartedFlowCommand)]
        if len(started_flow_cmd) > 1:
            return self.reject(reason=ClarifyReason.MULTIPLE_TASK_FLOWS)

        # === 校验 4：流程 ID 合法性 —— 若有 StartedFlowCommand，验证其 flow ID ===
        # 注：如果没有 StartedFlowCommand（仅 SetSlots / CancelFlow / ResumeFlow），跳过此校验
        if started_flow_cmd:
            started_cmd = started_flow_cmd[0]
            flow_id = started_cmd.flow
            flow = flow_list.get_flow_by_id(flow_id)
            if flow is None:
                return self.reject(reason=ClarifyReason.UNKNOWN_TASK_FLOW)

        return TurnPlanValidateResult(valid=True)

    def _validate_knowledge_track(self,
                                  turn_plan: TurnPlan,
                                  state: DialogueState,
                                  intents: dict[str, KnowledgeIntent]):
        """
        知识轨道内部校验。

        校验 1 —— 意图存在性：intents 列表不能为空
          失败原因：MISSING_KNOWLEDGE_INTENT
          含义：LLM 激活了知识轨道但未提供任何知识查询意图

        校验 2 —— 聚焦对象匹配：如果某个知识意图要求聚焦对象（requires_object 不为 None），
          则当前对话状态中必须存在匹配的聚焦对象
          失败原因：MISSING_FOCUSED_OBJECT
          含义：用户需要先点击/选中某个界面对象（如订单卡片）才能执行此知识查询
          校验逻辑：
            - 如果 intent.requires_object 为 None，表示无需聚焦对象，跳过此意图
            - 如果 intent.requires_object 不为 None，则 state.focused_object 必须非空且类型匹配

        :param turn_plan: LLM 输出的 TurnPlan
        :param state: 当前对话状态（用于获取聚焦对象）
        :param intents: 知识意图注册表
        :return: 校验结果
        """
        knowledge_plan = turn_plan.knowledge

        # === 校验 1：意图存在性 —— intents 列表不能为空 ===
        if not knowledge_plan.intents:
            return self.reject(ClarifyReason.MISSING_KNOWLEDGE_INTENT)

        # === 校验 2：聚焦对象匹配 —— 逐意图检查 requires_object 约束 ===
        focused_object = state.focused_object
        for intent in knowledge_plan.intents:
            intent_meta = intents[intent]
            required_object = intent_meta.requires_object
            # 仅当意图要求聚焦对象时才进行校验
            if required_object is not None:
                # 聚焦对象必须存在且类型匹配
                if focused_object is None or focused_object.type != required_object:
                    return self.reject(ClarifyReason.MISSING_FOCUSED_OBJECT)

        return TurnPlanValidateResult(valid=True)






