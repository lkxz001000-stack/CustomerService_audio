"""
FastAPI 应用工厂模块

本模块负责:
1. 创建 FastAPI 应用实例并配置生命周期（lifespan）
2. 在启动阶段初始化数据库引擎、HTTP客户端、对话引擎
3. 在关闭阶段释放数据库连接池和HTTP客户端资源
4. 挂载静态文件目录（static/）用于前端页面托管
5. 注册 chat 路由和根路径重定向
"""
from pathlib import Path
import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from contextlib import asynccontextmanager
from audio_cs.api.router.chat_router import router
from audio_cs.infrastructure.db import init_db_engine, dispose_engine
from audio_cs.infrastructure.http_client import init_http_client, dispose_http_client
from audio_cs.api.dependencies import init_dialogue_engine

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ===== 启动阶段（Init Phase）=====
    logger.info("初始化数据库引擎...")
    await init_db_engine()
    logger.info("初始化 HTTP 客户端...")
    init_http_client()
    logger.info("构建对话引擎...")
    init_dialogue_engine()
    logger.info("听书智能客服系统启动完成")
    yield
    # ===== 关闭阶段（Dispose Phase）=====
    logger.info("正在关闭数据库连接池...")
    await dispose_engine()
    logger.info("正在关闭 HTTP 客户端...")
    await dispose_http_client()
    logger.info("听书智能客服系统已关闭")


app = FastAPI(description="听书智能客服V1.0", lifespan=lifespan)
app.include_router(router)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")
