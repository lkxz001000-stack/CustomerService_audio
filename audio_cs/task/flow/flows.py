from dataclasses import dataclass, field, asdict
from audio_cs.task.flow.steps import FlowStep, StartFlowStep


@dataclass(slots=True)
class FlowSlot:
    """流程槽位定义：描述业务流程中需要收集的用户信息字段。"""
    name: str  # 槽位名称（如 order_number, refund_reason）
    type: str  # 槽位值的数据类型
    label: str  # 槽位的中文标签（用于展示给用户）
    description: str  # 槽位的描述说明


@dataclass(slots=True)
class Flow:
    """
    流程定义（业务流程或系统流程）。

    每个 Flow 由一系列 FlowStep 组成，步骤之间通过 Link 连接形成有向图。
    description 字段会提供给 LLM 作为工具描述，LLM 根据此描述决定启动哪个流程。
    """
    flow_id: str  # 流程唯一标识（系统流程以 system_ 为前缀）
    flow_name: str  # 流程中文名称
    description: str  # 流程描述（重要：LLM 据此选择流程）
    steps: list[FlowStep] = field(default_factory=list)  # 流程中的所有步骤
    slots: dict[str, FlowSlot] = field(default_factory=dict)  # 该流程关联的槽位定义

    def get_start_step(self) -> StartFlowStep | None:
        """获取流程的起始步骤（StartFlowStep）。"""
        for step in self.steps:
            if isinstance(step, StartFlowStep):
                return step
        return None

    def get_step_by_id(self, step_id: str) -> FlowStep | None:
        """根据步骤 ID 查找步骤。O(n) 查找，因步骤数通常较少所以性能可接受。"""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None


@dataclass(slots=True)
class FlowsList:
    """
    流程列表聚合。

    合并了 user_flows.yml 和 system_flows.yml 两份配置文件中的所有流程。
    统一提供流程查找能力。
    """
    flows: list[Flow] = field(default_factory=list)  # 所有流程（业务+系统）
    slots: dict[str, FlowSlot] = field(default_factory=dict)  # 所有槽位定义

    def get_flow_by_id(self, flow_id: str) -> Flow | None:
        """根据流程 ID 查找流程。"""
        for flow in self.flows:
            if flow.flow_id == flow_id:
                return flow
        return None
