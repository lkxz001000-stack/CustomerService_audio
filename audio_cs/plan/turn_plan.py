"""
TurnPlan 层：LLM 输出的轮次规划结果及其子结构。

层次关系（从外到内）：
  TurnPlan                     — 本轮规划的顶层容器，LLM 输出的最外层 JSON
    ├── TaskTurnPlan           — 任务轨道子规划：包含若干条 Command（命令列表）
    ├── KnowledgeTurnPlan      — 知识检索轨道子规划：包含若干条意图 ID 列表
    └── ChitChatTurnPlan       — 闲聊轨道子规划：包含闲聊响应文本

TurnPlan 三条轨道互斥（LLM 应只激活其中一条），校验由 TurnPlanValidator 执行。

ClarifyReason 枚举定义校验失败的具体原因，由校验器返回给上层，
上层据此构造"澄清意图"的系统回复消息。

TurnPlanValidateResult 是校验结果的简单 DTO（valid + reason）。
"""

from dataclasses import dataclass, field
from typing import Any
from enum import Enum

from audio_cs.task.command.commands import Command


@dataclass
class TaskTurnPlan:
    """
    任务轨道（业务轨道）的子规划。

    包含一条或多条 Command（命令），由 CommandProcessor 按顺序执行。
    典型命令：start_flow（开启流程）、set_slots（填充槽位）、cancel_flow（取消流程）、resume_flow（恢复流程）。

    :ivar commands: LLM 输出的命令列表，按数组顺序执行
    """
    commands: list[Command] = field(default_factory=list)

    @classmethod
    def from_dict(cls, task_data: dict[str, Any]) -> "TaskTurnPlan":
        """从 LLM 输出的 task JSON 片段反序列化，解析嵌套的 Command 列表"""
        return cls(
            commands=[Command.from_dict(task_dict) for task_dict in task_data.get('commands', [])]
        )


@dataclass
class KnowledgeTurnPlan:
    """
    知识检索轨道的子规划。

    包含一组知识意图 ID 字符串（如 ["order_info", "product_info"]）。
    每个意图 ID 必须在 KnowledgeIntent 注册表中存在，否则校验失败。

    :ivar intents: LLM 输出的知识意图 ID 列表
    """
    intents: list[str]

    @classmethod
    def from_dict(cls, knowledge_data: dict[str, Any]) -> "KnowledgeTurnPlan":
        """从 LLM 输出的 knowledge JSON 片段反序列化"""
        return cls(intents=knowledge_data.get('intents', []))


@dataclass
class ChitChatTurnPlan:
    """
    闲聊轨道的子规划。

    结构最简单：仅包含一段 LLM 生成的闲聊回复文本。
    闲聊轨道不参与校验（校验器直接放行）。

    :ivar chat: LLM 生成的闲聊回复字符串
    """
    chat: str


@dataclass
class TurnPlan:
    """
    LLM 输出的本轮规划顶层容器（对应 LLM 返回的最外层 JSON）。

    三条轨道（task / knowledge / chitchat）最多只有一条非 None 时才是合法的。
    如果 LLM 返回了多条轨道，校验器会以 MULTIPLE_TRACKS 拒绝。

    :ivar task: 任务轨道子规划，None 表示未激活此轨道
    :ivar knowledge: 知识检索轨道子规划，None 表示未激活此轨道
    :ivar chitchat: 闲聊轨道子规划，None 表示未激活此轨道
    """
    task: TaskTurnPlan | None = None
    knowledge: KnowledgeTurnPlan | None = None
    chitchat: ChitChatTurnPlan | None = None

    @classmethod
    def from_dict(cls, turn_plan_data: dict[str, Any]) -> "TurnPlan":
        """从 LLM 输出的完整 JSON 字典反序列化为 TurnPlan，自动解析三条子轨道"""
        return cls(
            task=TaskTurnPlan.from_dict(turn_plan_data['task']) if turn_plan_data.get('task') else None,
            knowledge=KnowledgeTurnPlan.from_dict(turn_plan_data['knowledge']) if turn_plan_data.get(
                'knowledge') else None,
            chitchat=ChitChatTurnPlan(chat=turn_plan_data.get('chitchat')) if turn_plan_data.get('chitchat') else None,
        )

    def activated_tracks(self):
        """
        返回本轮激活的轨道名称列表。

        用于校验器判断：列表为空 → MISSING_TRACK；列表长度 > 1 → MULTIPLE_TRACKS。

        :return: 轨道名称字符串列表，如 ["task"]、["knowledge"]、["chichat"]
        """
        tracks = []

        if self.task is not None:
            tracks.append("task")
        if self.knowledge is not None:
            tracks.append("knowledge")
        if self.chitchat is not None:
            tracks.append("chichat")

        return tracks


class ClarifyReason(Enum):
    """
    校验失败原因枚举。

    由 TurnPlanValidator 在校验不通过时返回，每种枚举值对应一种具体的失败场景。
    上层使用方（如 DialogueEngine）根据 reason 构造"澄清意图"的系统回复消息，
    引导用户提供更明确的信息。

    分为两大类：
      - 轨道层级校验失败（MISSING_TRACK, MULTIPLE_TRACKS）
      - 轨道内部校验失败（任务轨道 x4, 知识轨道 x3）
    """
    # ---- 轨道层级校验失败 ----
    MISSING_TRACK = "missing_track"
    """LLM 未命中任何轨道：三条轨道全部为空，无法判断用户意图"""

    MULTIPLE_TRACKS = "multiple_tracks"
    """LLM 同时激活了多条轨道：例如同时输出 task 和 knowledge，违反互斥约束"""

    # ---- 任务轨道内部校验失败 ----
    MISSING_TASK_COMMANDS = "missing_task_commands"
    """任务轨道被激活但 commands 列表为空：未生成任何命令"""

    INVALID_TASK_COMMANDS = "invalid_task_commands"
    """命令类型不在白名单中：出现了不支持的 Command 子类型"""

    MULTIPLE_TASK_FLOWS = "multiple_task_flows"
    """LLM 意图同时开启多个业务流程：系统不支持同一轮启动多个流程"""

    UNKNOWN_TASK_FLOW = "unknown_task_flow"
    """LLM 指定的流程 ID 在 FlowList 中不存在：可能是幻觉或配置不一致"""

    # ---- 知识轨道内部校验失败 ----
    MISSING_KNOWLEDGE_INTENT = "missing_knowledge_intent"
    """知识轨道被激活但 intents 列表为空：未生成任何知识查询意图"""

    MISSING_FOCUSED_OBJECT = "missing_focused_object"
    """知识意图要求聚焦对象（如需要先点击某张卡片），但当前对话状态中无聚焦对象"""

    OBJECT_REQUIRES_INTENT = "object_requires_intent"
    """聚焦对象存在但不匹配知识意图所要求的对象类型：如用户点击了订单卡片但尝试查询商品信息"""


@dataclass
class TurnPlanValidateResult:
    """
    TurnPlan 校验结果 DTO。

    校验通过时 valid=True, reason=None；
    校验失败时 valid=False, reason 为 ClarifyReason 枚举值。

    :ivar valid: 校验是否通过
    :ivar reason: 失败原因（校验通过时为 None）
    """

    valid: bool  # 校验是否通过：True=合法可执行, False=不合法需要澄清
    reason: ClarifyReason | None = None  # 失败原因枚举，valid=True 时为 None
