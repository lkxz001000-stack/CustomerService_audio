"""
LLM 客户端模块

本模块负责初始化和管理大语言模型客户端。使用 LangChain 的 init_chat_model
（1.x 版本之后推荐写法）创建兼容 OpenAI 接口格式的聊天模型实例。

模型提供商配置:
  - model_provider="openai": 使用 OpenAI 兼容的 API 协议
  - 实际后端由 base_url 指定（阿里云 DashScope: dashscope.aliyuncs.com）
  - 模型名由 .env 中的 LLM_MODEL 配置（如 qwen-plus）

关键参数说明:
  - temperature=0: 设置为 0 以最大程度保证输出的稳定性和确定性，
    避免对话引擎中的规划、路由等关键决策因随机性产生不一致的结果。
  - timeout=120: HTTP 请求超时时间，单位为秒，给 LLM 推理留足缓冲。
"""
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from audio_cs.config.settings import settings

# 全局 LLM 客户端单例，应用启动时模块加载即初始化
llm_client: BaseChatModel = init_chat_model(
    model=settings.llm_model,
    model_provider="openai",  # 兼容 OpenAI 协议的 API 提供商
    base_url=settings.llm_base_url,
    api_key=settings.llm_api_key,
    temperature=0,  # 尽最大努力保证输出的稳定性（确定性输出）
    timeout=120
)

if __name__ == '__main__':
    response = llm_client.invoke("你好，我现在心情不好，给我讲一个幽默的笑话，确保能让我笑")

    print(response.content)
