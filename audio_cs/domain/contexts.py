"""
上下文领域模型层（Context Domain Model Layer）
============================================

本模块定义了客服系统中流程执行期间的上下文数据模型。
上下文（Context）是"承载动态、可变信息的容器"——在流程运行期间，
每一步的状态、收集的槽位数据、流程标识等动态信息都存储在上下文中。

上下文概念：
    把动态（变化）的东西装进去 —— 承载动态可变的内容。

核心模型：
    TaskContext:      业务流程上下文（用户正在执行的业务，如退款申请）
    SystemContext:    系统流程上下文（系统自动触发的流程，如开场白、中断提示等）
      ├── StartedSystemContext:     开启业务流程的欢迎语
      ├── InterruptedSystemContext: 中断旧流程的提示语
      ├── ResumedSystemContext:     恢复旧流程的提醒语
      ├── CanceledSystemContext:    取消流程的确认语
      └── CollectedSystemContext:   收集槽位信息的引导语

设计要点：
    TaskContext/SystemContext 各子类未来给引擎使用（运行流程以及执行流程的步骤）。
    引擎未来执行流程时，并不固定在哪一步，TaskContext 中的 flow_id 和 step_id
    就是用于追踪当前位置的抽象标识。

SYSTEM_CONTEXT_TO_CLASS 注册表：
    用于 SystemContext 的反序列化。因为 SystemContext 是基类，反序列化时
    需要根据 flow_id 路由到正确的子类（工厂模式）。
    注册表映射关系：
        "system_task_started"          → StartedSystemContext
        "system_task_resumed"          → ResumedSystemContext
        "system_collect_information"   → CollectedSystemContext
        "system_task_interrupted"      → InterruptedSystemContext
        "system_task_canceled"         → CanceledSystemContext
"""
from typing import Any
from dataclasses import field, dataclass, asdict


@dataclass(slots=True)
class TaskContext:
    """
    业务流程上下文
    -------------
    保存用户在执行某一个业务流程期间的动态信息。

    核心属性:
        flow_id: 业务流程的唯一标识（如 "refund_apply"、"order_query"）
        step_id: 流程中当前所处的步骤标识（如 "collect_order_number"、"confirm_order"）
        slots:   收集到的槽位数据字典（如 {"order_number": "12345"}）

    在 DialogueState 中的位置:
        active_task:         当前正在运行的业务流程上下文
        interrupted_active_tasks: 被中断的业务流程上下文栈

    协作关系:
        - 由 TurnPlanner（LLM 规划层）创建，通过 CommandProcessor 维护
        - 业务流程 YAML 定义（flow_config/）中的 flow_id 和 step_id 与此对应
        - set_slots() 方法在流程执行过程中逐步填充槽位数据

    生命周期:
        创建 → 引擎执行步骤 → 收集槽位 → 所有步骤完成 → 销毁
        若中途被中断 → 压入 interrupted_active_tasks 栈 → 等待恢复
    """

    flow_id: str  # 业务流程的流程ID（对应 flow_config/*.yml 中定义的流程标识）
    step_id: str  # 某一个业务流程对应的步骤ID（当前执行到流程的哪一步）
    slots: dict[str, Any] = field(default_factory=dict)  # 收集的槽位数据

    def to_dict(self) -> dict[str, Any]:
        """
        将 TaskContext 序列化为字典。

        返回:
            dict: 包含 flow_id、step_id、slots 的字典。
                  slots 使用 dict() 浅拷贝做数据隔离。
        """
        return {
            "flow_id": self.flow_id,
            "step_id": self.step_id,
            "slots": dict(self.slots)  # 浅拷贝隔离，防止外部修改影响内部状态
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskContext":
        """
        从字典反序列化为 TaskContext 实例。

        参数:
            data: 包含 flow_id、step_id、slots 键的字典

        返回:
            TaskContext: 新构造的实例
        """
        return cls(
            flow_id=data['flow_id'],
            step_id=data['step_id'],
            slots=data.get('slots')
        )


@dataclass(slots=True)
class SystemContext:
    """
    系统流程上下文（基类/模板）
    -------------------------
    定义系统流程的通用结构。系统流程是由引擎自动触发、不直接对应用户意图的
    内部流程。所有具体的系统流程类型都继承自此类。

    核心属性:
        flow_id: 系统流程的唯一标识（如 "system_task_started"）
        step_id: 系统流程中当前所处的步骤标识

    子类（多态层次）:
        - StartedSystemContext      → flow_id = "system_task_started"
        - InterruptedSystemContext  → flow_id = "system_task_interrupted"
        - ResumedSystemContext      → flow_id = "system_task_resumed"
        - CanceledSystemContext     → flow_id = "system_task_canceled"
        - CollectedSystemContext    → flow_id = "system_collect_information"

    反序列化策略:
        from_dict() 不是直接构造 SystemContext，而是通过 SYSTEM_CONTEXT_TO_CLASS
        注册表查找 flow_id 对应的子类，然后构造子类实例。这是一种工厂模式的应用，
        使得反序列化出的对象具有正确的类型和多态行为。
    """
    flow_id: str  # 开启的系统流程ID（不同的阶段，如 started、interrupted 等）
    step_id: str  # 开启系统流程的步骤ID（某一个流程下的不同的步骤）

    def to_dict(self) -> dict[str, Any]:
        """
        将具体的子类对象转成字典。

        返回:
            dict: 使用 dataclasses.asdict() 递归序列化整个数据类及其子类字段。
                  相比手动构造字典，asdict() 能自动处理继承层次中的所有字段。
        """
        return asdict(self)  # type:ignore  # asdict() 递归处理所有 dataclass 字段

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SystemContext":
        """
        从字典反序列化为对应的 SystemContext 子类对象（工厂模式）。

        参数:
            data: 包含 flow_id 等字段的字典

        返回:
            SystemContext: 根据 flow_id 路由到的具体子类实例

        工厂模式说明:
            由于 SystemContext 是基类，有多个子类（Started、Interrupted 等），
            反序列化时无法预知应该构造哪个子类。SYSTEM_CONTEXT_TO_CLASS 注册表
            通过 flow_id 映射到对应的子类构造器，实现类型正确的反序列化。

            注册表映射（在模块底部定义）：
                "system_task_started"          → StartedSystemContext
                "system_task_resumed"          → ResumedSystemContext
                "system_collect_information"   → CollectedSystemContext
                "system_task_interrupted"      → InterruptedSystemContext
                "system_task_canceled"         → CanceledSystemContext
        """
        # 根据 flow_id 从注册表查找对应的子类
        clz = SYSTEM_CONTEXT_TO_CLASS[data['flow_id']]
        # 使用子类的构造器创建实例（**data 解包传入所有字段）
        return clz(**data)


@dataclass(slots=True)
class StartedSystemContext(SystemContext):
    """
    开启业务流程的系统上下文
    -----------------------
    当用户触发一个新的业务流程时，引擎在激活业务流程之前先触发此系统流程。

    触发时机:
        开启业务流程的时候（先触发 welcome/splash 消息，再进入业务逻辑）

    额外属性:
        started_flow_id:   具体开启的业务流程 ID（变化，取决于用户选择的业务）
        started_flow_name: 具体开启的业务流程名称（如 "订单查询"、"退款申请"）

    典型输出:
        "好的，我来帮您处理退款申请。请提供您的订单编号。"
    """
    started_flow_id: str  # 具体开启的业务流程ID
    started_flow_name: str  # 具体开启的业务流程的名字


@dataclass(slots=True)
class InterruptedSystemContext(SystemContext):
    """
    中断业务流程的系统上下文
    -----------------------
    当用户正在执行流程 A 时触发了流程 B，引擎先将流程 A 中断并压栈，
    然后触发此系统流程告知用户旧流程已暂停。

    触发时机:
        场景：之前正在进行 A 业务流程，接着开启 B 的业务流程。
        底层：先把之前的业务流程存储到 interrupted_active_tasks 栈中，
        然后开启新的业务流程，最后触发中断开场白。

    额外属性:
        interrupted_flow_id:   被中断的业务流程 ID
        interrupted_flow_name: 被中断的业务流程名字
        started_flow_id:       新开启的业务流程 ID
        started_flow_name:     新开启的业务流程名字

    典型输出:
        "您之前正在进行的【订单查询】已暂停，我先帮您处理【退款申请】。"
    """
    interrupted_flow_id: str  # 中断的业务流程ID
    interrupted_flow_name: str  # 中断的业务流程名字
    started_flow_id: str  # 开启新的业务流程ID
    started_flow_name: str  # 开启新的业务流程名字


@dataclass(slots=True)
class ResumedSystemContext(SystemContext):
    """
    恢复业务流程的系统上下文
    -----------------------
    当新业务流程执行完毕后，引擎从 interrupted_active_tasks 栈中恢复
    之前被中断的旧流程，并触发此系统流程告知用户旧流程已恢复。

    触发时机:
        场景：之前正在进行 A 业务流程，开启了 B 的业务流程，
        接着 B 的业务流程做完了，继续执行 A 的业务流程。

    额外属性:
        resumed_flow_id:   被恢复的业务流程 ID
        resumed_flow_name: 被恢复的业务流程名字（从栈中恢复的流程）

    典型输出:
        "【退款申请】已处理完毕，我们继续之前的【订单查询】。请问您想查询哪一笔订单？"
    """
    resumed_flow_id: str  # 中断的业务流程ID
    resumed_flow_name: str  # 中断的业务流程名字


@dataclass(slots=True)
class CanceledSystemContext(SystemContext):
    """
    取消业务流程的系统上下文
    -----------------------
    当用户主动要求取消当前正在执行的业务流程时触发。

    触发时机:
        场景：之前开启了一个业务流程，接着用户说"取消"、"不做了"。

    额外属性:
        canceled_flow_id:   被取消的业务流程 ID
        canceled_flow_name: 被取消的业务流程名字

    典型输出:
        "好的，已为您取消【退款申请】。请问还有什么可以帮您的？"
    """
    canceled_flow_id: str  # 取消的业务流程ID
    canceled_flow_name: str  # 取消的业务流程名字


@dataclass(slots=True)
class CollectedSystemContext(SystemContext):
    """
    收集槽位信息的系统上下文
    -----------------------
    当业务流程需要向用户收集某个槽位信息时触发。引导用户填写必要的参数。

    触发时机:
        当某一个业务流程要补充槽位信息的时候触发。
        1. 告诉用户槽位需要填写什么（如 "请告诉我您的订单号"）
        2. 收集用户填写的槽位值（slot_name 指定了槽位名）
        3. 下游逻辑可以继续使用用户填写的槽位信息

    额外属性:
        response:  响应信息字典，包含提示文本（如 {"text": "请告诉我您的订单号。"}）
        slot_name: 要收集的槽位名称（如 "order_number"、"refund_reason"）

    典型输出:
        response = {"text": "请告诉我您的订单号。"}
        slot_name = "order_number"
        → 用户回复 "12345"
        → 引擎将 "12345" 写入 slots["order_number"]
    """
    response: dict[str, Any]  # {"text": "请告诉我你的订单号。"}
    slot_name: str  # 槽位名字 "order_number"


# =============================================================================
# SYSTEM_CONTEXT_TO_CLASS 注册表
# =============================================================================
# 用途：SystemContext 的反序列化工厂注册表
#
# SystemContext 是基类，有多个具体子类。反序列化时需要根据 flow_id 字段
# 来确定应该构造哪个子类的实例。这个字典就是 flow_id → 子类构造器的映射。
#
# 工作流程：
#   1. 从数据库 JSON blob 中读取 {"flow_id": "system_task_started", ...}
#   2. SystemContext.from_dict() 中用 flow_id 查表
#   3. 找到 StartedSystemContext 类
#   4. 调用 StartedSystemContext(**data) 构造正确的子类实例
#
# 新增 SystemContext 子类时，需要在此注册表中添加对应的映射条目。
SYSTEM_CONTEXT_TO_CLASS: dict[str, Any] = {

    "system_task_started": StartedSystemContext,           # 开启业务流程 → StartedSystemContext
    "system_task_resumed": ResumedSystemContext,           # 恢复业务流程 → ResumedSystemContext
    "system_collect_information": CollectedSystemContext,  # 收集槽位信息 → CollectedSystemContext
    "system_task_interrupted": InterruptedSystemContext,   # 中断业务流程 → InterruptedSystemContext
    "system_task_canceled": CanceledSystemContext          # 取消业务流程 → CanceledSystemContext
}
