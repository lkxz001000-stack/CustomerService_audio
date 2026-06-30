"""
依赖注入（DI）装配工厂

本模块是整个客服系统的组装点（Composition Root），负责：
1. 加载流程配置文件（system_flows.yml 和 user_flows.yml）
2. 创建并装配 DialogueEngine 所需的所有依赖组件
3. 将各层组件（规划器、处理轨道、澄清器等）连接成可运行的对话引擎

所有组件的创建和连接集中在此处，上层调用者只需调用 build_dialogue_engine()
即可获得一个完全装配好的 DialogueEngine 实例。
"""

from pathlib import Path

from audio_cs.chitchat.responder import ChitChatResponder
from audio_cs.engine.dialogue_engine import DialogueEngine
from audio_cs.knowledge.responder import KnowledgeResponder
from audio_cs.plan.planner import TurnPlanner
from audio_cs.task.handler import TaskHandler
from audio_cs.knowledge.handler import KnowledgeHandler
from audio_cs.plan.validator import TurnPlanValidator
from audio_cs.chitchat.handler import ChitChatHandler
from audio_cs.task.flow.loader import FlowLoader
from audio_cs.knowledge.intents import KNOWLEDGE_INTENTS
from audio_cs.clarify.responder import ClarifyResponser
from audio_cs.task.command.processor import CommandProcessor
from audio_cs.task.flow.executor import FlowExecutor
from audio_cs.task.action.builder import build_action_runner
from audio_cs.knowledge.providers.registry import KnowledgeProviderRegistry
from audio_cs.knowledge.providers.knowledge import AlbumAPIProvider, TrackAPIProvider, OrderAPIProvider, MembershipAPIProvider, FAQProvider, RAGProvider, AlbumSearchProvider

# 项目根目录（往上两级：audio_cs/engine/builder.py → audio_cs → 项目根）
PROJECT_ROOT_DIR = Path(__file__).resolve().parents[2]
# 流程配置文件目录
FLOW_CONFIG_DIR = PROJECT_ROOT_DIR / "flow_config"
# 流程配置文件列表（系统流程 + 业务流程）
FLOW_CONFIG_FILE = ["system_flows.yml", "user_flows.yml"]


def build_dialogue_engine():
    """
    构建完整装配的 DialogueEngine 实例

    组装过程：
    1. FlowLoader —— 从 YAML 文件加载系统流程和业务流程定义
    2. CommandProcessor —— 解析和分发四种命令（start_flow / resume_flow / cancel_flow / set_slots）
    3. FlowExecutor —— 根据流程定义逐步推进执行
    4. build_action_runner —— 创建动作执行器（调用外部 API）
    5. TaskHandler —— 业务流程轨道处理器，组合 serializer、processor、executor、action_runner
    6. TurnPlanner —— 调用 LLM 进行意图规划和轨道路由分析
    7. TurnPlanValidator —— 校验 LLM 输出的 TurnPlan 合法性
    8. KnowledgeHandler —— 知识查询轨道处理器
       - KnowledgeProviderRegistry：注册所有知识数据源提供者（自动发现机制）
         注册的 Provider：AlbumAPI / TrackAPI / OrderAPI / MembershipAPI / FAQ / RAG
       - KnowledgeResponder：将知识查询结果交给 LLM 生成回复
    9. ChitChatHandler —— 闲聊轨道处理器
    10. ClarifyResponser —— 意图澄清器

    :return: 完全装配好的 DialogueEngine 实例
    """

    # 1. 加载流程配置：从 flow_config/ 目录读取 system_flows.yml 和 user_flows.yml
    #    flow_list 包含两个 YAML 文件中的全部流程（系统流程 + 业务流程）
    flow_list = FlowLoader().load_many_yaml(
        [FLOW_CONFIG_DIR / file for file in FLOW_CONFIG_FILE])

    return DialogueEngine(
        # LLM 规划器：调用大模型进行意图识别和轨道路由
        planner=TurnPlanner(),
        # Task 轨道处理器：执行业务流程
        task_handler=TaskHandler(flow_list=flow_list,
                                 command_processor=CommandProcessor(),
                                 executor=FlowExecutor(),
                                 action_runner=build_action_runner()
                                 ),
        # TurnPlan 校验器：确保 LLM 输出的命令和意图是合法且可执行的
        turn_plan_validator=TurnPlanValidator(),
        # Knowledge 轨道处理器：处理知识查询
        # - KNOWLEDGE_INTENTS：预定义的知识查询意图词汇表（自动发现）
        # - KnowledgeProviderRegistry：注册所有 Provider，运行时按意图匹配对应的数据源
        knowledge_handler=KnowledgeHandler(
            knowledge_intents=KNOWLEDGE_INTENTS,
            knowledge_register=KnowledgeProviderRegistry(providers=[
                AlbumAPIProvider(),       # 专辑信息查询
                TrackAPIProvider(),       # 声音/节目信息查询
                OrderAPIProvider(),       # 订单信息查询
                MembershipAPIProvider(),  # 会员信息查询
                FAQProvider(),            # FAQ 知识库
                RAGProvider(),             # RAG 检索增强生成
                AlbumSearchProvider(),     # 专辑搜索/列表
            ]),
            knowledge_responder=KnowledgeResponder()
        ),
        # ChitChat 轨道处理器：处理闲聊
        chitchat_handler=ChitChatHandler(chitchat_responder=ChitChatResponder()),
        # 意图澄清器：当 LLM 意图不确定或校验失败时介入引导
        clarify_responder=ClarifyResponser()

    )
