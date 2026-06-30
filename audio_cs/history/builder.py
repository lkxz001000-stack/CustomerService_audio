"""
聊天历史构建器模块

本模块负责将对话历史（DialogueState 中的 Turn 列表）转换为
LLM 可理解的纯文本格式历史记录，供 TurnPlanner 在规划阶段
作为上下文的一部分注入提示词中。

同时提供面向前端的结构化历史消息构建能力。

文本格式约定:
  USER: {用户消息内容}
  BOT: {机器人回复内容}
  USER: ...
  BOT: ...

文本消息直接使用原文，对象消息（卡片点击）渲染为:
  [id=xxx label=订单/商品 title=xxx attributes=k1=v1 k2=v2]

关于之前修复的 None text bug:
  _render_text_msg 使用 (text or "").strip() 而非 text.strip()，
  确保 text 为 None 时不抛 AttributeError，而是返回空字符串。
"""
from typing import Literal

from audio_cs.domain.state import Turn
from audio_cs.domain.messages import UserMessage, BotMessage, FocusedObject, MessageType, ChatHistoryMessage


class ChatHistoryBuilder:
    """对话历史构建器，提供纯文本和结构化两种历史输出格式。"""

    @staticmethod
    def build(turns: list[Turn]) -> str:
        """
        构建用于 LLM 上下文的纯文本格式对话历史。

        遍历所有的 Turn（对话轮次），每个 Turn 包含一个用户消息和
        若干机器人回复消息，按 Q/A 交替格式拼接为多行文本。

        遍历逻辑（嵌套循环）:
          外层 for: 遍历每个 Turn（一轮对话）
            内层 for: 遍历该轮中机器人的所有 BotMessage（可能有多条）

        输出格式示例:
          USER: 我的订单状态是什么？
          BOT: 您的订单已发货，预计3天内送达。
          USER: [id=A20260410001 label=订单 title=xxx attributes=status=已发货]
          BOT: 该订单当前状态为"已发货"。

        :param turns: 对话历史中的所有轮次
        :return: 拼接后的纯文本历史字符串（每行一条消息）
        """
        chat_messages = []
        # 外层循环: 遍历每个对话轮次
        for turn in turns:
            # 1. 先获取用户角色消息(Q)
            user_message = turn.user_message
            user_msg_str = ChatHistoryBuilder.process_user_message(user_message)
            chat_messages.append(f"USER: {user_msg_str}")

            # 2. 接着处理机器人回复消息(A) —— 一轮中机器人可能回复多条消息
            bot_messages = turn.bot_messages
            for bot_msg in bot_messages:
                bot_msg_str = ChatHistoryBuilder._process_bot_message(bot_msg)
                chat_messages.append(f"BOT: {bot_msg_str}")

        return "\n".join(chat_messages)

    @staticmethod
    def process_user_message(user_message: UserMessage) -> str:
        """
        将用户消息转换为纯文本字符串。

        根据消息类型分支:
          - TEXT 类型: 直接取文本内容
          - OBJECT 类型: 渲染为对象描述字符串 [id=..., label=..., ...]

        :param user_message: 用户消息领域对象
        :return: 用户消息的文本表示
        """
        if user_message.type is MessageType.TEXT:
            return ChatHistoryBuilder._render_text_msg(user_message.text)

        return ChatHistoryBuilder._render_obj_msg(user_message.object)

    @staticmethod
    def _process_bot_message(bot_msg: BotMessage) -> str:
        """
        将机器人消息转换为纯文本字符串。

        机器人消息可能是纯文本（text 有值）或对象卡片（object 有值），
        优先处理文本消息。

        :param bot_msg: 机器人消息领域对象
        :return: 机器人消息的文本表示
        """
        if bot_msg.text:  # 有值：纯文本消息
            return ChatHistoryBuilder._render_text_msg(bot_msg.text)

        return ChatHistoryBuilder._render_obj_msg(bot_msg.object)

    @staticmethod
    def _render_text_msg(text: str | None) -> str:
        """
        渲染纯文本消息。

        使用 (text or "").strip() 而非 text.strip() 的原因是:
        当 text 为 None 时，text.strip() 会抛出 AttributeError，
        (text or "") 会将 None 安全地转换为空字符串再调用 .strip()。

        :param text: 消息文本内容（可能为 None）
        :return: 去除首尾空白后的文本字符串
        """
        return (text or "").strip()

    @staticmethod
    def _render_obj_msg(object: FocusedObject) -> str:
        """
        渲染对象（卡片点击）消息为标准文本格式。

        对于"订单"类型，label 显示为"订单"；
        其他类型（如商品）显示为"商品"。

        输出格式: [id=xxx label=xxx title=xxx attributes=k1=v1 k2=v2]

        :param object: 用户点击的聚焦对象
        :return: 对象的文本表示
        """
        # 根据对象类型确定中文标签
        label = "订单" if object.type == "order" else "商品"
        id = object.id
        title = object.title
        # 将属性字典渲染为 "k1=v1 k2=v2" 格式
        attributes_str = " ".join([f"{k}={v}" for k, v in object.attributes.items()])

        return f"[id={id} label={label} title={title} attributes={attributes_str}]"

    @staticmethod
    def build_chat_history(session_id: str,
                           role: Literal["user", "bot"],
                           text: str | None,
                           object: FocusedObject | None):
        """
        构建面向前端的结构化历史消息对象。

        将领域数据组装为 ChatHistoryMessage，用于 /api/chat/history 端点
        返回给前端渲染历史对话界面。

        :param session_id: 会话（用户）标识
        :param role: 消息角色，取值 "user" 或 "bot"
        :param text: 消息文本内容（可为 None）
        :param object: 消息附带的对象卡片（可为 None）
        :return: 结构化的历史消息对象
        """
        return ChatHistoryMessage(
            session_id=session_id,
            role=role,
            text=text,
            object=object
        )
