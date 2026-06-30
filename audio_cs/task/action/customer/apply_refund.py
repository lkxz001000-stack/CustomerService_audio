"""
退款申请 Action。

根据用户提供的订单号查询订单状态，验证是否满足退款条件，
然后将处理结果写入槽位供回复模板渲染。

注意：当前实现仅做状态校验并返回模拟结果，
实际退款提交逻辑（调用 /api/v1/refunds）尚未在此 Action 中集成。
"""

from typing import Any

from audio_cs.domain.state import DialogueState
from audio_cs.task.action.base import Action, ActionResult
from audio_cs.task.action.customer.shared import fetch_order


class ApplyRefundAction(Action):
    """退款申请动作。

    处理流程：
    1. 从 slots 中获取 order_number
    2. 调用音频平台接口查询订单详情
    3. 校验订单状态是否允许退款（仅 "paid" / "已支付" / "已完成" 可退）
    4. 写入相应的处理结果到 order_summary 槽位
    """

    name = "action_apply_refund"

    async def run(self, state: DialogueState, action_args: dict[str, Any]) -> ActionResult:
        """执行退款申请校验。

        参数：
            state：对话状态，提供 sender_id 和 slots 中的 order_number
            action_args：本动作不使用

        返回：
            ActionResult，包含 order_summary 槽位更新
        """
        order_number = state.active_task.slots.get("order_number")

        payload = await fetch_order(state.sender_id, order_number)

        # 订单不存在：无法申请退款
        if payload is None:
            return ActionResult(slot_updates={
                "order_summary": "未找到该订单，无法申请退款。请确认订单号是否正确。",
            })

        order = payload.get("order", {})
        order_status = order.get("orderStatus") or order.get("order_status") or ""

        # 退款资格校验：仅已支付或已完成的订单可以退款
        # 待支付、已取消等状态均不支持退款
        if order_status not in ("paid", "已支付", "已完成"):
            return ActionResult(slot_updates={
                "order_summary": f"该订单当前状态不支持退款（状态：{order_status}）。如有疑问请提交工单。",
            })

        # 退款申请通过（模拟结果）
        return ActionResult(slot_updates={
            "order_summary": "退款申请已提交，客服将在1-3个工作日内处理。退款将按你选择的退款方式退回。",
        })
