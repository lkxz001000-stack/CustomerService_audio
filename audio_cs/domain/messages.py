"""
消息领域模型层（Message Domain Model Layer）
============================================

本模块定义了客服系统中所有消息相关的领域数据模型，是整个 DDD 设计中
表现层的核心载体。消息是用户与系统交互的最小单元，贯穿整个对话生命周期。

数据模型层次：
  - MessageType：消息类型枚举（文本 / 对象卡片）
  - FocusedObject：用户点击的卡片对象（订单、专辑、曲目等）
  - UserMessage：用户发送的消息（文本或卡片点击）
  - BotMessage：机器人回复的消息
  - ProcessResult：消息处理结果的聚合体
  - ChatHistoryMessage：用于持久化存储的对话历史消息

所有数据模型均使用 @dataclass(slots=True) 冻结属性，保证：
  1. 对象属性不可动态扩展，类型安全
  2. 内存占用更小（无 __dict__）
  3. 属性访问速度更快（slot 直接寻址）

设计模式：每个模型都提供 to_dict() / from_dict() 用于序列化和反序列化，
配合 DialogueState 的 JSON blob 持久化策略。
"""
from enum import Enum
from typing import Any, Self, Literal
from dataclasses import dataclass, field


class MessageType(Enum):
    """
    消息类型枚举
    -----------
    定义用户与客服系统之间可能的消息交互形式。

    TEXT:   纯文本消息，用户直接输入文字内容
    OBJECT: 对象消息，用户点击了界面上的卡片（如订单卡片、专辑卡片），
            客服系统收到的是结构化 JSON 而非文本
    """
    TEXT = "text"
    OBJECT = "object"


@dataclass(slots=True)
class FocusedObject:
    """
    用户焦点对象（卡片点击数据模型）
    ---------------------------------
    当用户在界面上点击某个卡片（如订单、专辑、曲目）时，前端会将卡片的
    结构化信息传回后端，后端封装为 FocusedObject 对象。

    核心属性：
      - id：   对象唯一标识（订单卡片代表订单编号，专辑卡片代表专辑ID）
      - type： 对象类型标识（"order" / "album" / "track" 等）
      - title：对象展示标题（用户可见的名称）
      - attributes：对象附加属性字典（灵活扩展字段）

    协作关系：
      - 被 UserMessage 引用（用户点击卡片时）
      - 被 BotMessage 引用（机器人回复卡片时）
      - 被 DialogueState.focused_object 持有（当前会话的焦点上下文）
    """
    id: str  # 订单类型卡片代表订单编号，专辑类型卡片代表专辑ID
    type: str  # "order" or "album" or "track"
    title: str | None = None  # 标题
    attributes: dict = field(default_factory=dict)  # 其它属性和属性值

    def to_dict(self) -> dict:
        """
        将 FocusedObject 实例序列化为字典。

        返回:
            dict: 包含 id、type、title、attributes 的字典。
                  其中 attributes 使用浅拷贝（dict()），与原始数据做隔离，
                  防止外部修改影响内部状态。

        注意:
            浅拷贝仅复制字典本身，若 attributes 的值是可变对象
            （如内嵌 list/dict），它们仍然共享引用。如需完全隔离
            需使用 copy.deepcopy()。
        """
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "attributes": dict(self.attributes)  # 浅拷贝 数据做隔离(可变对象会受到影响) copy.deepcopy()深拷贝
        }

    @classmethod
    def from_dict(cls, data: dict[
        str, Any]) -> "FocusedObject":  # 前向引用的解决方案  1."" 变成一个字符串 python解释器直接忽略掉 2.from __future__ import  annotations(早期) 3. Self:返回类实例
        """
        从字典反序列化为 FocusedObject 实例。

        参数:
            data: 包含 id、type、title、attributes 键的字典

        返回:
            FocusedObject: 新构造的实例对象

        Python 前向引用说明:
            返回类型使用字符串 "FocusedObject" 而非直接使用类型名，
            因为此时类体尚未完全定义，Python 解释器会忽略这个字符串，
            等到类型检查阶段再解析。也可用 from __future__ import annotations
            或 typing.Self 来替代这种写法。
        """
        return cls(
            id=data['id'],
            type=data['type'],
            title=data.get('title'),
            attributes=dict(data.get('attributes'))
        )


@dataclass(slots=True)  # 1. 访问速度快__slots__  __dict__() 2. 占用内存空间更小 3.对象的属性个数固定住
class UserMessage:
    """
    用户消息模型
    -----------
    表示用户向客服系统发送的一条消息。这是对话的输入端，所有对话轮次皆由此触发。

    核心属性:
        sender_id:  用户唯一标识（由前端传入，对应听书平台的 X-User-Id）
        message_id: 消息唯一标识（前端未传时由系统通过 uuid 生成）
        type:       消息类型（TEXT 文本输入 / OBJECT 卡片点击）
        text:       文本内容（当 type == TEXT 时有效）
        object:     卡片对象（当 type == OBJECT 时有效）

    TEXT 和 OBJECT 互斥约定:
        当 type == TEXT 时，text 有值、object 为 None
        当 type == OBJECT 时，object 有值、text 为 None

    生命周期:
        ChatRequest（API 层） → UserMessage（本层） → DialogueState.pending_turn
        → Turn.user_message → ChatHistoryMessage（持久化）
    """
    sender_id: str  # 必填参数（用户ID） 前端传过来的
    message_id: str  # 必填参数 (消息ID) 前端没传（扩展） 自己生成自己传入(uuid)
    type: MessageType  # 消息类型(文本以及对象类型)
    text: str | None = None  # 可选
    object: FocusedObject | None = None  # 可选

    def to_dict(self) -> dict[str, Any]:
        """
        将 UserMessage 序列化为字典。

        返回:
            dict: 包含 sender_id、message_id、type（字符串值）、text、object 的字典。
                  type 字段取 .value（如 "text"/"object"），object 字段嵌套调用 to_dict()。
        """
        return {

            "sender_id": self.sender_id,
            "message_id": self.message_id,
            "type": self.type.value,  # 枚举转字符串，如 MessageType.TEXT -> "text"
            "text": self.text,
            "object": self.object.to_dict() if self.object is not None else None  # 嵌套序列化卡片对象
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserMessage":
        """
        从字典反序列化为 UserMessage 实例。

        参数:
            data: 包含 sender_id、message_id、type、text、object 键的字典

        返回:
            UserMessage: 新构造的实例，其中 type 通过 MessageType() 构造器还原为枚举值
        """
        return cls(
            sender_id=data['sender_id'],
            message_id=data['message_id'],
            type=MessageType(data['type']),  # 字符串还原为枚举值
            text=data.get('text'),
            object=FocusedObject.from_dict(data['object']) if data.get('object') else None  # 递归反序列化卡片对象
        )


@dataclass(slots=True)
class BotMessage:
    """
    机器人回复消息模型
    -----------------
    表示客服机器人向用户返回的一条回复消息。由引擎处理完用户请求后生成。

    核心属性:
        text:   回复的文本内容。无论是业务流程的结果文本、知识查询的答案，
                还是闲聊的回复，最终都会赋值到 text 属性。
        object: 回复的卡片对象（扩展点，当前业务场景较少使用）。

    与 UserMessage 的关系:
        UserMessage 是 Turn 的输入，BotMessage 是 Turn 的输出。
        一轮对话中一个 UserMessage 可以对应多个 BotMessage（列表形式）。
    """
    text: str | None = None  # 应用的内容结果都会给text属性
    object: FocusedObject | None = None  # 扩展点

    def to_dict(self) -> dict[str, Any]:
        """
        将 BotMessage 序列化为字典。

        返回:
            dict: 包含 text、object 键的字典。object 为 None 时不展开。
        """
        return {
            "text": self.text,
            "object": self.object.to_dict() if self.object is not None else None
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """
        从字典反序列化为 BotMessage 实例。

        参数:
            data: 包含 text、object 键的字典

        返回:
            BotMessage: 新构造的实例。使用 typing.Self 标注返回类型。
        """
        return cls(
            text=data.get('text'),
            object=FocusedObject.from_dict(data['object']) if data.get('object') else None
        )


@dataclass(slots=True)
class ProcessResult:
    """
    消息处理结果聚合体
    -----------------
    封装引擎处理完一条用户消息后的完整输出，作为 service 层与 api 层之间的
    数据传输对象（DTO）。

    核心属性:
        sender_id:  对应用户唯一标识，api 层据此路由回复到正确的 SSE 连接
        message_id: 对应的用户消息 ID，用于前端做消息关联（request-id 模式）
        messages:   BotMessage 列表，一条用户消息可能产生多条机器人回复

    设计意图:
        将处理结果从领域模型中解耦出来，service 层不需要关心如何把回复
        推送给前端（SSE / WebSocket / 轮询），只需返回 ProcessResult，
        api 层负责实际的推送机制。
    """
    sender_id: str
    message_id: str
    messages: list[BotMessage]


@dataclass(slots=True)
class ChatHistoryMessage:
    """
    对话历史消息模型（持久化用）
    --------------------------
    用于存储到数据库的简化消息模型。相比 Turn（包含完整的 UserMessage 和
    BotMessage 列表），ChatHistoryMessage 是扁平化的单条记录。

    核心属性:
        session_id: 所属会话标识
        role:       角色标识（"user" 或 "bot"），使用 Literal 约束合法值
        text:       消息文本内容
        object:     关联的卡片对象（可选）

    与 Turn 的关系:
        ChatHistoryMessage 是 Turn 的扁平化投影。一个 Turn 可以拆成多条
        ChatHistoryMessage（1 条 user + N 条 bot），便于按时间线查询对话历史。
    """
    session_id: str
    role: Literal["user", "bot"]
    text: str | None = None
    object: FocusedObject | None = None
