"""
聊天接口路由模块

本模块定义了面向前端的 REST API 端点，共 4 个:

  1. GET  /hello          - 健康检查端点，返回 {"success": "ok"}
  2. POST /api/chat       - 核心聊天端点，接收用户消息并返回机器人回复
  3. GET  /api/chat/history - 历史对话查询端点，返回用户与机器人的历史消息
  4. GET  /api/user/status  - 用户状态查询端点，校验用户账户是否正常

核心请求/响应转换模式:
  前端 --> ChatRequest(Schema) --> UserMessage(Domain) --> DialogueService -->
  ProcessResult(Domain) --> ChatResponse(Schema) --> 前端
"""
import logging
import json
import uuid
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from audio_cs.api.dependencies import DialogueServiceDep
from audio_cs.api.schemas import ChatRequest, ChatResponse, ChatBotMessage, ChatObject, ChatMessageResponse, SessionStateResponse
from audio_cs.domain.messages import ProcessResult, UserMessage, MessageType, FocusedObject,ChatHistoryMessage
from audio_cs.config.settings import settings
from evaluation.telemetry import telemetry
from audio_cs.infrastructure import http_client

logger = logging.getLogger(__name__)
router = APIRouter()

# 用户状态中文映射
_STATUS_LABELS: dict[str, str] = {
    "normal": "正常",
    "muted": "限制发言",
    "disabled": "已禁用",
    "cancelled": "已注销",
}


def _audio_db_url() -> str:
    """从客服数据库 URL 推导出 audio 平台数据库 URL（同服不同库）。"""
    return settings.database_url.replace("/audio_cs", "/audio")


async def _get_user_account_status(user_id: str) -> str | None:
    """查询 audio 平台 user_account 表的 account_status 字段。"""
    engine = create_async_engine(_audio_db_url(), echo=False)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT account_status FROM user_account WHERE id = :uid"),
                {"uid": int(user_id)}
            )
            row = result.fetchone()
            return row[0] if row else None
    finally:
        await engine.dispose()


@router.get("/hello")
async def hello():
    """健康检查端点，用于验证服务是否正常运行。"""
    return {"success": "ok"}


@router.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(chat_request: ChatRequest,
                        service: DialogueServiceDep):
    # 1. 将接口数据模型转成领域数据模型
    user_message = _build_user_message(chat_request)
    logger.info("收到消息: sender_id=%s, type=%s, text=%s",
                user_message.sender_id, user_message.type.value,
                (user_message.text or "")[:50])

    # 2. 注入service使用
    process_result: ProcessResult = await service.hand_dialogue(user_message)

    # 3. 将领域数据模型转成接口数据模型
    chat_response = _build_chat_response(process_result)

    logger.debug("回复消息: sender_id=%s, msg_count=%d, diag=%s",
                 process_result.sender_id, len(process_result.messages),
                 json.dumps(process_result.diagnostics or {}, ensure_ascii=False))
    return chat_response


def _build_user_message(chat_request: ChatRequest) -> UserMessage:
    """
    将接口数据模型 ChatRequest 转换为领域数据模型 UserMessage。

    转换逻辑:
      - 为新消息生成唯一的 UUID 作为 message_id
      - 如果 chat_request.object 非空，则消息类型为 OBJECT（用户点击了卡片）
      - 如果 chat_request.object 为空，则消息类型为 TEXT（用户输入了文字）
      - 将 ChatObject 的字段逐个映射到 FocusedObject 领域对象

    :param chat_request: 前端发送的聊天请求 Schema
    :return: 领域层的 UserMessage 对象
    """
    return UserMessage(
        sender_id=chat_request.sender_id,
        message_id=str(uuid.uuid4()),
        type=MessageType.OBJECT if chat_request.object else MessageType.TEXT,
        text=chat_request.text,
        object=FocusedObject(
            id=chat_request.object.id,
            type=chat_request.object.type,
            title=chat_request.object.title,
            attributes=chat_request.object.attributes,
        ) if chat_request.object else None
    )


def _build_chat_response(process_result: ProcessResult) -> ChatResponse:
    """
    将领域处理结果 ProcessResult 转换为接口响应模型 ChatResponse。

    转换逻辑:
      - sender_id 和 message_id 直接透传
      - messages 列表中的每个 BotMessage 映射为一个 ChatBotMessage:
        * BotMessage.text -> ChatBotMessage.text（纯文本）
        * BotMessage.object -> ChatObject（业务对象卡片）
        * 二者互斥，至少一个非空

    :param process_result: 对话引擎处理后的领域结果
    :return: 符合前端约定的 ChatResponse Schema
    """

    return ChatResponse(
        sender_id=process_result.sender_id,
        message_id=process_result.message_id,
        messages=[ChatBotMessage(text=bot_message.text,
                                 object=ChatObject(
                                     id=bot_message.object.id,
                                     type=bot_message.object.type,
                                     title=bot_message.object.title,
                                     attributes=bot_message.object.attributes,
                                 ) if bot_message.object else None) for bot_message in process_result.messages],
        diagnostics=process_result.diagnostics,
    )



@router.get("/api/chat/history", response_model=ChatMessageResponse)
async def chat_history_endpoint(sender_id: str,
                                service: DialogueServiceDep) -> ChatMessageResponse:
    """
    历史对话查询端点 —— 返回指定用户与机器人的所有历史消息。

    处理流程:
      1. 调用 DialogueService.load_chat_history(sender_id)
         从数据库中加载用户的对话状态，提取历史轮次中的问答记录
      2. 包装为 ChatMessageResponse 返回给前端

    :param sender_id: 用户唯一标识（查询参数）
    :param service: FastAPI DI 注入的对话服务实例
    :return: 包含历史消息列表的响应体
    """

    chat_message_response: list[ChatHistoryMessage] = await service.load_chat_history(sender_id)

    return ChatMessageResponse(sender_id=sender_id, messages=chat_message_response)


@router.get("/api/user/status")
async def user_status_endpoint(sender_id: str):
    """用户状态查询 —— 校验用户账户是否正常。

    查询 audio 平台的 user_account 表，返回账户状态。
    仅 account_status='normal' 的用户可以正常对话。
    """
    try:
        status = await _get_user_account_status(sender_id)
    except Exception:
        logger.exception("查询用户状态失败: sender_id=%s", sender_id)
        raise HTTPException(status_code=502, detail="查询用户状态失败，请稍后重试")

    if status is None:
        raise HTTPException(status_code=404, detail=f"用户ID {sender_id} 不存在")

    return {
        "sender_id": sender_id,
        "account_status": status,
        "status_label": _STATUS_LABELS.get(status, status),
        "can_chat": status == "normal",
    }


@router.get("/api/chat/session", response_model=SessionStateResponse)
async def session_state_endpoint(sender_id: str,
                                  service: DialogueServiceDep) -> SessionStateResponse:
    """获取当前会话状态 —— 返回当前任务流程和已收集的槽位信息。

    不返回消息历史（消息历史通过 /api/chat/history 获取）。
    """
    state = await service.repository.load_dialogue(sender_id)

    active_task_info = None
    if state.active_task:
        active_task_info = {
            "flow_id": state.active_task.flow_id,
            "step_id": state.active_task.step_id,
            "slots": dict(state.active_task.slots),
        }

    interrupted_info = []
    for task in state.interrupted_active_tasks:
        interrupted_info.append({
            "flow_id": task.flow_id,
            "step_id": task.step_id,
            "slots": dict(task.slots),
        })

    focused_obj = state.focused_object.to_dict() if state.focused_object else None

    return SessionStateResponse(
        sender_id=sender_id,
        has_active_session=state.current_session() is not None,
        active_task=active_task_info,
        interrupted_tasks=interrupted_info,
        focused_object=focused_obj,
    )


@router.post("/api/chat/stream")
async def chat_stream_endpoint(chat_request: ChatRequest,
                                service: DialogueServiceDep):
    """SSE 流式聊天端点。

    与 /api/chat 使用相同的处理逻辑，通过 Server-Sent Events
    实时流式返回每条 BotMessage。

    事件格式:
      data: {"type": "message", "content": {"text": "...", "object": null}}
      data: {"type": "done", "message_id": "xxx"}
    """
    user_message = _build_user_message(chat_request)
    logger.info("SSE流式消息: sender_id=%s, text=%s",
                user_message.sender_id, (user_message.text or "")[:50])

    async def event_generator():
        process_result = await service.hand_dialogue(user_message)
        for msg in process_result.messages:
            event_data = json.dumps({
                "type": "message",
                "content": {
                    "text": msg.text,
                    "object": {
                        "id": msg.object.id,
                        "type": msg.object.type,
                        "title": msg.object.title,
                        "attributes": msg.object.attributes,
                    } if msg.object else None,
                }
            }, ensure_ascii=False)
            yield f"data: {event_data}\n\n"
        diag = json.dumps(process_result.diagnostics or {}, ensure_ascii=False)
        yield f"data: {json.dumps({'type': 'done', 'message_id': process_result.message_id, 'diagnostics': json.loads(diag)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/api/telemetry")
async def telemetry_endpoint():
    """在线指标端点 —— 返回当前服务质量的实时快照。"""
    return await telemetry.snapshot()


@router.post("/api/telemetry/reset")
async def telemetry_reset_endpoint():
    """重置在线指标计数器。"""
    await telemetry.reset()
    return {"success": True}


@router.get("/api/orders")
async def orders_endpoint(sender_id: str):
    """获取用户订单列表（代理 audio-data 接口）。

    调用音频平台 GET /api/v1/orders 获取用户全部订单，
    提取关键字段后返回给前端渲染订单卡片。
    """
    url = f"{settings.audio_api_base_url}/api/v1/orders"
    headers = {"X-User-Id": sender_id}
    params = {"pageSize": 100}
    try:
        response = await http_client.http_client.get(url, headers=headers, params=params)
        response.raise_for_status()
        body = response.json()
        orders = []
        data = body.get("data", {}) if isinstance(body, dict) else {}
        for item in data.get("list", []):
            orders.append({
                "order_no": item.get("orderNo", ""),
                "order_id": item.get("orderId", ""),
                "total_amount": item.get("totalAmount", ""),
                "order_status": item.get("orderStatus", ""),
                "created_at": item.get("createdAt", ""),
                "paid_at": item.get("paidAt", ""),
            })
        return {"orders": orders}
    except Exception as e:
        logger.exception("获取订单列表失败: sender_id=%s, url=%s, error=%s", sender_id, url, e)
        raise HTTPException(status_code=502, detail=f"获取订单列表失败: {e}")