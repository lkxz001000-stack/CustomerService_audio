"""
知识提供者具体实现

包含所有具体的知识数据提供者，每个提供者通过不同的方式检索数据：

API 类提供者（实时数据）：
- AlbumAPIProvider: 调用后端 API 获取专辑详细信息
- TrackAPIProvider: 调用后端 API 获取章节/音轨详细信息
- OrderAPIProvider: 调用后端 API 获取用户订单详情（需用户身份认证）
- MembershipAPIProvider: 调用后端 API 获取用户会员状态和权益信息

静态数据提供者：
- FAQProvider: 返回预设的常见问题解答（硬编码数据）
- RAGProvider: 基于向量检索的知识库查询（当前为桩实现，待接入真实 RAG 引擎）
"""

import json
from typing import Any

from audio_cs.domain.state import DialogueState
from audio_cs.knowledge.providers.base import KnowledgeProvider, KnowledgeChunk
from audio_cs.config.settings import settings
from audio_cs.infrastructure import http_client


class AlbumAPIProvider(KnowledgeProvider):
    """专辑信息 API 提供者

    通过调用听书平台后端 API 获取指定专辑的详细信息。
    依赖 state.focused_object.id 作为专辑 ID 发起请求。

    检索结果以 JSON 格式化文本返回，包含专辑标题、作者、简介、章节列表等字段。
    """
    provider_id = 'api.album'

    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        """检索专辑信息

        从对话状态的 focused_object 中提取专辑 ID，
        调用后端 /api/v1/albums/{id} 接口获取数据。

        Args:
            state: 对话状态，从中获取 focused_object.id 作为专辑 ID

        Returns:
            包含专辑 JSON 数据的 KnowledgeChunk；如果无焦点对象则返回提示信息
        """
        album_id = state.focused_object.id if state.focused_object else None
        if not album_id:
            return [KnowledgeChunk(content="未找到专辑信息")]
        data: dict[str, Any] = await self._get_album_by_id(album_id)
        text = json.dumps(data, ensure_ascii=False, indent=2)
        return [KnowledgeChunk(content=f"专辑信息:\n{text}")]

    async def _get_album_by_id(self, album_id: str) -> dict[str, Any]:
        """调用后端专辑详情接口"""
        url = f"{settings.audio_api_base_url}/api/v1/albums/{album_id}"
        response = await http_client.http_client.get(url)
        return response.json().get("data", {})


class TrackAPIProvider(KnowledgeProvider):
    """章节信息 API 提供者

    通过调用听书平台后端 API 获取指定章节/音轨的详细信息。
    依赖 state.focused_object.id 作为章节 ID 发起请求。

    检索结果以 JSON 格式化文本返回，包含章节标题、时长、序号等字段。
    """
    provider_id = 'api.track'

    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        """检索章节信息

        从对话状态的 focused_object 中提取章节 ID，
        调用后端 /api/v1/tracks/{id} 接口获取数据。

        Args:
            state: 对话状态，从中获取 focused_object.id 作为章节 ID

        Returns:
            包含章节 JSON 数据的 KnowledgeChunk；如果无焦点对象则返回提示信息
        """
        track_id = state.focused_object.id if state.focused_object else None
        if not track_id:
            return [KnowledgeChunk(content="未找到章节信息")]
        data: dict[str, Any] = await self._get_track_by_id(track_id)
        text = json.dumps(data, ensure_ascii=False, indent=2)
        return [KnowledgeChunk(content=f"章节信息:\n{text}")]

    async def _get_track_by_id(self, track_id: str) -> dict[str, Any]:
        """调用后端章节详情接口"""
        url = f"{settings.audio_api_base_url}/api/v1/tracks/{track_id}"
        response = await http_client.http_client.get(url)
        return response.json().get("data", {})


class OrderAPIProvider(KnowledgeProvider):
    """订单信息 API 提供者

    通过调用听书平台后端 API 获取指定订单的详细信息。
    需要通过 X-User-Id 请求头传递用户身份以进行权限校验。
    依赖 state.sender_id（用户标识）和 state.focused_object.id（订单 ID）。

    检索结果以 JSON 格式化文本返回，包含订单状态、金额、商品明细等字段。
    """
    provider_id = 'api.order'

    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        """检索订单信息

        从对话状态中提取订单 ID（focused_object）和用户 ID（sender_id），
        以用户身份调用后端 /api/v1/orders/{id} 接口获取订单详情。

        Args:
            state: 对话状态，提供 focused_object.id（订单ID）和 sender_id（用户身份）

        Returns:
            包含订单 JSON 数据的 KnowledgeChunk；如果无焦点对象则返回提示信息
        """
        focused_object = state.focused_object
        if not focused_object:
            return [KnowledgeChunk(content="未找到订单信息")]
        order_id = focused_object.id
        order_data = await self._get_order_by_id(state.sender_id, order_id)
        text = json.dumps(order_data, ensure_ascii=False, indent=2)
        return [KnowledgeChunk(content=f"订单信息:\n{text}")]

    async def _get_order_by_id(self, sender_id: str, order_id: str) -> dict[str, Any]:
        """调用后端订单详情接口，携带 X-User-Id 进行用户身份认证"""
        url = f"{settings.audio_api_base_url}/api/v1/orders/{order_id}"
        headers = {"X-User-Id": sender_id}
        response = await http_client.http_client.get(url, headers=headers)
        return response.json().get("data", {})


class MembershipAPIProvider(KnowledgeProvider):
    """会员信息 API 提供者

    通过调用听书平台后端 /api/v1/me 接口获取当前用户的会员状态和权益信息。
    不需要焦点对象，仅依赖 state.sender_id（用户标识）。

    检索结果以 JSON 格式化文本返回，包含会员等级、到期时间、权益列表等字段。
    """
    provider_id = 'api.membership'

    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        """检索当前用户的会员信息

        以用户身份调用后端 /api/v1/me 接口，获取用户个人资料及会员状态。

        Args:
            state: 对话状态，提供 sender_id 用于用户身份识别

        Returns:
            包含会员信息 JSON 数据的 KnowledgeChunk
        """
        url = f"{settings.audio_api_base_url}/api/v1/me"
        headers = {"X-User-Id": state.sender_id}
        response = await http_client.http_client.get(url, headers=headers)
        data = response.json().get("data", {})
        text = json.dumps(data, ensure_ascii=False, indent=2)
        return [KnowledgeChunk(content=f"会员信息:\n{text}")]


class FAQProvider(KnowledgeProvider):
    """FAQ 常见问题提供者

    返回预设的常见问题解答文本。当前为硬编码数据，
    后续可改造为从数据库或配置文件动态加载 FAQ 内容。

    注意：此处为静态数据，不依赖对话状态中的任何上下文信息。
    所有用户收到相同的 FAQ 内容，LLM 会根据用户具体问题从中筛选相关信息。
    """
    provider_id = 'faq.default'

    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        """返回硬编码的常见问题解答

        当前包含4条常见问题：会员购买、退款流程、播放问题、下载管理。
        这些内容作为背景知识注入 LLM 提示词，由 LLM 从中挑选与当前问题相关的部分。

        Args:
            state: 对话状态（当前未使用，保留以便后续根据用户画像个性化FAQ）

        Returns:
            包含预设 FAQ 文本的 KnowledgeChunk
        """
        return [KnowledgeChunk(content='听书平台常见问题：\n1. 如何购买会员？在APP内选择会员套餐即可购买。\n2. 如何退款？在订单详情页可以申请退款，1-3个工作日内处理。\n3. 播放问题？检查网络连接或清除缓存后重试。\n4. 下载的音频在哪里？在我的下载中可以查看已下载的内容。')]


class RAGProvider(KnowledgeProvider):
    """RAG 知识库检索提供者（桩实现）

    当前为占位实现（桩/Stub），直接返回"未检索到相关信息"。
    后续将接入真实的 RAG（检索增强生成）引擎，从向量知识库中检索相关文档。

    预期的 RAG 流程：
    1. 将用户问题转换为向量（Embedding）
    2. 在向量数据库中检索相似文档
    3. 返回 top-k 相关文档片段作为 Chunk
    """
    provider_id = 'rag.default'

    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        """RAG 检索（当前为桩实现）

        注意：当前未接入真实 RAG 引擎，直接返回占位文本。
        待后续集成向量数据库和 Embedding 模型后实现真正的语义检索。

        Args:
            state: 对话状态（保留参数，供后续真实实现使用）

        Returns:
            包含占位提示的 KnowledgeChunk
        """
        return [KnowledgeChunk(content="未检索到相关信息")]


class AlbumSearchProvider(KnowledgeProvider):
    """专辑搜索/列表 API 提供者。

    支持两种模式：
    1. 搜索模式：按关键词搜索专辑列表（GET /api/v1/albums?keyword=）→ 列表展示
    2. 详情模式：按名称查找专辑详情（GET /api/v1/albums/lookup?name=）→ 含章节信息

    依赖 state.focused_object 区分模式：有 focused_object 走详情查找，无则走搜索。
    """
    provider_id = 'api.album_search'

    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        """检索专辑信息（搜索或按名称查详情）。

        Args:
            state: 对话状态，提供 sender_id、focused_object、pending_turn.user_message.text

        Returns:
            包含搜索/详情 JSON 数据的 KnowledgeChunk
        """
        user_text = state.pending_turn.user_message.text or ""

        # 有焦点对象（用户提到了具体作品名）→ 按名称查详情
        if state.focused_object and state.focused_object.type == "album":
            name = state.focused_object.title or state.focused_object.id
            return await self._lookup_by_name(name)

        # 无焦点对象 → 按关键词搜索列表
        return await self._search_albums(user_text)

    async def _search_albums(self, keyword: str) -> list[KnowledgeChunk]:
        """按关键词搜索专辑列表。"""
        try:
            url = f"{settings.audio_api_base_url}/api/v1/albums"
            params = {"keyword": keyword, "pageSize": 5}
            response = await http_client.http_client.get(url, params=params)
            response.raise_for_status()
            data = response.json().get("data", {})
            text = json.dumps(data, ensure_ascii=False, indent=2)
            return [KnowledgeChunk(content=f"专辑搜索结果:\n{text}")]
        except Exception:
            return [KnowledgeChunk(content="未检索到相关专辑信息")]

    async def _lookup_by_name(self, name: str) -> list[KnowledgeChunk]:
        """按名称查找专辑详情（含章节信息）。"""
        try:
            url = f"{settings.audio_api_base_url}/api/v1/albums/lookup"
            params = {"name": name}
            response = await http_client.http_client.get(url, params=params)
            response.raise_for_status()
            data = response.json().get("data", {})
            text = json.dumps(data, ensure_ascii=False, indent=2)
            return [KnowledgeChunk(content=f"专辑详情:\n{text}")]
        except Exception:
            return [KnowledgeChunk(content=f"未找到「{name}」的详细信息")]
