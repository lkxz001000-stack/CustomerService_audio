"""
知识提供者基类与数据模型

定义知识检索层的核心抽象：
- KnowledgeChunk：检索返回的知识片段数据模型，封装从各数据源获取的文本内容
- KnowledgeProvider：所有知识提供者必须实现的抽象基类，定义统一的检索接口

设计意图（Provider 契约）：
所有具体提供者（APIProvider、FAQProvider、RAGProvider 等）必须：
1. 声明唯一的 provider_id 类属性，用于注册和查找
2. 实现 retrieve() 方法，接收 DialogueState 并返回 KnowledgeChunk 列表

这种设计使得 Handler 可以通过统一接口调用不同的数据源，
新增数据源只需添加新的 Provider 子类并注册即可，无需修改调用方代码。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from audio_cs.domain.state import DialogueState

@dataclass
class KnowledgeChunk:
    """知识片段数据模型

    封装从单个数据源检索到的一条知识信息。多个提供者返回的 Chunk
    最终会汇总拼接后注入 LLM 提示词，作为生成回复的参考素材。

    Attributes:
        content: 检索到的文本内容，可以是 API 返回的 JSON 格式化文本、
                 FAQ 的固定答案或 RAG 检索到的文档片段
    """
    content: str   # 检索到的内容


class KnowledgeProvider(ABC):
    """知识提供者抽象基类

    所有知识数据源的统一接口。每个子类代表一种数据检索方式：
    - API 类：调用后端 HTTP 接口获取实时数据（如专辑、订单信息）
    - FAQ 类：返回预设的常见问题解答
    - RAG 类：从向量知识库中检索相关文档

    Attributes:
        provider_id: 提供者唯一标识符（类属性），用于在注册表中索引。
                     子类必须重写此属性。格式约定：{类型}.{名称}，
                     如 "api.album"、"faq.default"、"rag.default"
    """
    provider_id = ""

    @abstractmethod
    async def retrieve(
            self,
            state: DialogueState,
    ) -> list[KnowledgeChunk]:
        """从数据源检索相关知识

        抽象方法，所有子类必须实现。根据当前对话状态中的上下文信息
        （用户ID、焦点对象、对话历史等），从对应的数据源检索相关知识。

        Args:
            state: 对话状态对象，包含 sender_id（用户标识）、
                   focused_object（用户关注的焦点对象）、
                   current_session()（当前会话）等上下文信息

        Returns:
            KnowledgeChunk 列表，每个元素包含一段检索到的文本内容。
            如果没有检索到有效数据，应返回包含提示信息的 Chunk
            （如 "未找到专辑信息"），而非空列表。
        """
        pass



