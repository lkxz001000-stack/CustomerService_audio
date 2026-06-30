"""
流程步骤定义。

流程由四种步骤类型组成，每个步骤通过链接（links）指向后续步骤：
- StartFlowStep：流程入口
- EndFlowStep：流程终点
- ActionFlowStep：执行动作（API 调用或生成回复）
- CollectFlowStep：信息收集（向用户询问槽位值）

步骤实例通过 from_dict 工厂方法从 YAML 配置反序列化。
"""

from typing import Any, Self
from enum import Enum
from dataclasses import dataclass, field
from audio_cs.task.flow.links import FlowStepLink, FlowStepStaticLink, FlowStepConditionLink, FlowStepFallbackLink


class FlowStepType(Enum):
    """
    流程步骤类型枚举。

    - START: 流程起始步骤（业务和系统流程通用）
    - END: 流程结束步骤（业务和系统流程通用）
    - COLLECT: 信息收集步骤（仅出现在业务流程中，用于收集槽位信息）
    - ACTION: 动作步骤，三种情况：
        1. action_response — 告知用户信息（开场白、引导填写槽位等）
        2. action_listen — 将控制权交给用户，让流程暂停等待用户输入
        3. action_xxx — 调用外部 API 获取数据（仅出现在业务流程中）
    """
    START = "start"
    COLLECT = "collect"
    ACTION = "action"
    END = "end"


@dataclass(slots=True)
class ResponseDefinition:
    """
    响应内容定义。

    mode 决定文本生成方式：
    - "static": 直接使用 text 文案
    - "rephrase": 将 text 作为提示词通过 LLM 改写后输出
    - 其他: 作为 prompt 提示词通过 LLM 从头生成回复
    """
    text: str  # 响应文本内容
    mode: str = "static"  # 响应模式（static / rephrase / 其他为 prompt 模式）
    prompt: str | None = None  # 可选的额外提示词


@dataclass(slots=True)
class SlotValidation:
    """槽位校验规则：定义槽位值的条件检查和校验失败时的响应。"""
    condition: str  # Python 条件表达式（如 "slot_value.isdigit()"），通过 eval 计算
    failure_response: ResponseDefinition | None = None  # 校验失败时发给用户的提示


@dataclass(slots=True)
class FlowStep:
    """
    流程步骤基类。

    包含所有步骤类型的通用字段，并提供 from_dict 工厂方法
    通过 FLOW_STEP_TYPE_TO_CLASS 注册表派发到具体子类。
    """
    id: str  # 步骤唯一标识
    type: FlowStepType  # 步骤类型
    next: list[FlowStepLink] = field(default_factory=list)  # 后续链接列表

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """工厂方法：根据步骤类型分发到对应的子类 from_dict。"""
        step_type = data['type']
        clz = FLOW_STEP_TYPE_TO_CLASS[step_type]
        return clz.from_dict(data)

    @staticmethod
    def load_base_fields(step_data: dict[str, Any]) -> dict[str, Any]:
        """提取步骤字典中的通用基础字段。"""
        return {
            'id': step_data['id'],
            'type': FlowStepType(step_data['type']),
            'next': FlowStep.build_links(step_data['next'])
        }

    @classmethod
    def build_links(cls, link: str | list[dict[str, Any]]) -> list[FlowStepLink]:
        """
        构建步骤链接列表。

        支持两种 YAML 格式：
        - 字符串："next_step_id" → 静态链接
        - 列表：[{if: 条件, then: 目标}, {else: 兜底}] → 条件/兜底链接
        """
        links: list[FlowStepLink] = []
        if isinstance(link, str):
            # 简单字符串 → 无条件静态跳转
            links.append(FlowStepStaticLink(target=link))
        else:
            for condition_link in link:
                if "if" in condition_link:
                    # 条件链接：满足 if 表达式时跳转 then
                    links.append(FlowStepConditionLink(
                        condition=condition_link['if'],
                        target=condition_link['then']
                    ))
                else:
                    # 兜底链接：以上条件都不满足时跳转
                    links.append(FlowStepFallbackLink(target=condition_link['else']))
        return links


@dataclass(slots=True)
class StartFlowStep(FlowStep):
    """流程入口步骤：流程从该步骤开始执行。"""

    @classmethod
    def from_dict(cls, start_step_data: dict[str, Any]):
        return cls(**FlowStep.load_base_fields(start_step_data))


@dataclass(slots=True)
class EndFlowStep(FlowStep):
    """流程结束步骤：流程到达此步骤时终止。"""

    @classmethod
    def from_dict(cls, end_step_data: dict[str, Any]):
        return cls(**FlowStep.load_base_fields(end_step_data))


@dataclass(slots=True)
class ActionFlowStep(FlowStep):
    """
    动作步骤：执行具体操作。

    action 字段决定动作类型：
    - "action_listen": 暂停执行，等待用户输入（仅系统流程）
    - "action_response": 生成回复文本（使用 Jinja2 模板渲染）
    - "action_xxx": 调用外部 API 获取数据（仅业务流程）
    """
    action: str = ""  # 动作名称
    args: dict[str, Any] = field(default_factory=dict)  # 动作参数（传递给模板或 API）

    @classmethod
    def from_dict(cls, action_step_data: dict[str, Any]):
        return cls(
            **FlowStep.load_base_fields(action_step_data),
            action=action_step_data['action'],
            args=action_step_data.get('args')
        )


@dataclass(slots=True)
class CollectFlowStep(FlowStep):
    """
    信息收集步骤：向用户询问某个槽位的值。

    采用双入口机制：
    1. 首次进入 → 触发 system_collect_information 系统流程（询问用户）
    2. 用户回复后再次进入 → 验证槽位值，通过则继续流程
    """
    slot_name: str = ""  # 要收集的槽位名称
    response: ResponseDefinition = field(default_factory=ResponseDefinition)  # 询问用户的提示文本
    validate: SlotValidation | None = None  # 可选的槽位校验规则

    @classmethod
    def from_dict(cls, collect_step_data: dict[str, Any]):
        return cls(
            **FlowStep.load_base_fields(collect_step_data),
            slot_name=collect_step_data.get('slot_name'),
            response=ResponseDefinition(
                text=collect_step_data['response']['text'],
                mode=collect_step_data['response'].get('mode', 'static'),
                prompt=collect_step_data['response'].get('prompt')
            ),
            validate=SlotValidation(
                condition=collect_step_data['validate']['condition'],
                failure_response=ResponseDefinition(
                    text=collect_step_data['validate']['failure_response']['text'],
                    mode=collect_step_data['validate'].get('failure_response').get('mode'),
                    prompt=collect_step_data['validate'].get('failure_response').get('prompt')
                ) if collect_step_data['validate'].get('failure_response') else None
            ) if collect_step_data.get('validate') else None
        )


# 步骤类型字符串 → 步骤类的注册表（用于 from_dict 工厂方法派发）
FLOW_STEP_TYPE_TO_CLASS: dict[str, type[FlowStep]] = {
    "start": StartFlowStep,
    "end": EndFlowStep,
    "collect": CollectFlowStep,
    "action": ActionFlowStep
}





