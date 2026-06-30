"""
接口层的数据模型（Pydantic Schema）模块

本模块定义前端与服务端之间的数据契约，遵循"Schema <--> Domain"的双向转换模式:

  前端 JSON 字符串 --> 接口数据模型(Schema) --> 领域数据模型(Domain) --> 业务层使用
  业务层使用完(Domain) --> 接口数据模型(Schema) --> 返回给前端

转换职责:
  - ChatRequest (Schema) --> UserMessage (Domain)  由 chat_router._build_user_message 完成
  - ProcessResult (Domain) --> ChatResponse (Schema) 由 chat_router._build_chat_response 完成

ChatObject 字段说明:
  - id: 业务对象唯一标识（如订单号、商品ID等）
  - type: 对象类型标识（如 "order"、"product"）
  - title: 对象的显示标题/名称，可为空
  - attributes: 对象携带的附加属性键值对，默认为空字典
"""

from pydantic import BaseModel
from typing import Any
from audio_cs.domain.messages import ChatHistoryMessage


class ChatObject(BaseModel):
    """前端传递或后端返回的业务对象卡片（如订单、商品等）。"""
    id: str
    type: str
    title: str | None = None
    attributes: dict[str, Any] = {}  # 附加属性键值对，如 {"status": "已发货", "price": "99.00"}


class ChatBotMessage(BaseModel):
    """机器人回复的单条消息，可以是纯文本或业务对象卡片（二选一）。"""
    text: str | None = None  # 纯文本回复内容（与 object 互斥，至少一个非空）
    object: ChatObject | None = None  # 业务对象卡片（与 text 互斥，至少一个非空）


class ChatRequest(BaseModel):
    """前端发送的聊天请求体。"""
    sender_id: str  # 用户唯一标识（对应 X-User-Id）
    text: str | None = None  # 用户输入的文本（TEXT 消息时必填）
    object: ChatObject | None = None  # 用户点击的卡片对象（OBJECT 消息时必填）


class ChatResponse(BaseModel):
    """后端返回的聊天响应体。"""
    sender_id: str  # 机器人标识
    message_id: str  # 本轮对话的消息唯一ID（UUID）
    messages: list[ChatBotMessage]  # 机器人回复消息列表（支持多条消息组合回复）




class AvatarSessionResponse(BaseModel):
    """前端 lm-avatar-chat-sdk 初始化所需会话 JSON。"""
    sessionId: str  # 会话唯一标识
    rtcParams: dict = {}  # 实时通信参数（预留字段，当前未使用）
    avatarAssets: dict = {}  # 数字人资产配置（预留字段，当前未使用）



class ChatMessageResponse(BaseModel):
    """历史对话消息响应体。"""
    sender_id: str  # 用户标识
    messages: list[ChatHistoryMessage]  # 历史对话消息列表


class SessionStateResponse(BaseModel):
    """会话状态响应体。"""
    sender_id: str
    has_active_session: bool
    active_task: dict | None = None  # {flow_id, flow_name, step_id, slots}
    interrupted_tasks: list[dict] = []  # [{flow_id, step_id, slots}]
    focused_object: dict | None = None