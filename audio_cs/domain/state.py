"""
对话状态领域模型层（DialogueState - 聚合根）
============================================

本模块是 DDD 架构中的核心聚合根（Aggregate Root），定义了客服系统
最为重要的领域对象 DialogueState 及其内部实体。

聚合根在 DDD 中的角色：
    DialogueState 是整个对话引擎操作的唯一入口对象。所有对对话状态的
    读取、修改、持久化都必须通过 DialogueState 提供的方法进行，
    外部代码不能直接操作其内部属性（Session、Turn、Context 等）。

领域对象层次结构：
    DialogueState（聚合根）
      ├── sessions: list[Session]       会话列表（一个用户可有多个历史会话）
      │     └── turns: list[Turn]       轮次列表（一个会话可有多个对话轮次）
      │           ├── user_message: UserMessage   用户消息（输入端）
      │           └── bot_messages: list[BotMessage]  机器人回复（输出端）
      ├── active_task: TaskContext      当前正在执行的业务流程
      ├── interrupted_active_tasks: list[TaskContext]  被中断的业务流程栈
      ├── active_system_task: SystemContext   当前正在执行的系统流程
      ├── focused_object: FocusedObject       当前焦点卡片对象
      ├── current_session_id: str             当前活跃会话标识
      └── pending_turn: Turn                  缓冲区中的待提交轮次

持久化策略：
    DialogueState 整体序列化为 JSON blob，通过 repository 层以 UPSERT
    方式存入 MySQL。每次请求开始时从数据库加载，处理完毕后写回。

三个部分：
1. 流程相关：active_task、interrupted_active_tasks、active_system_task
2. 卡片相关：focused_object
3. 会话相关：sessions、current_session_id、pending_turn
"""
import uuid, time
from typing import Any
from dataclasses import dataclass, field
from audio_cs.domain.messages import UserMessage, BotMessage, FocusedObject
from audio_cs.domain.contexts import TaskContext, SystemContext


@dataclass(slots=True)
class Turn:
    """
    对话轮次模型
    -----------
    表示用户与客服机器人之间的一轮完整交互。一轮对话 = 一条用户消息 + N 条机器人回复。

    核心属性:
        turn_id:      轮次唯一标识（UUID），用于追踪和审计
        user_message: 用户输入的消息（可以是文本或卡片点击）
        bot_messages: 机器人的回复消息列表（一条用户消息可能触发多条回复）

    在 DialogueState 中的位置:
        Session.turns 列表中存储历史已提交的轮次。
        当前正在进行的轮次存放在 DialogueState.pending_turn 缓冲区中，
        提交后才会追加到 Session.turns。

    生命周期:
        start_turn() 创建 pending_turn → 引擎处理 → commit_pending_turn() 写入 Session.turns
    """
    turn_id: str  # 对话轮次标识
    user_message: UserMessage
    bot_messages: list[BotMessage]

    def to_dict(self) -> dict[str, Any]:
        """
        将 Turn 序列化为字典，递归序列化内部消息对象。

        返回:
            dict: 包含 turn_id、user_message、bot_messages 的字典
        """
        return {
            "turn_id": self.turn_id,
            "user_message": self.user_message.to_dict(),
            "bot_messages": [bot_message.to_dict() for bot_message in self.bot_messages]
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Turn":
        """
        从字典反序列化为 Turn 实例，递归反序列化内部消息对象。

        参数:
            data: 包含 turn_id、user_message、bot_messages 键的字典

        返回:
            Turn: 新构造的实例
        """
        return cls(
            turn_id=data['turn_id'],
            user_message=UserMessage.from_dict(data['user_message']),
            bot_messages=[BotMessage.from_dict(bot_message_dict) for bot_message_dict in data.get('bot_messages', [])]
        )


@dataclass(slots=True)
class Session:
    """
    会话模型
    -------
    代表用户与客服系统之间的一次连接周期。一次"开启客服窗口"到"关闭/超时"
    的过程为一个 Session。

    核心属性:
        session_id:       会话唯一标识（UUID）
        started_at:       会话开始时间戳（time.time()）
        last_activity_at: 最后一次活跃时间戳（每次收到消息时更新）
        closed_at:        会话关闭时间戳（None 表示仍活跃，有值表示已关闭）
        turns:            该会话内的所有对话轮次列表

    会话生命周期:
        1. 创建：start_session() 创建新 Session，记录 started_at 和 last_activity_at
        2. 活跃：每收到一条用户消息，更新 last_activity_at
        3. 超时关闭：距上次活跃超过 60 分钟，自动关闭旧会话并创建新会话
        4. 显式关闭：close_session() 记录 closed_at，清空 current_session_id

    超时判定规则:
        closed_at 有值 → 会话已关闭（不可再用）
        closed_at 为 None → 会话仍活跃，可以继续使用
    """
    session_id: str  # 会话标识
    started_at: float  # session开启时间
    last_activity_at: float  # session最后一次激活时间（超时判定）
    closed_at: float | None = None  # session关闭时间（None=活跃中，有值=已关闭）
    turns: list[Turn] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """
        将 Session 序列化为字典。

        返回:
            dict: 包含 session_id、started_at、last_activity_at、closed_at、turns 的字典
        """
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "last_activity_at": self.last_activity_at,
            "closed_at": self.last_activity_at,
            "turns": [turn.to_dict() for turn in self.turns]
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        """
        从字典反序列化为 Session 实例。

        参数:
            data: 包含 session_id、started_at、last_activity_at、closed_at、turns 键的字典

        返回:
            Session: 新构造的实例
        """
        return cls(
            session_id=data['session_id'],
            started_at=data['started_at'],
            last_activity_at=data['last_activity_at'],
            closed_at=data['closed_at'],
            turns=[Turn.from_dict(turn_dict) for turn_dict in data.get('turns', [])]
        )


@dataclass(slots=True)
class DialogueState:
    """
    对话聚合根（Aggregate Root）
    ============================
    这是整个客服引擎中最核心的领域对象，代表一个用户完整的对话状态。
    引擎在处理任何请求时，都是围绕这一个对象进行读取和修改。

    设计原则:
        1. 聚合根是外部访问内部实体的唯一入口，所有状态变更都必须通过
           DialogueState 的方法进行，外部代码不得直接操作内部属性。
        2. 每个用户有且仅有一份 DialogueState，以 sender_id 作为唯一标识。
        3. DialogueState 支持完整序列化/反序列化（to_dict / from_dict），
           配合 repository 层以 JSON blob 形式持久化到 MySQL。

    三大状态域:

        【流程状态域】-- 管理业务/系统流程的执行与中断恢复
            active_task:              当前正在运行的业务流程上下文
            interrupted_active_tasks: 被中断的业务流程栈（后进先出）
            active_system_task:       当前正在执行的系统流程上下文

            流程中断与恢复机制（类似 CPU 中断栈）：
                - 当用户在执行流程 A 时触发了流程 B，系统将流程 A 压入
                  interrupted_active_tasks 栈，激活流程 B。
                - 流程 B 执行完毕后，系统从栈中恢复流程 A 继续执行。
                - 栈中可能有多层中断（A→B→C→B→A 逐层恢复）。

        【卡片状态域】-- 追踪用户当前关注的可视化对象
            focused_object: 用户在界面上点击或关注的卡片对象。
                           用于智能客服理解用户当前意图的上下文。

        【会话状态域】-- 管理对话会话的创建/关闭/超时/轮次
            sessions:            该用户的所有历史会话列表（每个会话独立）
            current_session_id:  当前活跃会话的标识
            pending_turn:        当前正在处理、尚未提交到会话的轮次缓冲区

            pending_turn 缓冲区模式:
                引擎在处理用户消息时，先将 Turn 放入 pending_turn，
                在引擎内部逐步填充 bot_messages。所有轨道（Task / Knowledge /
                ChitChat）处理完毕后，调用 commit_pending_turn() 将完整轮次
                追加到 sessions 中。如果处理过程中出错，pending_turn 被丢弃，
                不会污染已持久化的会话数据。

    生命周期（单次请求）:
        1. 从 MySQL 加载当前用户的 DialogueState（或新建）
        2. start_turn() 在 pending_turn 缓冲区创建新轮次
        3. 引擎路由到 Task / Knowledge / ChitChat 轨道处理
        4. 各轨道向 pending_turn.bot_messages 追加回复
        5. commit_pending_turn() 将轮次提交到 current_session().turns
        6. 调用 to_dict() 序列化，通过 repository 写回 MySQL
    """

    # ==========================流程相关字段==========================
    # 当前正在运行的业务流程上下文（用户正在做的业务，如"退款申请"）
    # active_task 和 active_system_task 优先取系统流程（参见 current_activating_task）
    # ==========================卡片相关字段==========================
    # 用户当前关注的焦点卡片对象（从界面点击传入）
    # ==========================会话相关字段==========================
    # sessions: 所有历史会话列表；current_session_id: 当前活跃会话；pending_turn: 缓冲区中的轮次

    sender_id: str  # 用户ID（聚合根的唯一标识，每个用户一份 DialogueState）
    active_task: TaskContext | None = None  # 当前正在运行的业务流程
    interrupted_active_tasks: list[TaskContext] = field(default_factory=list)  # 当前已经中断的业务流程（栈结构）
    active_system_task: SystemContext | None = None  # 当前正在执行的系统流程
    focused_object: FocusedObject | None = None  # 卡片对象（用户点击的界面卡片上下文）
    sessions: list[Session] = field(default_factory=list)
    current_session_id: str | None = None
    pending_turn: Turn | None = None  # 缓冲区中的待提交轮次（处理完成后才写入 sessions）

    def to_dict(self) -> dict:
        """
        将整个 DialogueState 聚合根序列化为字典。
        递归序列化所有内部实体：Session、Turn、UserMessage、BotMessage、
        TaskContext、SystemContext、FocusedObject。

        返回:
            dict: 完整的对话状态字典，可直接 JSON 序列化后存入数据库
        """
        return {
            "sender_id": self.sender_id,
            "active_task": self.active_task.to_dict() if self.active_task is not None else None,
            "interrupted_active_tasks": [interrupted_task.to_dict() for interrupted_task in
                                         self.interrupted_active_tasks],
            "active_system_task": self.active_system_task.to_dict() if self.active_system_task is not None else None,
            "focused_object": self.focused_object.to_dict() if self.focused_object is not None else None,
            "sessions": [session.to_dict() for session in
                         self.sessions],
            "current_session_id": self.current_session_id,
            "pending_turn": self.pending_turn.to_dict() if self.pending_turn is not None else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DialogueState":
        """
        从字典反序列化为完整的 DialogueState 聚合根。
        递归反序列化所有内部实体。字段为 None 时使用默认值。

        参数:
            data: 从数据库 JSON blob 反序列化而来的字典

        返回:
            DialogueState: 完整重建的对话状态对象

        注意:
            active_task 恢复时需要根据 flow_id 路由到正确的 SystemContext 子类。
            这是在 SystemContext.from_dict() 内部通过 SYSTEM_CONTEXT_TO_CLASS
            注册表实现的工厂模式反序列化。
        """
        return cls(
            sender_id=data['sender_id'],
            active_task=TaskContext.from_dict(data['active_task']) if data.get('active_task') else None,
            interrupted_active_tasks=[TaskContext.from_dict(interrupted_tasks_dict) for interrupted_tasks_dict in
                                      data['interrupted_active_tasks']] if data.get('interrupted_active_tasks') else [],
            active_system_task=SystemContext.from_dict(data['active_system_task']) if data.get(
                'active_system_task') else None,
            focused_object=FocusedObject.from_dict(data['focused_object']) if data.get('focused_object') else None,

            sessions=[Session.from_dict(session_dict) for session_dict in
                      data['sessions']] if data.get('sessions') else [],

            current_session_id=data.get('current_session_id'),
            pending_turn=Turn.from_dict(data['pending_turn']) if data.get('pending_turn') else None
        )

    # ==========================流程相关==========================

    def start_active_system_task(self, system_context: SystemContext) -> None:
        """
        开启并激活系统流程（如 started、interrupted、resumed 等）。

        参数:
            system_context: 要激活的系统流程上下文对象（SystemContext 及其子类）

        用途:
            当引擎需要执行系统级操作时调用，例如：
            - 开启业务流程时触发 started 系统流程（欢迎开场白）
            - 中断旧流程时触发 interrupted 系统流程（中断提示语）
            - 恢复流程时触发 resumed 系统流程（恢复提醒语）
        """
        self.active_system_task = system_context

    def end_activating_system_task(self):
        """
        结束当前正在激活的系统流程，将 active_system_task 置为 None。

        调用时机:
            系统流程执行完毕后调用，让控制权交还给业务流程或等待下一次用户输入。
        """
        self.active_system_task = None

    def start_active_business_task(self, task_context: TaskContext) -> None:
        """
        开启并激活业务流程（如订单查询、退款申请、工单提交等）。

        参数:
            task_context: 要激活的业务流程上下文对象（包含 flow_id、step_id、slots）
        """
        self.active_task = task_context

    def end_activating_business_task(self) -> None:
        """
        结束当前正在激活的业务流程，将 active_task 置为 None。

        调用时机:
            业务流程所有步骤执行完毕时调用。
        """
        self.active_task = None

    def end_activating_task(self):
        """
        结束所有正在运行的流程（同时清空业务流程和系统流程）。

        调用时机:
            用户主动取消或以其他方式终止所有流程时调用。
        """
        self.active_task = None
        self.active_system_task = None

    def interrupted_activating_task(self):
        """
        中断当前正在运行的业务流程。

        中断栈机制:
            【步骤1】将当前正在运行的业务流程压入 interrupted_active_tasks 栈中保存
            【步骤2】清空 active_task，腾出位置准备接收新的业务流程

        典型场景:
            用户在执行"订单查询"流程时，突然说"我要申请退款"。
            → 系统将"订单查询"的 TaskContext 压入栈
            → 清空 active_task
            → 创建新的"退款申请" TaskContext 并激活
            → 触发 InterruptedSystemContext 生成中断开场白
        """
        # 1. 将正在运行的业务流程存储到栈中（类似 CPU 中断时保存现场）
        self.interrupted_active_tasks.append(self.active_task)
        # 2. 清空当前正在运行的业务流程，准备接收新的业务流程
        self.active_task = None

    def resumed_interrupted_business_task(self, flow_id: str | None = None) -> bool:
        """
        恢复之前中断的业务流程（从中断栈中弹出）。

        参数:
            flow_id: 指定要恢复的流程 ID。
                     None 时默认恢复栈顶（最近中断的）流程。
                     有值时遍历栈查找匹配的流程 ID 并恢复。

        返回:
            bool: True 表示成功恢复了一个流程；False 表示栈为空或未找到匹配的流程。

        恢复逻辑:
            1. 先检查栈是否为空，为空则无法恢复，返回 False
            2. 如果 flow_id 为 None（默认模式）：
               - 从栈顶弹出最近中断的流程，恢复为 active_task，返回 True
            3. 如果 flow_id 有值（指定模式）：
               - 遍历栈查找匹配的流程 ID
               - 找到后将匹配的流程恢复为 active_task，从栈中删除该元素，返回 True
               - 未找到匹配项则返回 False

        典型场景:
            - 用户先执行"订单查询"中途转向"退款申请"
            - "退款申请"完成后，引擎调用 resumed_interrupted_business_task() 恢复"订单查询"
            - 生成 ResumedSystemContext 触发恢复提醒语
        """

        # 1. 检验栈中是否有元素（栈为空则无流程可恢复）
        if not self.interrupted_active_tasks:
            return False

        # 2. 未指定流程 ID：默认恢复栈顶（最近中断的流程，LIFO）
        if flow_id is None:
            interrupted_active_task = self.interrupted_active_tasks.pop()  # 栈顶弹出
            self.active_task = interrupted_active_task  # 恢复为当前活跃流程
            return True

        # 3. 指定了流程 ID：遍历栈查找匹配的流程（O(n) 扫描，支持恢复非栈顶流程）
        for i, interrupted_task in enumerate(self.interrupted_active_tasks):
            if interrupted_task.flow_id == flow_id:
                self.active_task = interrupted_task  # 恢复目标流程
                del self.interrupted_active_tasks[i]  # 从栈中移除（不是 pop，因为可能不在栈顶）
                return True
        return False  # 未找到匹配的流程 ID

    def current_activating_task(self):
        """
        获取当前正在运行的流程（按优先级返回）。

        优先级规则:
            系统流程 > 业务流程

        返回:
            TaskContext | SystemContext | None:
                - 有 active_system_task 时，优先返回系统流程
                - 没有系统流程但有 active_task 时，返回业务流程
                - 两者都为空时返回 None

        设计意图:
            系统流程（如 started、interrupted）是临时性的、优先级更高的操作，
            它们执行期间应该"遮蔽"正在运行的业务流程。
            系统流程结束后 end_activating_system_task() 将 active_system_task 置 None，
            current_activating_task() 就会自动回退到返回 active_task。
        """

        return self.active_system_task or self.active_task

    # ==========================槽位相关==========================

    def set_slots(self, slots: dict[str, Any]):
        """
        设置当前活跃业务流程的槽位值（合并更新）。

        参数:
            slots: 键值对字典，将被合并到 active_task.slots 中

        注意:
            如果没有活跃的 active_task，此操作为空操作（不会报错）。
            使用 dict.update() 语义，同名键会覆盖旧值。

        槽位在业务流程中的作用:
            槽位（slots）是业务流程在执行过程中收集的用户输入参数。
            例如"退款申请"流程的 slots 可能包含：
            {"order_number": "12345", "reason": "质量问题", "amount": "99.00"}
            set_slots 由 CommandProcessor 在流程执行过程中调用。
        """

        if self.active_task is not None:
            self.active_task.slots.update(slots)  # 合并更新，同名键覆盖

    def remove_slot(self, slot_name: str) -> Any:
        """
        从当前业务流程的槽位中移除指定槽位，并返回其值。

        参数:
            slot_name: 要移除的槽位名称（如 "order_number"）

        返回:
            Any: 被移除槽位的值。若 active_task 为 None 则抛出 AttributeError。

        用途:
            流程取消或步骤回退时，需要从 slots 中清理已收集但不再需要的数据。
        """
        return self.active_task.slots.pop(slot_name)

    # ==========================卡片相关==========================

    def set_focused_object(self, focused_object: FocusedObject):
        """
        设置当前会话的焦点卡片对象。

        参数:
            focused_object: 用户点击的卡片对象（订单/专辑/曲目等）

        用途:
            当用户在界面上点击某个卡片时，前端将卡片信息传回，
            引擎通过此方法将卡片上下文保存在 DialogueState 中，
            后续流程可以根据 focused_object 推断用户意图。
        """
        self.focused_object = focused_object

    # ==========================session(会话)相关==========================

    def current_session(self) -> Session | None:
        """
        获取当前活跃的 Session 对象。

        返回:
            Session | None: 当前会话对象。如果 current_session_id 无效或为 None，
                            返回 None。

        查找逻辑:
            遍历 sessions 列表，匹配 session_id == current_session_id 的记录。
            这是一个 O(n) 的线性查找，在正常使用场景下 sessions 列表很短。
        """

        for session in self.sessions:
            if session.session_id == self.current_session_id:
                return session
        return None  # 未找到匹配的会话（可能尚未创建或被关闭）

    def start_session(self):
        """
        创建并启动一个新的 Session。

        【会话创建流程】:
            1. 生成当前时间戳 now
            2. 创建 Session 对象：
               - session_id: 使用 uuid.uuid4() 生成唯一标识
               - started_at: 当前时间戳
               - last_activity_at: 初始值与 started_at 相同
            3. 将新 Session 的 session_id 设置为 current_session_id
            4. 将 Session 对象追加到 sessions 列表中

        调用时机:
            - 用户首次发起对话（sessions 为空）
            - 旧会话超时后需要创建新会话（先 close_session，再 start_session）
        """

        now = time.time()
        # 1. 创建session对象（记录创建时间和最后活跃时间）
        session = Session(session_id=str(uuid.uuid4()), started_at=now, last_activity_at=now)

        # 2. 更新当前的session_id（指向新创建的会话）
        self.current_session_id = session.session_id

        # 3. 将session对象存储到sessions列表中（保留历史会话记录）
        self.sessions.append(session)

    def close_session(self):
        """
        关闭当前活跃的 Session。

        【关闭流程】:
            1. 找到当前活跃的会话（通过 current_session()）
            2. 将会话的 closed_at 设置为当前时间戳（标记会话结束时间）
            3. 将 current_session_id 置为 None（表示无活跃会话）
            4. 会话保留在 sessions 列表中（不删除，用于历史查询）

        注意:
            关闭后 Session 仍在 sessions 列表中，只是 closed_at 有值。
            sessions 列表保存了用户的历史会话，可用于回溯对话记录。
        """

        if self.current_session() is not None:
            # 1. 修改session的关闭时间（标记会话生命周期结束）
            self.current_session().closed_at = time.time()
            # 2. 清空当前session id（表示无活跃会话）
            self.current_session_id = None
            # 3. 不从sessions中移除（保留历史会话用于审计和查询）

    def reset_running_state_for_new_session(self):
        """
        重置运行状态，为新会话做准备（会话超时时调用）。

        【重置内容】:
            1. 流程相关：清空 active_task、interrupted_active_tasks、active_system_task
               → 旧会话中的流程全部终结，新会话从零开始
            2. 卡片相关：清空 focused_object
               → 清除旧会话中的卡片上下文
            3. 缓冲区相关：清空 pending_turn
               → 丢弃旧会话未提交的轮次，防止脏数据污染新会话

        调用时机:
            DialogueEngine 在处理请求前检测会话是否超时（60分钟）。
            如果超时，依次调用：
            close_session() → reset_running_state_for_new_session() → start_session()
            以完成会话的完整切换。
        """

        # 1.清空任务相关的（流程状态全部重置）
        self.active_task = None
        self.interrupted_active_tasks = list()  # 新建空列表，不使用 list.clear() 来触发 GC
        self.active_system_task = None

        # 2.清空卡片（旧会话的焦点上下文不再有意义）
        self.focused_object = None

        # 3.清空缓冲区（丢弃上一个会话未提交的轮次数据）
        self.pending_turn = None

    # ==========================Turn(轮次)相关==========================

    def start_turn(self, user_message: UserMessage):
        """
        开始一个新的对话轮次（存储在 pending_turn 缓冲区中）。

        参数:
            user_message: 用户发送的消息对象

        【缓冲区模式详解】:
            轮次不会直接写入 sessions.turns，而是先放入 pending_turn 缓冲区。
            这样做的原因是：
            1. 引擎处理过程中可能需要多次追加 bot_messages（多个轨道分别产出回复）
            2. 如果处理过程中出现异常，pending_turn 被丢弃，不会污染已持久化的会话数据
            3. 只有所有处理步骤都成功完成后，才调用 commit_pending_turn() 提交

        【创建流程】:
            1. 检查当前是否有活跃会话（无活跃会话时不做任何操作）
            2. 创建 Turn 对象：turn_id 用 uuid 生成，bot_messages 初始为空列表
            3. 将 Turn 放入 pending_turn 缓冲区
        """

        if self.current_session() is not None:
            # 创建轮次对象：turn_id 用 UUID 保证唯一性，bot_messages 初始为空
            turn = Turn(turn_id=str(uuid.uuid4()), user_message=user_message, bot_messages=[])
            self.pending_turn = turn  # 放入缓冲区，等待后续处理填充 bot_messages

    def commit_pending_turn(self):
        """
        提交缓冲区中的轮次到当前会话的对话历史中。

        【提交流程】:
            1. 将 pending_turn 追加到当前会话的 turns 列表末尾
            2. 将 pending_turn 置为 None（清空缓冲区，防止重复提交）

        调用时机:
            引擎的所有处理轨道（Task / Knowledge / ChitChat）都完成后调用。
            此时 pending_turn.bot_messages 已经被各轨道填充完整。

        设计保障:
            提交后 pending_turn 为 None，后续的意外重复调用不会导致重复提交。
            如果 pending_turn 为 None，current_session().turns.append(None)
            会引发 AttributeError，需要调用方确保在 start_turn 之后调用。
        """
        self.current_session().turns.append(self.pending_turn)  # 将完整轮次写入会话历史
        self.pending_turn = None  # 清空缓冲区，防止重复提交
