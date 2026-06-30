"""
数据库会话管理模块

本模块负责异步数据库引擎和会话工厂的创建与管理。
使用 SQLAlchemy 2.x 的异步 API（AsyncEngine + AsyncSession），
通过 aiomysql 驱动连接 MySQL 数据库。

核心组件:
  - engine: 全局异步数据库引擎，管理连接池
  - session_factory: 异步会话工厂，每次请求创建一个新的 AsyncSession

关键设计说明:
  - expire_on_commit=False:
    在同步环境下，commit 后访问对象属性会触发自动查询数据库获取最新值，
    但在异步环境下，commit 后访问已过期属性会报错（不能用 await 读取自动刷新的属性）。
    设置为 False 后，commit 不会将对象标记为过期，属性值保留在内存中，
    避免了异步环境下的过期属性访问问题。
"""
import logging
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text

from audio_cs.config.settings import settings

logger = logging.getLogger(__name__)

# 全局异步数据库引擎（应用启动时初始化，关闭时释放）
engine: AsyncEngine | None = None

# 全局异步会话工厂（基于 engine 创建，用于生成请求级会话）
session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db_engine():
    global engine, session_factory
    engine = create_async_engine(settings.database_url, echo=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    logger.info("数据库引擎初始化完成")


async def dispose_engine():
    await engine.dispose()
    logger.info("数据库引擎已释放")


async def main():
    """本地测试入口：初始化引擎后执行一条简单的 SELECT 查询。"""
    await init_db_engine()

    async with session_factory() as session:   # async别漏
        result = await  session.execute(text("select  1"))  # 防止sql注入
        print(result.fetchone())


import asyncio

if __name__ == '__main__':
    asyncio.run(main())
