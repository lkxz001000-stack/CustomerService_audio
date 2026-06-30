"""
动作系统构建器模块。

负责组装 Action 系统的核心组件：
1. 通过自动发现机制扫描 customer 包，找出所有 Action 子类并注册
2. 手动注册内置 Action（ActionResponse、ActionListener）
3. 最终构建并返回配置完整的 ActionRunner

自动发现原理：
使用 Python 标准库 pkgutil 遍历包内模块 + inspect 筛选 Action 子类，
实现"新增 Action 子类即自动注册"，无需手动维护注册列表。
"""

import importlib
import inspect
import pkgutil

from audio_cs.task.action.base import Action
from audio_cs.task.action.builtin.listener import ActionListener
from audio_cs.task.action.builtin.response import ActionResponse
from audio_cs.task.action.register import ActionRegister
from audio_cs.task.action.runner import ActionRunner


def register_builtin_actions(action_runner: ActionRunner):
    """注册内置（框架级）Action 到运行器的注册中心。

    内置 Action 包括：
    - ActionResponse：生成 / 改写回复消息
    - ActionListener：流程挂起哨兵，暂停等待用户输入

    这些 Action 是框架层面的通用能力，不依赖具体业务场景，
    因此直接硬编码注册。

    参数：
        action_runner：已构造好的 ActionRunner 实例
    """
    action_runner.registry.register(ActionResponse())
    action_runner.registry.register(ActionListener())


def register_custom_actions(action_runner: ActionRunner):
    """自动发现并注册 customer 包下的所有客户 Action 子类。

    扫描 audio_cs.task.action.customer 包：
    1. 用 pkgutil.iter_modules 列出包内所有 .py 模块
    2. 跳过子包（is_pkg=True），仅处理叶子模块
    3. 对每个模块，用 importlib.import_module 动态导入
    4. 用 inspect.getmembers 遍历模块内所有类
    5. 筛选条件：
       - 是 Action 的子类（issubclass）
       - 不是 Action 本身
       - 类的 __module__ 等于当前模块名（排除导入的类）
    6. 满足条件的类直接实例化并注册到运行器

    参数：
        action_runner：已构造好的 ActionRunner 实例
    """
    # 1. 导入 customer 包
    package = importlib.import_module("audio_cs.task.action.customer")

    # 2. 遍历包内所有模块
    for _, module_name, is_pkg in pkgutil.iter_modules(package.__path__, prefix=f"{package.__name__}."):
        # 3. 跳过子包，只处理 .py 模块
        if is_pkg:
            continue
        # 4. 动态导入模块
        module = importlib.import_module(module_name)
        # 5. 检查模块中每个类的成员
        for _, obj in inspect.getmembers(module, inspect.isclass):
            # 6. 必须是 Action 的具体子类（排除 Action 自身）
            if not issubclass(obj, Action) or obj is Action:
                continue
            # 7. 确保类是在当前模块定义的（而非从别处导入）
            if obj.__module__ != module.__name__:
                continue
            # 8. 实例化并注册
            action_runner.registry.register(obj())


def build_action_runner() -> ActionRunner:
    """构建完整的 ActionRunner。

    工厂函数，依次执行：
    1. 创建 ActionRegister 和 ActionRunner
    2. 注册内置 Action
    3. 自动发现并注册客户 Action
    4. 返回配置完成的 ActionRunner

    返回：
        已注册所有内置和客户 Action 的 ActionRunner 实例
    """
    action_runner = ActionRunner(ActionRegister())
    register_builtin_actions(action_runner)
    register_custom_actions(action_runner)
    return action_runner



















