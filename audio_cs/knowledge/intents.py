"""
知识意图注册表

定义客服系统中所有可识别的知识查询意图。当 LLM 判断用户输入属于"知识查询"轨道时，
会输出一个或多个意图 ID，系统根据这些 ID 查找对应的数据提供者来检索信息。

每个 KnowledgeIntent 包含：
- id: 意图唯一标识，与 LLM 提示词中定义的意图名称一致
- description: 中文描述，说明该意图对应的用户意图
- provider_ids: 为该意图提供数据的提供者 ID 列表（可对应多个提供者）
- requires_object: 该意图是否需要用户提供一个"焦点对象"（如专辑、订单等）

设计原则：意图与数据提供者解耦 —— 一个意图可以组合多个数据源（API+FAQ+RAG），
方便后续灵活调整数据检索策略而不影响 LLM 的意图识别逻辑。
"""

from dataclasses import dataclass, field


@dataclass
class KnowledgeIntent:
    """知识意图数据类

    描述一个知识查询意图的元数据配置，用于连接 LLM 意图识别和实际数据检索。

    Attributes:
        id: 意图唯一标识符（字符串），如 "album_info"、"order_info"
        description: 意图的中文描述，说明用户想了解什么
        provider_ids: 关联的数据提供者 ID 列表，一个意图可依赖多个数据源
        requires_object: 该意图是否依赖用户指定一个焦点对象（如 "album"、"order"），
                        为 None 表示不需要焦点对象
    """
    id: str
    description: str
    provider_ids: list[str] = field(default_factory=list)
    requires_object: str | None = None


# 知识意图注册表：将所有可识别的知识查询意图集中管理
KNOWLEDGE_INTENTS: dict[str, KnowledgeIntent] = {
    # 专辑信息咨询：用户想了解某张有声书/广播剧/播客专辑的详细信息
    # 数据来源：api.album（调用后端专辑API获取数据）
    "album_info": KnowledgeIntent(
        id="album_info", description="有声书/广播剧/播客等专辑信息咨询",
        provider_ids=["api.album"], requires_object="album",
    ),
    # 章节详情咨询：用户想了解某个章节/音轨的详细信息
    # 数据来源：api.track（调用后端章节API获取数据）
    "track_info": KnowledgeIntent(
        id="track_info", description="章节详情咨询",
        provider_ids=["api.track"], requires_object="track",
    ),
    # 订单信息咨询：用户想查看某个订单的详细信息（状态、金额、商品等）
    # 数据来源：api.order（调用后端订单API获取数据，需携带用户身份）
    "order_info": KnowledgeIntent(
        id="order_info", description="订单信息咨询",
        provider_ids=["api.order"], requires_object="order",
    ),
    # 会员权益咨询：用户想了解会员权益、套餐内容等
    # 数据来源：api.membership（获取用户会员状态）+ faq.default（常见会员问题）
    "membership_info": KnowledgeIntent(
        id="membership_info", description="会员权益咨询",
        provider_ids=["api.membership", "faq.default"],
    ),
    # 退款政策咨询：用户想了解退款条件、流程、时效等
    # 数据来源：faq.default（常见退款问题）+ rag.default（知识库检索补充）
    "refund_policy": KnowledgeIntent(
        id="refund_policy", description="退款政策咨询",
        provider_ids=["faq.default", "rag.default"],
    ),
    # 播放功能帮助：用户遇到播放问题，需要操作指导
    # 数据来源：faq.default（常见播放问题）+ rag.default（知识库检索补充）
    "playback_help": KnowledgeIntent(
        id="playback_help", description="播放功能使用帮助",
        provider_ids=["faq.default", "rag.default"],
    ),
    # 平台规则咨询：用户想了解平台的使用规则、内容审核标准等
    # 数据来源：rag.default（通过RAG从知识库中检索相关规则文档）
    "platform_rule": KnowledgeIntent(
        id="platform_rule", description="平台规则咨询",
        provider_ids=["rag.default"],
    ),
    # 通用听书信息咨询：兜底意图，涵盖未被其他意图匹配的听书相关问题
    # 数据来源：faq.default（常见问题）+ rag.default（知识库检索）
    "general_audio_info": KnowledgeIntent(
        id="general_audio_info", description="听书平台通用信息咨询",
        provider_ids=["faq.default", "rag.default"],
    ),
    # 专辑搜索/浏览：用户按关键词、分类、评分等条件搜索有声书、广播剧、课程、播客
    # 数据来源：api.album_search（调用后端专辑搜索API）
    "album_search": KnowledgeIntent(
        id="album_search", description="按关键词、分类、评分等条件搜索/浏览有声书、广播剧、知识课程、播客等专辑列表",
        provider_ids=["api.album_search"],
    ),
    # 按名称查专辑详情：用户提到某部具体作品名称，查询其章节数、主播、时长等详情
    # 数据来源：api.album_search（从用户文本中提取作品名进行查找）
    "album_content_detail": KnowledgeIntent(
        id="album_content_detail", description="按专辑名称查询某部作品的详细信息（总章节数、已更新章节、主播、时长等）",
        provider_ids=["api.album_search"],
    ),
}
