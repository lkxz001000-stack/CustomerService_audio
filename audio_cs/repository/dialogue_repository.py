"""
对话状态持久层（Repository）模块

本模块负责 DialogueState 的数据库读写操作，遵循 DDD 的 Repository 模式，
将领域对象与 ORM 存储细节隔离开来。

核心设计: UPSERT 模式（INSERT ... ON DUPLICATE KEY UPDATE）
  - 如果 sender_id 对应的记录不存在，执行 INSERT 创建新记录
  - 如果 sender_id 对应的记录已存在（主键冲突），执行 UPDATE 覆盖 state_json
  - 这种模式简化了业务层逻辑，无需判断"是否存在"再决定 add/update，
    一条 SQL 完成所有操作，同时也避免了并发下的竞态条件。
"""
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert

from audio_cs.model.state_record import DialogueStateRecord
from audio_cs.domain.state import DialogueState

logger = logging.getLogger(__name__)


class DialogueRepository:
    """
    对话状态的持久层组件（读写数据库 dialogue_states 表）。

    每个方法接收或返回领域对象 DialogueState，内部负责
    与数据库记录的序列化/反序列化转换。
    """

    def __init__(self, session: AsyncSession):
        """
        :param session: 请求级异步数据库会话，由 FastAPI DI 注入
        """
        self.session = session

    async def load_dialogue(self, sender_id: str) -> DialogueState:
        """
        根据 sender_id 查询用户的对话状态。

        查询流程:
          1. 定义 SELECT SQL（按主键 sender_id 查询）
          2. 执行 SQL
          3. 获取单条结果:
             - 找到 -> 将 JSON 反序列化为 DialogueState 领域对象
             - 未找到 -> 返回空的 DialogueState（新用户，无历史对话）

        :param sender_id: 用户唯一标识
        :return: 对话状态领域对象（新用户则为空白状态）
        """

        # 1. 定义查询的SQL
        stmt = select(DialogueStateRecord).where(DialogueStateRecord.sender_id == sender_id)

        # 2. 执行SQL
        cursor = await self.session.execute(stmt)

        # 3. 获取结果
        result = cursor.scalar_one_or_none()

        if result:
            logger.debug("加载已有对话状态: sender_id=%s", sender_id)
            return DialogueState.from_dict(json.loads(result.state_json))

        logger.debug("创建新对话状态: sender_id=%s", sender_id)
        return DialogueState(sender_id=sender_id)

    async def save_dialogue(self, dialogue_state: DialogueState):
        """
        保存对话状态到数据库（UPSERT 模式）。

        处理逻辑:
          1. 将 DialogueState 领域对象序列化为 JSON 字符串
          2. 使用 MySQL 的 INSERT ... ON DUPLICATE KEY UPDATE 语法:
             - sender_id 不存在 -> 新增记录
             - sender_id 已存在 -> 更新 state_json 字段
          3. 执行 SQL 并提交事务

        注意: 使用 ensure_ascii=False 确保中文字符正常存储，
              不会转义为 \\uXXXX 格式。

        :param dialogue_state: 需要持久化的对话状态领域对象
        """

        # 1. 序列化
        dialogue_str = json.dumps(dialogue_state.to_dict(), ensure_ascii=False)

        # 2. 定义SQL
        insert_stmt = insert(DialogueStateRecord).values(
            sender_id=dialogue_state.sender_id, state_json=dialogue_str
        )

        # UPSERT: insert 语句升级到 update 语句，条件是主键重复（sender_id 冲突）
        # on_duplicate_key_update 是 MySQL 特有的语法
        upsert_stmt = insert_stmt.on_duplicate_key_update(
            state_json=insert_stmt.inserted.state_json
        )

        # 3. 执行SQL
        await self.session.execute(upsert_stmt)

        # 4. commit
        await self.session.commit()
