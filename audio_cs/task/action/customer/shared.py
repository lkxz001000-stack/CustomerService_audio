"""
客户 Action 共享模块。

提供客户类 Action 共用的 HTTP 辅助函数，封装与音频平台后端
（audio-data 项目）的接口交互，统一处理错误和响应数据提取。

功能清单：
- fetch_order：订单查询（2步查找：列表匹配 → 详情获取）
- fetch_playback_history：播放记录查询
- submit_refund：退款申请提交
- create_ticket：工单创建
- _build_order_summary：订单摘要格式化工具
- _extract_data：响应数据安全提取
- _base_url：音频平台基地址
"""

from typing import Any
import logging
from urllib.parse import quote

from audio_cs.config.settings import settings
from audio_cs.infrastructure import http_client

logger = logging.getLogger(__name__)


def _base_url() -> str:
    """获取音频平台 API 基地址，去除尾部斜杠。"""
    return settings.audio_api_base_url.rstrip("/")


def _check_api_error(result: dict | None) -> str | None:
    """检查音频平台统一响应中的业务错误。

    音频平台所有接口返回格式为 {"code": 0, "msg": "...", "data": {...}}，
    code 为 0 表示成功，非 0（如 "USER_NOT_FOUND_OR_DISABLED"）表示业务错误。

    返回：
        业务错误消息字符串；无错误时返回 None
    """
    if not isinstance(result, dict):
        return None
    code = result.get("code")
    if code is not None and code != 0:
        msg = result.get("msg", "") or result.get("message", "")
        return f"API业务错误(code={code}): {msg}"
    return None


def _extract_data(result: dict | None) -> dict | None:
    """从音频平台统一响应格式中安全提取 data 字段。

    音频平台所有接口返回格式为 {"code": ..., "msg": ..., "data": {...}}，
    本函数提取其中的 data 字段，并确保它是 dict 类型。

    参数：
        result：接口返回的完整 JSON 字典（或 None）

    返回：
        data 字段的值（dict 类型），如果不存在或类型不匹配则返回 None
    """
    data = result.get("data") if isinstance(result, dict) else None
    return data if isinstance(data, dict) else None


async def fetch_order(user_id: str, order_no: str) -> dict | None:
    """查询订单详情。

    支持两种 order_no 格式：
    1. 纯数字（如 "42"）：直接作为订单 ID 调用详情接口
    2. 字符串格式（如 "ORD000000000004"）：先通过列表接口按 orderNo 字段
       匹配找到对应的数字 ID，再调用详情接口

    因此整个过程是"2步查找"：
    第1步（非纯数字时）：GET /api/v1/orders?pageSize=100，在列表中匹配 orderNo
    第2步：               GET /api/v1/orders/{numeric_id}，获取完整订单详情

    参数：
        user_id：用户标识，通过 X-User-Id 请求头传递
        order_no：订单编号（纯数字或格式化字符串）

    返回：
        订单详情 data 字典，包含 order（订单信息）和 items（订单项列表）；
        查询失败或未找到时返回 None
    """
    try:
        headers = {"X-User-Id": user_id}
        numeric_id = None

        # ---- 第1步：如果 order_no 是格式化的字符串编号，先查列表获取数字 ID ----
        if order_no.isdigit():
            numeric_id = int(order_no)
        else:
            params = {"pageSize": 100}
            r = await http_client.http_client.get(
                f"{_base_url()}/api/v1/orders",
                headers=headers,
                params=params
            )
            r.raise_for_status()
            body = r.json()
            err = _check_api_error(body)
            if err:
                logger.warning("fetch_order 列表接口错误: user_id=%s, order_no=%s, %s", user_id, order_no, err)
                return None
            data = _extract_data(body)
            if data:
                for item in data.get("list", []):
                    if item.get("orderNo") == order_no:
                        numeric_id = item["orderId"]
                        break

        if numeric_id is None:
            logger.info("fetch_order 未找到订单: user_id=%s, order_no=%s", user_id, order_no)
            return None

        # ---- 第2步：通过数字 ID 获取订单详情 ----
        r = await http_client.http_client.get(
            f"{_base_url()}/api/v1/orders/{numeric_id}",
            headers=headers
        )
        r.raise_for_status()
        body = r.json()
        err = _check_api_error(body)
        if err:
            logger.warning("fetch_order 详情接口错误: user_id=%s, order_no=%s, numeric_id=%s, %s", user_id, order_no, numeric_id, err)
            return None
        return _extract_data(body)
    except Exception:
        logger.exception("fetch_order 异常: user_id=%s, order_no=%s", user_id, order_no)
        return None


async def fetch_playback_history(user_id: str) -> dict | None:
    """获取用户的播放收听记录。

    调用 GET /api/v1/listening-progress，获取最近 10 条收听进度。

    参数：
        user_id：用户标识

    返回：
        播放记录列表 data 字典；异常时返回 None
    """
    try:
        headers = {"X-User-Id": user_id}
        params = {"pageSize": 200}
        r = await http_client.http_client.get(
            f"{_base_url()}/api/v1/listening-progress",
            headers=headers,
            params=params,
            timeout=10
        )
        r.raise_for_status()
        body = r.json()
        err = _check_api_error(body)
        if err:
            logger.warning("fetch_playback_history 接口错误: user_id=%s, %s", user_id, err)
            return None
        return _extract_data(body)
    except Exception:
        logger.exception("fetch_playback_history 异常: user_id=%s", user_id)
        return None


async def submit_refund(user_id: str, payment_id: int, refund_reason: str) -> dict | None:
    """提交退款申请。

    调用 POST /api/v1/refunds，提交退款请求。

    参数：
        user_id：用户标识
        payment_id：支付记录 ID
        refund_reason：退款原因

    返回：
        退款申请响应 data 字典；异常时返回 None
    """
    try:
        headers = {"X-User-Id": user_id, "Content-Type": "application/json"}
        r = await http_client.http_client.post(
            f"{_base_url()}/api/v1/refunds",
            headers=headers,
            json={
                "paymentId": payment_id,
                "refundReason": refund_reason,
                "items": []
            }
        )
        r.raise_for_status()
        body = r.json()
        err = _check_api_error(body)
        if err:
            logger.warning("submit_refund 接口错误: user_id=%s, payment_id=%s, %s", user_id, payment_id, err)
            return None
        return _extract_data(body)
    except Exception:
        logger.exception("submit_refund 异常: user_id=%s, payment_id=%s", user_id, payment_id)
        return None


async def create_ticket(user_id: str, ticket_type: str, description: str, order_id: str | None = None) -> dict | None:
    """创建客服工单。

    调用 POST /api/v1/support-tickets，提交用户反馈工单。
    如果提供了有效的 order_id（纯数字），会作为关联内容附加到工单中。

    参数：
        user_id：用户标识
        ticket_type：工单类型（英文枚举值，如 payment_issue）
        description：工单描述内容
        order_id：关联订单的数字 ID（可选，None 表示不关联）

    返回：
        工单创建响应 data 字典；异常时返回 None
    """
    try:
        headers = {"X-User-Id": user_id, "Content-Type": "application/json"}
        body: dict[str, Any] = {
            "ticketType": ticket_type,
            "ticketTitle": f"用户反馈 - {ticket_type}",
            "ticketContent": description,
        }
        if order_id and order_id != "无" and order_id.isdigit():
            body["relatedType"] = "content_order"
            body["relatedId"] = int(order_id)
        r = await http_client.http_client.post(
            f"{_base_url()}/api/v1/support-tickets",
            headers=headers,
            json=body
        )
        r.raise_for_status()
        resp_body = r.json()
        err = _check_api_error(resp_body)
        if err:
            logger.warning("create_ticket 接口错误: user_id=%s, ticket_type=%s, %s", user_id, ticket_type, err)
            return None
        return _extract_data(resp_body)
    except Exception:
        logger.exception("create_ticket 异常: user_id=%s, ticket_type=%s", user_id, ticket_type)
        return None


async def fetch_album_by_name(album_name: str) -> dict | None:
    """按名称查询专辑详情（含章节信息）。

    调用 GET /api/v1/albums/lookup?name=xxx 获取专辑完整信息。

    参数：
        album_name：专辑名称

    返回：
        专辑详情 data 字典；查询失败时返回 None
    """
    try:
        params = {"name": album_name}
        r = await http_client.http_client.get(
            f"{_base_url()}/api/v1/albums/lookup",
            params=params
        )
        r.raise_for_status()
        body = r.json()
        err = _check_api_error(body)
        if err:
            logger.warning("fetch_album_by_name 接口错误: album_name=%s, %s", album_name, err)
            return None
        return _extract_data(body)
    except Exception:
        logger.exception("fetch_album_by_name 异常: album_name=%s", album_name)
        return None


def _build_order_summary(payload: dict[str, Any]) -> str:
    """从订单详情 payload 构建人类可读的订单摘要文本。

    提取的信息包括：
    - 订单金额（totalAmount）
    - 订单内容项（items 中的 itemName，最多取前2项）

    参数：
        payload：fetch_order 返回的 data 字典，
                 包含 order（订单信息）和 items（订单项列表）

    返回：
        格式化的摘要字符串，例如：
        "订单金额 ¥29.90。内容：红楼梦、三体"
        如果没有可用信息则返回 "暂无详细信息"
    """
    parts = []
    order = payload.get("order", {})
    if order.get("totalAmount"):
        parts.append(f"订单金额：[¥{order['totalAmount']}]")
    # 购买时间
    purchase_time = order.get("createdAt") or order.get("paidAt") or order.get("created_at") or ""
    if purchase_time:
        parts.append(f"购买时间：[{purchase_time}]")
    items = payload.get("items", [])
    if items:
        titles = [str(item.get("itemName") or "").strip() for item in items[:2] if item.get("itemName")]
        if titles:
            parts.append("内容：[" + "、".join(titles) + "]")
    return "\n".join(parts) if parts else "暂无详细信息"
