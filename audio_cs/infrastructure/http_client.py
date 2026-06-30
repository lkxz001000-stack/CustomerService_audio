"""
HTTP 客户端模块

本模块管理全局异步 HTTP 客户端（基于 httpx.AsyncClient），用于调用
听书平台数据后台（audio-data 项目）的 REST API 接口。

设计说明:
  - 全局单例模式: 模块级 http_client 变量在应用启动时初始化，关闭时释放，
    避免每次请求都创建/销毁连接的开销。
  - trust_env=False:
    阻止 httpx 从系统环境变量（如 HTTP_PROXY、SSL_CERT_FILE 等）读取代理
    和证书配置，确保客户端使用纯代码配置的连接参数，避免被宿主机环境变量
    意外干扰（尤其在容器化部署时很重要）。
"""
import asyncio
import logging
from httpx import AsyncClient

logger = logging.getLogger(__name__)

# 全局 HTTP 客户端单例
http_client: AsyncClient | None = None


def init_http_client():
    global http_client
    http_client = AsyncClient(timeout=120, trust_env=False)
    logger.info("HTTP 客户端初始化完成")


async def dispose_http_client():
    await http_client.aclose()
    logger.info("HTTP 客户端已关闭")


async def main():
    """本地测试入口：初始化客户端后发送 GET 请求到听书平台数据后台。"""
    init_http_client()

    # response = await http_client.get(url="http://111.228.53.183:18081/orders/A20260410001")
    response = await http_client.get(url="http://192.168.200.125:18081/orders/A20260410001")


    print(response)


if __name__ == '__main__':
    asyncio.run(main())
