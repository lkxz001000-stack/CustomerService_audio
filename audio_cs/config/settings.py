"""
应用配置模块

从项目根目录的 .env 文件中收集所有配置信息，利用 pydantic-settings 的
BaseSettings 机制自动完成类型校验和类型转换（如端口号字符串 --> int）。

支持的配置键（均需在 .env 文件中定义）:
  LLM_MODEL          - 大语言模型名称（如 qwen-plus）
  LLM_BASE_URL       - LLM 服务商 API 地址（兼容 OpenAI 格式）
  LLM_API_KEY        - LLM 服务商 API 密钥
  AUDIO_API_BASE_URL - 听书平台数据后台 API 地址（模拟业务数据源）
  DATABASE_URL       - MySQL 异步连接字符串（格式: mysql+aiomysql://user:pass@host:port/db）
  APP_HOST           - 应用监听地址（0.0.0.0 表示监听所有网卡）
  APP_PORT           - 应用监听端口
"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录 = config/ 上两层
PROJECT_ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_FILE_PATH = PROJECT_ROOT_DIR / ".env"


class Settings(BaseSettings):
    """
    BaseSettings 利用 Pydantic 机制对配置信息做类型校验和类型转换。

    各字段说明:
      llm_model: LLM 模型名称，传递给 langchain init_chat_model
      llm_base_url: LLM 服务商的 API 端点，兼容 OpenAI 接口格式
      llm_api_key: API 认证密钥，用于请求鉴权
      audio_api_base_url: 听书平台数据后台的基础 URL，客服系统通过此地址查询订单、记录等
      database_url: 异步 MySQL 连接 URL，使用 aiomysql 驱动
      app_host: uvicorn 绑定的 IP 地址，0.0.0.0 表示监听所有网络接口
      app_port: uvicorn 绑定的 TCP 端口号，Pydantic 自动从字符串转换为 int
    """
    llm_model: str
    llm_base_url: str
    llm_api_key: str
    audio_api_base_url: str
    database_url: str
    app_host: str
    app_port: int

    # extra="ignore" 允许 .env 中存在未定义的额外键而不会报错
    model_config=SettingsConfigDict(env_file=ENV_FILE_PATH, env_file_encoding="utf-8", extra="ignore")  # extra="ignore"


settings = Settings()  # type: ignore

if __name__ == '__main__':
    print(settings.llm_base_url)
