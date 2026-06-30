"""
命令（Command）数据模型模块。

定义任务轨道中 LLM 输出的四种命令类型及其父类，LLM 的 JSON 输出通过 COMMAND_TO_CLASS
注册表自动映射为对应的 Python 数据类。

四种命令类型：
  1. StartedFlowCommand  — 开启新的业务流程（指定流程 ID）
  2. ResumedFlowCommand   — 恢复之前中断的业务流程（可指定流程 ID 或恢复最近中断的）
  3. CancelFlowCommand    — 取消当前正在执行的业务流程
  4. SetSlotsCommand      — 填充当前业务流程所需的槽位（键值对）

反序列化流程：
  LLM JSON → Command.from_dict() → 根据 command 字段查 COMMAND_TO_CLASS → 实例化对应子类
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class Command:
    """
    命令基类（抽象父类）。

    所有具体命令类型都继承自此基类。LLM 输出的 JSON 中通过 "command" 字段标识命令类型，
    from_dict 工厂方法据此分发到对应子类。

    实际使用中不应直接实例化 Command，而应使用其子类。

    :ivar command: 命令类型字符串，如 "start_flow"、"set_slots" 等
    """
    command: str

    @classmethod
    def from_dict(cls, command_data: dict[str, Any]) -> "Command":
        """
        命令反序列化工厂方法。

        根据 JSON 中的 'command' 字段值查找对应的数据类，然后实例化。
        映射关系由模块级常量 COMMAND_TO_CLASS 维护。

        示例：
          {'command': 'start_flow', 'flow': 'order_query'} → StartedFlowCommand(flow='order_query')
          {'command': 'set_slots', 'slots': {'order_id': 'A10001'}} → SetSlotsCommand(slots={...})

        :param command_data: LLM 输出的单条命令 JSON 字典
        :return: 对应的 Command 子类实例
        """
        command_type = command_data['command']
        clz = COMMAND_TO_CLASS.get(command_type)
        return clz(**command_data)


@dataclass
class StartedFlowCommand(Command):
    """
    启动流程命令。

    场景：用户表达了明确的业务需求，LLM 决定开启一个业务流程。
    示例：用户说"我想查一下我的订单状态" → LLM 输出 {"command": "start_flow", "flow": "order_status"}

    :ivar flow: 要开启的业务流程 ID，必须在 FlowList 中存在
    """
    flow: str  # 开启的业务流程流程ID


@dataclass
class ResumedFlowCommand(Command):
    """
    恢复流程命令。

    场景：用户之前中断了某个业务流程，现在想要继续。
    flow 为 None 时，表示恢复最近中断的业务流程（从栈顶取）；
    flow 不为 None 时，表示恢复指定的业务流程。

    示例：
      - {"command": "resume_flow"} → 恢复最近中断的流程
      - {"command": "resume_flow", "flow": "order_status"} → 恢复指定流程

    :ivar flow: 要恢复的业务流程 ID，None 表示恢复最近中断的
    """
    flow: str | None = None


@dataclass
class CancelFlowCommand(Command):
    """
    取消流程命令。

    场景：用户明确表示不想继续当前业务流程，要求取消。
    示例：用户说"我不查订单了" → LLM 输出 {"command": "cancel_flow"}

    flow 为 None 时取消当前活跃流程；不为 None 时可指定取消特定流程（预留参数）。

    :ivar flow: 要取消的业务流程 ID，None 表示取消当前活跃流程
    """
    flow: str | None = None


@dataclass
class SetSlotsCommand(Command):
    """
    填充槽位命令。

    场景：用户提供了业务流程所需的参数信息，LLM 提取并填充到槽位中。
    示例：
      - 用户说"我的订单号是A10001" → {"command": "set_slots", "slots": {"order_id": "A10001"}}
      - 用户说"退款原因是质量问题" → {"command": "set_slots", "slots": {"refund_reason": "质量问题"}}

    :ivar slots: 键值对字典，key 为槽位名称，value 为槽位值
    """
    slots: dict[str, Any]


# 命令类型注册表：LLM 输出的 command 字符串 → Python 数据类
# 新增命令类型时只需在此注册表中添加一行，Command.from_dict 即可自动支持
COMMAND_TO_CLASS: dict[str, type[Command]] = {

    "start_flow": StartedFlowCommand,
    "resume_flow": ResumedFlowCommand,
    "cancel_flow": CancelFlowCommand,
    "set_slots": SetSlotsCommand,
}
