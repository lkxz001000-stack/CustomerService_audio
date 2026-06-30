"""知识提供者注册表"""

from audio_cs.knowledge.providers.knowledge import KnowledgeProvider

class KnowledgeProviderRegistry:
    """知识提供者注册表

    管理所有知识提供者实例，按 provider_id 建立索引，提供快速查找能力。

    注册表模式（Registry Pattern）的作用：
    1. 集中管理：所有提供者实例在应用启动时统一注册，避免散落各处
    2. 解耦查找：调用方只需知道 provider_id 即可获取提供者，不依赖具体类名或导入路径
    3. 便于扩展：新增提供者只需在初始化时传入列表，无需修改注册表和调用方代码

    使用方式：
        registry = KnowledgeProviderRegistry([AlbumAPIProvider(), FAQProvider(), ...])
        provider = registry.get("api.album")  # 返回 AlbumAPIProvider 实例

    Attributes:
        _providers_by_id: 内部字典，key=provider_id（如 "api.album"），value=提供者实例
    """

    def __init__(self, providers: list[KnowledgeProvider]) -> None:
        """初始化注册表

        将所有提供者按 provider_id 索引存入内部字典。

        Args:
            providers: 知识提供者实例列表，每个实例必须具有唯一的 provider_id 类属性
        """
        self._providers_by_id = {p.provider_id: p for p in providers}

    def get(self, provider_id: str) -> KnowledgeProvider:
        """根据提供者 ID 获取对应的提供者实例

        Args:
            provider_id: 提供者唯一标识符，如 "api.album"、"faq.default"

        Returns:
            匹配的 KnowledgeProvider 实例

        Raises:
            KeyError: 如果 provider_id 在注册表中不存在
        """
        return self._providers_by_id[provider_id]