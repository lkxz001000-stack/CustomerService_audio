"""
订询查询 Action。

对应对话引擎中的 "query_order" 命令，
从音频平台的 /api/v1/orders 接口获取订单详情，
将订单状态和摘要写入槽位，供后续回复模板渲染。
"""

from typing import Any

from audio_cs.domain.state import DialogueState
from audio_cs.task.action.base import Action, ActionResult
from audio_cs.task.action.customer.shared import fetch_order, _build_order_summary

# 订单状态英文到中文的映射
_ORDER_STATUS_CN: dict[str, str] = {
    "paid": "已支付",
    "pending": "待支付",
    "cancelled": "已取消",
    "refunded": "已退款",
    "refunding": "退款中",
    "expired": "已过期",
    "failed": "支付失败",
}


class QueryOrderAction(Action):
    """订单查询动作。

    从当前流程的 slots 中读取 order_number，
    调用音频平台接口查询订单详情，
    将查询结果（订单状态、订单摘要）写回槽位。

    如果查询失败或订单不存在，写入友好的错误提示信息。
    """

    name = "action_query_order"

    async def run(self, state: DialogueState, action_args: dict[str, Any]) -> ActionResult:
        """执行订单查询。

        参数：
            state：对话状态，需从中获取 sender_id（用户ID）和
                  active_task.slots 中的 order_number
            action_args：本动作不使用，保留以符合接口约定

        返回：
            ActionResult，包含 order_status 和 order_summary 两个槽位更新
        """
        order_number = state.active_task.slots.get("order_number")
        payload = await fetch_order(state.sender_id, order_number)

        if payload is None:
            return ActionResult(slot_updates={
                "order_status": "未知",
                "order_summary": "暂时无法查询该订单信息，请稍后重试。如问题持续，请联系人工客服。",
            })

        order = payload.get("order", {})
        raw_status = order.get("orderStatus") or order.get("order_status") or ""
        return ActionResult(
            slot_updates={
                "order_status": _ORDER_STATUS_CN.get(raw_status, raw_status) if raw_status else "未知",
                "order_summary": _build_order_summary(payload)
            }
        )
