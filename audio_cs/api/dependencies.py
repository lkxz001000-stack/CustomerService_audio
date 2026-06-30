"""
FastAPI 依赖注入（DI）链模块

本模块构建了从基础设施到业务服务的完整依赖注入链条:

  依赖链（自底向上）:
    数据库会话工厂 --> AsyncSession --> DialogueRepository --> DialogueService
    配置文件     --> DialogueEngine  -->                              /

  注入方式:
    使用 FastAPI 的 Annotated[Type, Depends(callable)] 模式，
    将每个依赖包装为可复用的类型别名（*Dep），在路由函数签名中直接使用。

关于 `import audio_cs.infrastructure.db` 使用模块级导入的原因:
  该模块中的 session_factory 是一个模块级可变变量，在应用启动阶段
  由 init_db_engine() 动态赋值。如果使用 `from audio_cs.infrastructure.db import session_factory`，
  则只是将 import 时刻的值拷贝到当前模块的命名空间，后续 session_factory 被重新赋值时
  不会同步更新。因此必须使用模块级导入 `import audio_cs.infrastructure.db`，
  然后通过 `db.session_factory()` 调用，以延迟属性查找，确保每次获取的都是最新值。
"""
import logging
from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from audio_cs.services.dialogue_service import DialogueService
from audio_cs.engine.dialogue_engine import DialogueEngine
from audio_cs.repository.dialogue_repository import DialogueRepository
from audio_cs.infrastructure import db
from audio_cs.engine.builder import build_dialogue_engine

logger = logging.getLogger(__name__)

# 对话引擎全局单例，在 lifespan 启动阶段通过 init_dialogue_engine() 初始化
dialogue_engine: DialogueEngine | None = None

def init_dialogue_engine():
    global dialogue_engine
    dialogue_engine = build_dialogue_engine()
    logger.info("对话引擎单例构建完成")


def get_engine():
    """
    获取对话引擎实例。

    作为 FastAPI Depends 的工厂函数，每次请求时被调用，
    返回应用启动时初始化好的引擎全局单例。
    """
    return dialogue_engine


# FastAPI 依赖注入类型别名：对话引擎
DialogueEngineDep = Annotated[DialogueEngine, Depends(get_engine)]


async def get_session():
    """
    获取异步数据库会话（请求级生命周期）。

    使用 async with 从会话工厂创建一个新的 AsyncSession，
    请求处理完毕后自动关闭会话并归还连接到连接池。
    yield 之后的代码在 FastAPI 处理完请求后自动执行。
    """
    async with db.session_factory() as session:
        yield session  # FASTAPI 处理完请求（业务用完了）自动进入到该位置


# FastAPI 依赖注入类型别名：异步数据库会话
RepositorySessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_repository(session: RepositorySessionDep):
    """
    构建对话持久层组件。

    :param session: FastAPI 注入的异步数据库会话
    :return: 绑定到当前请求会话的 DialogueRepository 实例
    """
    return DialogueRepository(session=session)


# FastAPI 依赖注入类型别名：对话仓库
DialogueRepositoryDep = Annotated[DialogueRepository, Depends(get_repository)]


def get_dialogue_service(engine: DialogueEngineDep,
                         repo: DialogueRepositoryDep
                         ):
    """
    构建对话服务编排层组件。

    将对话引擎（处理逻辑）和对话仓库（持久化）组合为完整的 DialogueService，
    在 API 路由层使用，负责加载/保存 DialogueState 并委托引擎处理。

    :param engine: FastAPI 注入的对话引擎单例
    :param repo: FastAPI 注入的对话仓库实例（绑定请求级会话）
    :return: 组装好的 DialogueService 实例
    """
    return DialogueService(
        repository=repo,
        engine=engine
    )


# Annotated:将类型以及类型的元素
# FastAPI 依赖注入类型别名：对话服务（最上层，供路由直接使用）
DialogueServiceDep = Annotated[DialogueService, Depends(get_dialogue_service)]
