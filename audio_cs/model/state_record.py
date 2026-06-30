"""
对话状态 ORM 模型（DialogueStateRecord --> 数据库表 dialogue_states）

本模块定义对话状态在 MySQL 中的持久化结构，是从领域对象（DialogueState）
到关系型数据库表的映射桥梁。

ORM 到 Domain 的映射关系:
  DialogueStateRecord (ORM)  <-->  DialogueState (Domain)
  ------------------------------------
  sender_id   (主键列)       <-->  sender_id (用户标识)
  state_json  (TEXT列)       <-->  整个 DialogueState 对象序列化为 JSON

设计说明:
  - 对话状态不在关系型表中展开为多列，而是整体序列化为一个 JSON blob
  - state_json 是一个"大口袋"字段，存放 DialogState 的完整状态
    包括: 当前流程(flow_id)、流程索引(flow_index)、槽位(slots)、
    历史轮次(turns)等所有运行时信息
  - 这种设计的优势是灵活（领域模型变更不需要改表结构），
    代价是无法对 JSON 内部字段做高效的 SQL 查询

映射类型:
  - Mapped[str]: 为静态类型检查工具（mypy/pyright）提供类型提示，
    同时让 SQLAlchemy 自动推断数据库列类型
  - mapped_column(TEXT): 显式指定数据库列类型为 TEXT（长文本），
    覆盖 Mapped 类型推断的 VARCHAR 默认值
"""
from audio_cs.model.base import Base
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import TEXT


class DialogueStateRecord(Base):
    """
    对话框状态表 ORM 模型。

    mapped_column: 定义字段的约束（是否为空、是否主键、是否建立索引等元数据）
    Mapped: 给静态检查工具做类型提示、自动将 Python 类型映射到数据库列类型

    表结构:
      sender_id  VARCHAR(主键)  -- 用户唯一标识
      state_json TEXT(非空)     -- 对话状态 JSON blob
    """
    __tablename__ = 'dialogue_states'

    # Python 中定义的字段类型 str --> 类型推断为 VARCHAR 类型，但因 primary_key=True 会调整
    sender_id: Mapped[str] = mapped_column(primary_key=True)
    # 数据库中该列显式指定为 TEXT（长文本），适合存储完整的 JSON 状态数据
    state_json: Mapped[str] = mapped_column(TEXT, nullable=False, default={})
