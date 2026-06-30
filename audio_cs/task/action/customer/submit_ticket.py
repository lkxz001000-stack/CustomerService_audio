"""
工单提交 Action。

将用户在对话中填写的工单信息提交到音频平台的 /api/v1/support-tickets 接口，
包括工单类型、描述、关联订单号等字段。
"""

from typing import Any

from audio_cs.domain.state import DialogueState
from audio_cs.task.action.base import Action, ActionResult
from audio_cs.task.action.customer.shared import create_ticket


class SubmitTicketAction(Action):
    """工单提交动作。

    从 slots 中读取用户填写的工单类型、描述和关联订单号，
    将中文工单类型映射为平台 API 所需的英文枚举值，
    然后调用 create_ticket 接口提交工单。

    成功时将返回的工单编号写入 ticket_number 槽位，
    失败时写入错误提示。
    """

    name = "action_submit_ticket"

    async def run(self, state: DialogueState, action_args: dict[str, Any]) -> ActionResult:
        """执行工单提交。

        参数：
            state：对话状态，从中获取 sender_id 以及 slots 中的
                  ticket_type、order_number、ticket_description
            action_args：本动作不使用

        返回：
            ActionResult，包含 ticket_number 槽位更新
        """
        ticket_type_raw = state.active_task.slots.get("ticket_type", "other")
        order_number = state.active_task.slots.get("order_number", "")
        description = state.active_task.slots.get("ticket_description", "")

        # 工单类型映射：将用户选择的中文类型转换为平台 API 的英文枚举值
        # 前端展示中文给用户，后端使用英文编码与音频平台通信
        type_map = {
            "支付问题": "payment_issue",
            "账号问题": "account_issue",
            "内容问题": "content_issue",
            "功能反馈": "feature_feedback",
            "版权投诉": "copyright_complaint",
            "其他": "other",
        }
        mapped_type = type_map.get(ticket_type_raw, "other")

        payload = await create_ticket(
            state.sender_id,
            mapped_type,
            description,
            # 当 order_number 为 "无"（用户未关联订单），传 None 给接口
            order_number if order_number != "无" else None
        )

        if payload:
            return ActionResult(slot_updates={
                "ticket_number": payload.get("ticketNo") or payload.get("ticketId") or "已创建",
            })

        return ActionResult(slot_updates={
            "ticket_number": "工单创建失败，请稍后重试或联系人工客服。",
        })
