"""
流程步骤链接定义。

流程步骤之间通过链接形成有向图，支持三种链接类型：
1. FlowStepStaticLink：无条件跳转到下一步
2. FlowStepConditionLink：满足条件时跳转到指定步骤（条件使用 Python eval 计算）
3. FlowStepFallbackLink：兜底跳转（类似 else 分支）
"""

from dataclasses import dataclass


@dataclass(slots=True)
class FlowStepLink:
    """链接基类：包含目标步骤 ID。"""
    target: str  # 下一个步骤的 ID


@dataclass(slots=True)
class FlowStepStaticLink(FlowStepLink):
    """
    静态链接（无条件跳转）。

    YAML 示例:
        next: ask_refund_reason
    """
    pass


@dataclass(slots=True)
class FlowStepConditionLink(FlowStepLink):
    """
    条件链接（满足条件时跳转）。

    condition 字段为 Python 表达式字符串，运行时通过 eval 计算。
    表达式可访问 slots（当前槽位值）和 context（系统上下文变量）。

    YAML 示例:
        next:
          - if: "context.get('reason') == 'clarification_rejected'"
            then: clarification_rejected
    """
    condition: str  # Python 条件表达式（如 "slots.get('order_status') == 'paid'"）


@dataclass(slots=True)
class FlowStepFallbackLink(FlowStepLink):
    """
    兜底链接（默认跳转，类似 if-else 中的 else 分支）。

    YAML 示例:
        next:
          - else: ask_rephrase
    """
    pass
