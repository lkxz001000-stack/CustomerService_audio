"""
SQLAlchemy 声明式基类模块

通过 DeclarativeBase 创建统一的 ORM 基类 Base，项目内所有 ORM 模型类
均继承自此 Base。Base 内置了 DeclarativeBase 的元数据注册机制，使得
SQLAlchemy 能够自动发现和管理所有继承自 Base 的表映射类。
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
