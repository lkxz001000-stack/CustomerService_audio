"""
听书智能客服系统 —— 应用入口模块

本模块是 uvicorn 服务器的启动入口。通过读取配置文件中的 host 和 port，
启动 ASGI 应用实例（audio_cs.api.app:app）。

启动时自动拉起 audio-data 数据后台子进程，退出时自动关闭。

启动方式:
    python -m audio_cs.main
    uv run python -m audio_cs.main

运行条件: 项目根目录下需要存在 .env 文件，配置各项环境变量（LLM、数据库等）。
"""
import logging
import sys
import time
import subprocess
import signal
import os
import uvicorn
import httpx
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

# audio-data 项目路径（相对于本项目的同级目录）
_AUDIO_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "25_尚硅谷大模型项目实战之掌柜小二实战", "audio-data")
)
_AUDIO_DATA_PROC: subprocess.Popen | None = None
_AUDIO_DATA_READY_MAX_WAIT = 30  # 最多等待 30 秒


def _start_audio_data() -> subprocess.Popen | None:
    """启动 audio-data 数据后台子进程。"""
    if not os.path.isdir(_AUDIO_DATA_DIR):
        logger.warning("audio-data 项目目录不存在: %s，跳过启动", _AUDIO_DATA_DIR)
        return None

    logger.info("启动 audio-data 数据后台: %s", _AUDIO_DATA_DIR)
    try:
        proc = subprocess.Popen(
            ["uv", "run", "-m", "app.main"],
            cwd=_AUDIO_DATA_DIR,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        return proc
    except Exception:
        logger.exception("audio-data 启动失败")
        return None


def _wait_audio_data_ready() -> bool:
    """轮询等待 audio-data 健康检查就绪。"""
    url = f"{settings.audio_api_base_url}/health"
    deadline = time.time() + _AUDIO_DATA_READY_MAX_WAIT
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=2, trust_env=False)
            if r.status_code == 200:
                logger.info("audio-data 数据后台就绪")
                return True
        except Exception:
            pass
        time.sleep(1)
    logger.warning("audio-data 数据后台在 %s 秒内未就绪", _AUDIO_DATA_READY_MAX_WAIT)
    return False


def _stop_audio_data():
    """关闭 audio-data 子进程。"""
    global _AUDIO_DATA_PROC
    if _AUDIO_DATA_PROC is None:
        return
    logger.info("正在关闭 audio-data 数据后台...")
    _AUDIO_DATA_PROC.terminate()
    try:
        _AUDIO_DATA_PROC.wait(timeout=10)
    except subprocess.TimeoutExpired:
        _AUDIO_DATA_PROC.kill()
        _AUDIO_DATA_PROC.wait()
    logger.info("audio-data 数据后台已关闭")


def _cleanup_handler(signum=None, frame=None):
    """信号/退出时的清理回调。"""
    _stop_audio_data()


# 注册退出信号和正常退出时的清理回调
signal.signal(signal.SIGINT, _cleanup_handler)
signal.signal(signal.SIGTERM, _cleanup_handler)
import atexit
atexit.register(_stop_audio_data)


if __name__ == '__main__':
    # 1. 启动 audio-data 数据后台
    _AUDIO_DATA_PROC = _start_audio_data()
    if _AUDIO_DATA_PROC:
        _wait_audio_data_ready()

    # 2. 启动客服服务
    logger.info("启动听书智能客服服务: %s:%s", settings.app_host, settings.app_port)
    uvicorn.run(
        app="audio_cs.api.app:app",
        host=settings.app_host,
        port=settings.app_port,
        log_config=None,
    )
