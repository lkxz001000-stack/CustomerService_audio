from typing import Any

from audio_cs.domain.state import DialogueState
from audio_cs.task.action.base import Action, ActionResult


class ActionListener(Action):
    """监听哨兵 Action。

    这是一个特殊的"空动作"——它的 run() 方法不执行任何实际逻辑，
    直接返回空的 ActionResult。它的作用是通知 Flow Executor（流程执行器）：
    当前流程节点需要暂停并等待用户的下一次输入。

    典型使用场景：
    流程 YAML 中 info_collect 步骤收集完用户信息后，
    流程执行器执行到 ActionListener 时会中止执行栈，
    将控制权交还给 DialogueEngine，等待用户下一条消息。

    注意：这个 Action 的名称固定为 "action_listen"，
    Flow Executor 通过这个名称识别哨兵节点。
    """

    name = "action_listen"

    async def run(self,
                  state: DialogueState,
                  action_args: dict[str, Any]) -> ActionResult:
        """空实现——目的是告知流程执行器在此暂停。"""
        pass

