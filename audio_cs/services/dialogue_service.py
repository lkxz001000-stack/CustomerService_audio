import logging
from audio_cs.domain.messages import ProcessResult, UserMessage, ChatHistoryMessage
from audio_cs.repository.dialogue_repository import DialogueRepository
from audio_cs.domain.state import DialogueState
from audio_cs.engine.dialogue_engine import DialogueEngine
from audio_cs.history.builder import ChatHistoryBuilder

logger = logging.getLogger(__name__)


class DialogueService:
    def __init__(self,
                 repository: DialogueRepository,
                 engine: DialogueEngine):
        self.repository = repository
        self.engine = engine

    async def hand_dialogue(self, user_message: UserMessage) -> ProcessResult:
        # 1. 读（Read）：从数据库中读取用户的对话状态
        dialogue_state: DialogueState = await self.repository.load_dialogue(user_message.sender_id)
        logger.debug("加载对话状态: sender_id=%s, session_count=%d",
                     user_message.sender_id, len(dialogue_state.sessions))

        # 2. 算（Compute）：将消息委托给引擎处理
        process_result: ProcessResult = await self.engine.hand_message(user_message, dialogue_state)

        # 3. 写（Write）：将处理后的对话状态持久化回数据库
        await self.repository.save_dialogue(dialogue_state)
        logger.debug("对话状态已持久化: sender_id=%s", user_message.sender_id)

        return process_result

    async def load_chat_history(self, sender_id: str) -> list[ChatHistoryMessage]:
        """
        加载用户的完整聊天历史

        从数据库加载对话状态后，遍历所有会话（sessions）和轮次（turns），
        将用户消息和机器人回复按时间顺序展平为 ChatHistoryMessage 列表。

        遍历结构（两层循环 + 一层嵌套）：
        - 外层循环：遍历 sessions（每次会话可能有多个 turn）
          - 内层循环：遍历每个 session 的 turns
            - 处理 user_message（用户消息）
            - 嵌套循环：遍历每个 turn 的 bot_messages（一个 turn 可能产生多条机器人回复）

        :param sender_id: 用户标识（X-User-Id）
        :return: ChatHistoryMessage 列表，按会话轮次时间顺序排列，可直接用于前端渲染
        """

        # 1. 根据 sender_id 查询对话状态
        dialogue_state = await self.repository.load_dialogue(sender_id)

        # 2. 获取所有历史会话（sessions 列表）
        user_sessions = dialogue_state.sessions

        result = []

        # 3. 遍历所有历史会话
        #    外层循环：遍历 user_sessions 列表中的每一个 session
        for session in user_sessions:

            # 内层循环：遍历当前 session 中的每一个 turn（对话轮次）
            for turn in session.turns:

                # 3.1 处理用户角色的历史消息
                #     每个 turn 有且仅有一个 user_message
                user_message = turn.user_message
                user_history_message = ChatHistoryBuilder.build_chat_history(session_id=session.session_id,
                                                                             role="user",
                                                                             text=user_message.text,
                                                                             object=user_message.object)
                result.append(user_history_message)

                # 3.2 处理机器人角色的历史消息
                #     一个 turn 可能有多个 bot_messages（例如同时发送文本+卡片）
                bot_messages = turn.bot_messages

                # 嵌套循环：遍历当前 turn 的所有机器人回复消息
                for bot_message in bot_messages:
                    bot_history_message = ChatHistoryBuilder.build_chat_history(
                        session_id=session.session_id,
                        role="bot",
                        text=bot_message.text,
                        object=bot_message.object
                    )
                    result.append(bot_history_message)
        return result
