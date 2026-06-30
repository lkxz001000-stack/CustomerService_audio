"""
任务动作子系统的基础模块。

定义了 Action 动作系统的核心抽象层，包括：
- Action：所有业务动作的抽象基类，采用统一的 run() 接口
- ActionResult：动作执行结果，携带回复消息和槽位更新
- ActionCall：动作调用描述，由流程引擎产生，包含动作名和参数
"""

from abc import ABC, abstractmethod
from typing import Any
from dataclasses import dataclass, field
from audio_cs.domain.messages import BotMessage
from audio_cs.domain.state import DialogueState


@dataclass
class ActionResult:
    """动作执行结果。

    封装一个 Action 执行完毕后产出的数据：
    - messages：要发送给用户的机器人消息列表
    - slot_updates：需要更新到当前流程槽位的键值对
    """
    messages: list[BotMessage] = field(default_factory=list)
    slot_updates: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionCall:
    """动作调用描述。

    由流程引擎（Flow Executor）在解析 YAML 流程定义时构造，
    描述需要执行的动作名称及其参数。
    """
    action_name: str
    action_kwargs: dict[str, Any] = field(default_factory=dict)


class Action(ABC):
    """动作抽象基类。

    所有业务动作（内置动作、客户动作）都必须继承此类，
    并实现 run() 方法。每个子类需要通过 name 类属性声明
    自己的唯一名称，供 ActionRegister 注册和查找。

    注意：name 不是抽象属性，只是约定——子类直接覆盖即可。
    """
    name: str
    # 抽象action的名字属性

    @abstractmethod
    async def run(self,
                  state: DialogueState,
                  action_args: dict[str, Any]
                  ) -> ActionResult:
        """执行动作。

        参数：
            state：当前对话状态，包含用户信息、活跃流程、槽位等
            action_args：动作参数字典，由 ActionCall.action_kwargs 传入

        返回：
            ActionResult，包含回复消息和槽位更新
        """
        pass
