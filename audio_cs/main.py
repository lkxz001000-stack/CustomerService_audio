"""
听书智能客服系统 —— 应用入口模块

本模块是 uvicorn 服务器的启动入口。通过读取配置文件中的 host 和 port，
启动 ASGI 应用实例（audio_cs.api.app:app）。

启动方式:
    python -m audio_cs.main
    uv run python -m audio_cs.main

运行条件: 项目根目录下需要存在 .env 文件，配置各项环境变量（LLM、数据库等）。
"""
import logging
import sys
import uvicorn
from audio_cs.config.settings import settings

# ---- 日志配置 ----
LOG_FORMAT = "%(asctime)s [%(levelname)-5s] %(name)s | %(message)s"
LOG_DATE_FORMAT = "%m-%d %H:%M:%S"

logging.basicConfig(
    level=logging.DEBUG,
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT,
    stream=sys.stdout,
)

# 第三方库日志降噪
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("aiomysql").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

if __name__ == '__main__':
    logger.info("启动听书智能客服服务: %s:%s", settings.app_host, settings.app_port)
    uvicorn.run(
        app="audio_cs.api.app:app",
        host=settings.app_host,
        port=settings.app_port,
        log_config=None,  # 禁用 uvicorn 默认日志配置，使用我们的配置
    )
