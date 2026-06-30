from audio_cs.task.action.base import Action


class ActionRegister:
    """动作注册中心。

    以字典形式维护 Action 名称到 Action 实例的映射。
    提供 register（注册）、get（查找）两个核心操作。

    所有内置 Action 和客户自定义 Action 都需要在此注册后，
    才能被 ActionRunner 调度执行。

    使用方式：
        registry = ActionRegister()
        registry.register(QueryOrderAction())
        action = registry.get("action_query_order")
    """

    def __init__(self):
        """初始化空的动作注册表。"""
        self._actions: dict[str, Action] = {}

    def register(self, action: Action) -> None:
        """注册一个 Action 实例，以 action.name 为键。"""
        self._actions[action.name] = action

    def get(self, name: str) -> Action:
        """根据名称获取已注册的 Action 实例。

        如果名称不存在，抛出 KeyError。
        """
        if name not in self._actions:
            raise KeyError(f"Unknown action '{name}'.")
        return self._actions[name]



