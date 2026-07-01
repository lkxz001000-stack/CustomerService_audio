"""
黄金测试用例定义 —— 200 条标注期望轨道、意图、槽位的测试用例。

用例分类（7 类）：
  routing          40 条 — 轨道选择准确率
  slot_filling     40 条 — 槽位提取 F1
  knowledge        40 条 — 知识意图识别
  flow_completion  20 条 — 完整多轮业务流程
  anti_interference 20 条 — 防历史干扰
  edge_case        20 条 — 边界情况
  clarify          20 条 — 澄清触发
"""

from dataclasses import dataclass


@dataclass
class GoldenTurn:
    """单轮标注"""
    user_input: str
    user_id: int = 1
    expected_track: str = ""               # "task" | "knowledge" | "chitchat" | "clarify"
    expected_intent: str | None = None     # Knowledge 轨道时才填充
    expected_slots: dict | None = None     # Task 轨道时，期望提取的槽位
    expected_flow: str | None = None       # Task 轨道时，期望的流程名


@dataclass
class GoldenTestCase:
    """一个测试用例（可包含多轮对话）"""
    id: str
    category: str
    description: str
    turns: list[GoldenTurn]


# ============================================================
# 1. routing — 轨道准确率（40 条）
# ============================================================
ROUTING_CASES = [
    # ---- 会员咨询 → knowledge ----
    GoldenTestCase("r001", "routing", "会员权益查询",
        [GoldenTurn("我的会员有什么权益？", expected_track="knowledge", expected_intent="membership_info")]),
    GoldenTestCase("r002", "routing", "会员到期时间",
        [GoldenTurn("会员什么时候到期？", expected_track="knowledge", expected_intent="membership_info")]),
    GoldenTestCase("r003", "routing", "会员等级查询",
        [GoldenTurn("我现在是什么会员等级？", expected_track="knowledge", expected_intent="membership_info")]),
    GoldenTestCase("r004", "routing", "升级会员",
        [GoldenTurn("怎么升级成高级会员？", expected_track="knowledge", expected_intent="membership_info")]),
    GoldenTestCase("r005", "routing", "会员价格",
        [GoldenTurn("会员多少钱一个月？", expected_track="knowledge", expected_intent="membership_info")]),
    GoldenTestCase("r006", "routing", "会员对比",
        [GoldenTurn("普通会员和高级会员有什么区别？", expected_track="knowledge", expected_intent="membership_info")]),

    # ---- 平台规则 → knowledge ----
    GoldenTestCase("r007", "routing", "退款政策",
        [GoldenTurn("退款有什么规则？", expected_track="knowledge", expected_intent="platform_rule")]),
    GoldenTestCase("r008", "routing", "使用帮助",
        [GoldenTurn("怎么使用这个APP？", expected_track="knowledge", expected_intent="platform_rule")]),
    GoldenTestCase("r009", "routing", "下载功能",
        [GoldenTurn("可以离线下载吗？", expected_track="knowledge", expected_intent="platform_rule")]),
    GoldenTestCase("r010", "routing", "多设备登录",
        [GoldenTurn("一个账号可以在几个设备上登录？", expected_track="knowledge", expected_intent="platform_rule")]),

    # ---- 专辑/作品信息 → knowledge ----
    GoldenTestCase("r011", "routing", "专辑信息查询",
        [GoldenTurn("《三体》这本书怎么样？", expected_track="knowledge", expected_intent="album_info")]),
    GoldenTestCase("r012", "routing", "作者查询",
        [GoldenTurn("这本书的作者是谁？", expected_track="knowledge", expected_intent="album_info")]),
    GoldenTestCase("r013", "routing", "更新时间",
        [GoldenTurn("《斗罗大陆》什么时候更新？", expected_track="knowledge", expected_intent="album_info")]),

    # ---- 订单查询 → task ----
    GoldenTestCase("r014", "routing", "查订单",
        [GoldenTurn("帮我查一下订单ORD000000000004", expected_track="task", expected_flow="order_query",
                    expected_slots={"order_number": "ORD000000000004"})]),
    GoldenTestCase("r015", "routing", "订单状态",
        [GoldenTurn("我的订单到哪了？", expected_track="task", expected_flow="order_query")]),
    GoldenTestCase("r016", "routing", "最近订单",
        [GoldenTurn("我最近买了什么？", expected_track="task", expected_flow="order_query")]),
    GoldenTestCase("r017", "routing", "订单详情",
        [GoldenTurn("查一下我最新订单的详情", expected_track="task", expected_flow="order_query")]),

    # ---- 播放记录 → task ----
    GoldenTestCase("r018", "routing", "播放进度",
        [GoldenTurn("我昨天听到哪里了？", expected_track="task", expected_flow="playback_query")]),
    GoldenTestCase("r019", "routing", "最近播放",
        [GoldenTurn("我最近听了什么？", expected_track="task", expected_flow="playback_query")]),
    GoldenTestCase("r020", "routing", "指定书进度",
        [GoldenTurn("《头牌过气后》听到第几章了？", expected_track="task", expected_flow="playback_query",
                    expected_slots={"album_title": "头牌过气后"})]),

    # ---- 退款 → task ----
    GoldenTestCase("r021", "routing", "申请退款",
        [GoldenTurn("我要退款", expected_track="task", expected_flow="refund_apply")]),
    GoldenTestCase("r022", "routing", "退款原因",
        [GoldenTurn("买的书不喜欢怎么退？", expected_track="task", expected_flow="refund_apply")]),

    # ---- 工单 → task ----
    GoldenTestCase("r023", "routing", "提交工单",
        [GoldenTurn("反馈一个问题", expected_track="task", expected_flow="ticket_submit")]),
    GoldenTestCase("r024", "routing", "投诉建议",
        [GoldenTurn("我要投诉", expected_track="task", expected_flow="ticket_submit")]),

    # ---- 闲聊 → chitchat ----
    GoldenTestCase("r025", "routing", "问候",
        [GoldenTurn("你好", expected_track="chitchat")]),
    GoldenTestCase("r026", "routing", "感谢",
        [GoldenTurn("谢谢你的帮助", expected_track="chitchat")]),
    GoldenTestCase("r027", "routing", "自我介绍",
        [GoldenTurn("你是谁？", expected_track="chitchat")]),
    GoldenTestCase("r028", "routing", "能力询问",
        [GoldenTurn("你能做什么？", expected_track="chitchat")]),
    GoldenTestCase("r029", "routing", "再见",
        [GoldenTurn("拜拜", expected_track="chitchat")]),
    GoldenTestCase("r030", "routing", "闲聊天气",
        [GoldenTurn("今天天气真好", expected_track="chitchat")]),
    GoldenTestCase("r031", "routing", "笑话",
        [GoldenTurn("讲个笑话", expected_track="chitchat")]),

    # ---- 模糊意图 → clarify ----
    GoldenTestCase("r032", "routing", "单字输入",
        [GoldenTurn("嗯", expected_track="clarify")]),
    GoldenTestCase("r033", "routing", "模糊指代",
        [GoldenTurn("那个呢？", expected_track="clarify")]),
    GoldenTestCase("r034", "routing", "纯数字",
        [GoldenTurn("1234", expected_track="clarify")]),
    GoldenTestCase("r035", "routing", "无意义输入",
        [GoldenTurn("asdfgh", expected_track="clarify")]),

    # ---- 带语气的知识查询 → knowledge ----
    GoldenTestCase("r036", "routing", "想知道会员信息",
        [GoldenTurn("我想知道我的会员还有多久到期", expected_track="knowledge", expected_intent="membership_info")]),
    GoldenTestCase("r037", "routing", "了解一下权益",
        [GoldenTurn("了解一下会员有哪些权益", expected_track="knowledge", expected_intent="membership_info")]),
    GoldenTestCase("r038", "routing", "帮我查会员",
        [GoldenTurn("帮我查一下我的会员信息", expected_track="knowledge", expected_intent="membership_info")]),
    GoldenTestCase("r039", "routing", "会员相关问题",
        [GoldenTurn("会员可以听所有书吗？", expected_track="knowledge", expected_intent="membership_info")]),
    GoldenTestCase("r040", "routing", "咨询会员",
        [GoldenTurn("咨询一下会员服务", expected_track="knowledge", expected_intent="membership_info")]),
]

# ============================================================
# 2. slot_filling — 槽位提取 F1（40 条）
# ============================================================
SLOT_FILLING_CASES = [
    # ---- 订单号提取 ----
    GoldenTestCase("s001", "slot_filling", "标准订单号",
        [GoldenTurn("查订单ORD000000000004", expected_track="task", expected_flow="order_query",
                    expected_slots={"order_number": "ORD000000000004"})]),
    GoldenTestCase("s002", "slot_filling", "订单号带空格",
        [GoldenTurn("帮我查一下 ORD000000000008 这个订单", expected_track="task", expected_flow="order_query",
                    expected_slots={"order_number": "ORD000000000008"})]),
    GoldenTestCase("s003", "slot_filling", "订单号中文",
        [GoldenTurn("查订单号ORD000000000012", expected_track="task", expected_flow="order_query",
                    expected_slots={"order_number": "ORD000000000012"})]),
    GoldenTestCase("s004", "slot_filling", "仅订单号",
        [GoldenTurn("ORD000000000016", expected_track="task", expected_flow="order_query",
                    expected_slots={"order_number": "ORD000000000016"})]),
    GoldenTestCase("s005", "slot_filling", "引号括起订单号",
        [GoldenTurn("帮我查\"ORD000000000020\"", expected_track="task", expected_flow="order_query",
                    expected_slots={"order_number": "ORD000000000020"})]),

    # ---- 书名提取 ----
    GoldenTestCase("s006", "slot_filling", "书名号括起",
        [GoldenTurn("《斗罗大陆》听到哪里了？", expected_track="task", expected_flow="playback_query",
                    expected_slots={"album_title": "斗罗大陆"})]),
    GoldenTestCase("s007", "slot_filling", "引号括起书名",
        [GoldenTurn("\"三体\"的播放进度", expected_track="task", expected_flow="playback_query",
                    expected_slots={"album_title": "三体"})]),
    GoldenTestCase("s008", "slot_filling", "书名带数字",
        [GoldenTurn("米小圈上学记11听到哪里了？", expected_track="task", expected_flow="playback_query",
                    expected_slots={"album_title": "米小圈上学记11"})]),
    GoldenTestCase("s009", "slot_filling", "续集书名",
        [GoldenTurn("《头牌过气后第二季》更新了吗？", expected_track="task", expected_flow="playback_query",
                    expected_slots={"album_title": "头牌过气后第二季"})]),
    GoldenTestCase("s010", "slot_filling", "口语化书名",
        [GoldenTurn("那个剑来的听书进度", expected_track="task", expected_flow="playback_query",
                    expected_slots={"album_title": "剑来"})]),
    GoldenTestCase("s011", "slot_filling", "英文书名",
        [GoldenTurn("Harry Potter 有声书进度", expected_track="task", expected_flow="playback_query",
                    expected_slots={"album_title": "Harry Potter"})]),
    GoldenTestCase("s012", "slot_filling", "长书名",
        [GoldenTurn("《霸道总裁爱上我之宠妻无度》听书进度", expected_track="task", expected_flow="playback_query",
                    expected_slots={"album_title": "霸道总裁爱上我之宠妻无度"})]),

    # ---- 退款槽位 ----
    GoldenTestCase("s013", "slot_filling", "退款原因-不喜欢",
        [GoldenTurn("不喜欢这本书", expected_track="task", expected_flow="refund_apply",
                    expected_slots={"refund_reason": "不喜欢"})]),
    GoldenTestCase("s014", "slot_filling", "退款原因-买错了",
        [GoldenTurn("买错了想退", expected_track="task", expected_flow="refund_apply",
                    expected_slots={"refund_reason": "买错了"})]),
    GoldenTestCase("s015", "slot_filling", "退款原因-质量问题",
        [GoldenTurn("音质太差，听不清楚", expected_track="task", expected_flow="refund_apply",
                    expected_slots={"refund_reason": "音质太差"})]),
    GoldenTestCase("s016", "slot_filling", "退款原因-重复购买",
        [GoldenTurn("不小心重复购买了", expected_track="task", expected_flow="refund_apply",
                    expected_slots={"refund_reason": "重复购买"})]),
    GoldenTestCase("s017", "slot_filling", "退款原因-内容不符",
        [GoldenTurn("内容和介绍不符", expected_track="task", expected_flow="refund_apply",
                    expected_slots={"refund_reason": "内容和介绍不符"})]),

    # ---- 工单槽位 ----
    GoldenTestCase("s018", "slot_filling", "工单类型-Bug反馈",
        [GoldenTurn("APP经常闪退", expected_track="task", expected_flow="ticket_submit",
                    expected_slots={"ticket_type": "Bug反馈"})]),
    GoldenTestCase("s019", "slot_filling", "工单类型-功能建议",
        [GoldenTurn("希望能增加倍速播放功能", expected_track="task", expected_flow="ticket_submit",
                    expected_slots={"ticket_type": "功能建议"})]),
    GoldenTestCase("s020", "slot_filling", "工单描述详细",
        [GoldenTurn("播放到一半就自动停止了，每次都要重新打开APP才能继续", expected_track="task",
                    expected_flow="ticket_submit", expected_slots={"ticket_description": "播放到一半就自动停止了"})]),

    # ---- 组合槽位 ----
    GoldenTestCase("s021", "slot_filling", "退款-订单号+原因",
        [GoldenTurn("ORD000000000024我要退款，买错了", expected_track="task", expected_flow="refund_apply",
                    expected_slots={"order_number": "ORD000000000024", "refund_reason": "买错了"})]),
    GoldenTestCase("s022", "slot_filling", "退款-订单号+原因+类型",
        [GoldenTurn("订单ORD000000000028申请全额退款，不想要了", expected_track="task", expected_flow="refund_apply",
                    expected_slots={"order_number": "ORD000000000028", "refund_reason": "不想要了", "refund_type": "全额退款"})]),

    # ---- 模糊槽位（需要LLM推理） ----
    GoldenTestCase("s023", "slot_filling", "间接指代订单",
        [GoldenTurn("上面那个订单的详情", expected_track="task", expected_flow="order_query")]),
    GoldenTestCase("s024", "slot_filling", "时间指代",
        [GoldenTurn("上周买的那本书", expected_track="task", expected_flow="order_query")]),
    GoldenTestCase("s025", "slot_filling", "最新订单",
        [GoldenTurn("最新一笔订单", expected_track="task", expected_flow="order_query")]),

    # ---- 多种表达方式 ----
    GoldenTestCase("s026", "slot_filling", "口语退款",
        [GoldenTurn("能退钱吗？", expected_track="task", expected_flow="refund_apply")]),
    GoldenTestCase("s027", "slot_filling", "商量退款",
        [GoldenTurn("这个我不太满意，想退掉", expected_track="task", expected_flow="refund_apply")]),
    GoldenTestCase("s028", "slot_filling", "礼貌请求查订单",
        [GoldenTurn("麻烦帮我查一下订单ORD000000000032，谢谢", expected_track="task", expected_flow="order_query",
                    expected_slots={"order_number": "ORD000000000032"})]),
    GoldenTestCase("s029", "slot_filling", "简短查进度",
        [GoldenTurn("进度", expected_track="task", expected_flow="playback_query")]),
    GoldenTestCase("s030", "slot_filling", "问听书位置",
        [GoldenTurn("上次听到哪里了", expected_track="task", expected_flow="playback_query")]),

    # ---- 边缘槽位 ----
    GoldenTestCase("s031", "slot_filling", "订单号含字母数字混合",
        [GoldenTurn("ORD202507010000000036", expected_track="task", expected_flow="order_query",
                    expected_slots={"order_number": "ORD202507010000000036"})]),
    GoldenTestCase("s032", "slot_filling", "书名含特殊符号",
        [GoldenTurn("《C++编程思想》有声书进度", expected_track="task", expected_flow="playback_query",
                    expected_slots={"album_title": "C++编程思想"})]),
    GoldenTestCase("s033", "slot_filling", "退款-不满意",
        [GoldenTurn("听了几集不满意想退", expected_track="task", expected_flow="refund_apply",
                    expected_slots={"refund_reason": "不满意"})]),
    GoldenTestCase("s034", "slot_filling", "工单-App问题",
        [GoldenTurn("登录不上去了", expected_track="task", expected_flow="ticket_submit",
                    expected_slots={"ticket_type": "Bug反馈"})]),
    GoldenTestCase("s035", "slot_filling", "工单-内容问题",
        [GoldenTurn("这本书有章节重复了", expected_track="task", expected_flow="ticket_submit",
                    expected_slots={"ticket_type": "内容问题"})]),

    # ---- 多本书场景 ----
    GoldenTestCase("s036", "slot_filling", "两本书进度",
        [GoldenTurn("《三体》和《流浪地球》的进度分别是多少？", expected_track="task",
                    expected_flow="playback_query")]),
    GoldenTestCase("s037", "slot_filling", "最近听的书进度",
        [GoldenTurn("最近听的那本修仙小说进度", expected_track="task", expected_flow="playback_query")]),

    # ---- 订单号带说明文字 ----
    GoldenTestCase("s038", "slot_filling", "订单+状态询问",
        [GoldenTurn("我的订单ORD000000000040发货了吗？", expected_track="task", expected_flow="order_query",
                    expected_slots={"order_number": "ORD000000000040"})]),
    GoldenTestCase("s039", "slot_filling", "订单+支付问题",
        [GoldenTurn("ORD000000000044这笔订单支付失败了怎么回事", expected_track="task", expected_flow="order_query",
                    expected_slots={"order_number": "ORD000000000044"})]),
    GoldenTestCase("s040", "slot_filling", "退款+全部订单",
        [GoldenTurn("最近买的三本书都想退", expected_track="task", expected_flow="refund_apply")]),
]

# ============================================================
# 3. knowledge — 知识意图识别（40 条）
# ============================================================
KNOWLEDGE_CASES = [
    # ---- 会员相关 ----
    GoldenTestCase("k001", "knowledge", "会员权益详情",
        [GoldenTurn("高级会员有哪些权益？", expected_track="knowledge", expected_intent="membership_info")]),
    GoldenTestCase("k002", "knowledge", "会员续费",
        [GoldenTurn("怎么续费会员？", expected_track="knowledge", expected_intent="membership_info")]),
    GoldenTestCase("k003", "knowledge", "自动续费",
        [GoldenTurn("会员会自动续费吗？", expected_track="knowledge", expected_intent="membership_info")]),
    GoldenTestCase("k004", "knowledge", "取消会员",
        [GoldenTurn("怎么取消自动续费？", expected_track="knowledge", expected_intent="membership_info")]),
    GoldenTestCase("k005", "knowledge", "会员试用",
        [GoldenTurn("有免费试用吗？", expected_track="knowledge", expected_intent="membership_info")]),
    GoldenTestCase("k006", "knowledge", "会员优惠",
        [GoldenTurn("会员有什么优惠活动？", expected_track="knowledge", expected_intent="membership_info")]),
    GoldenTestCase("k007", "knowledge", "学生会员",
        [GoldenTurn("有学生价吗？", expected_track="knowledge", expected_intent="membership_info")]),
    GoldenTestCase("k008", "knowledge", "家庭会员",
        [GoldenTurn("可以共享会员给家人吗？", expected_track="knowledge", expected_intent="membership_info")]),

    # ---- 平台规则 ----
    GoldenTestCase("k009", "knowledge", "退款条件",
        [GoldenTurn("购买后多久可以退款？", expected_track="knowledge", expected_intent="platform_rule")]),
    GoldenTestCase("k010", "knowledge", "听书限制",
        [GoldenTurn("每天能听多久？", expected_track="knowledge", expected_intent="platform_rule")]),
    GoldenTestCase("k011", "knowledge", "下载数量",
        [GoldenTurn("最多能下载多少本书？", expected_track="knowledge", expected_intent="platform_rule")]),
    GoldenTestCase("k012", "knowledge", "版权说明",
        [GoldenTurn("下载的书可以分享给别人吗？", expected_track="knowledge", expected_intent="platform_rule")]),
    GoldenTestCase("k013", "knowledge", "发票相关",
        [GoldenTurn("怎么开发票？", expected_track="knowledge", expected_intent="platform_rule")]),
    GoldenTestCase("k014", "knowledge", "支付方式",
        [GoldenTurn("支持哪些支付方式？", expected_track="knowledge", expected_intent="platform_rule")]),
    GoldenTestCase("k015", "knowledge", "账号安全",
        [GoldenTurn("怎么修改密码？", expected_track="knowledge", expected_intent="platform_rule")]),
    GoldenTestCase("k016", "knowledge", "隐私政策",
        [GoldenTurn("我的听书记录会被别人看到吗？", expected_track="knowledge", expected_intent="platform_rule")]),

    # ---- 专辑/作品信息 ----
    GoldenTestCase("k017", "knowledge", "作品简介",
        [GoldenTurn("《三体》讲的是什么？", expected_track="knowledge", expected_intent="album_info")]),
    GoldenTestCase("k018", "knowledge", "演播者信息",
        [GoldenTurn("这本书是谁播讲的？", expected_track="knowledge", expected_intent="album_info")]),
    GoldenTestCase("k019", "knowledge", "作品评分",
        [GoldenTurn("《诡秘之主》评分多少？", expected_track="knowledge", expected_intent="album_info")]),
    GoldenTestCase("k020", "knowledge", "章节数",
        [GoldenTurn("《全职高手》一共多少章？", expected_track="knowledge", expected_intent="album_info")]),
    GoldenTestCase("k021", "knowledge", "完结状态",
        [GoldenTurn("《剑来》完结了吗？", expected_track="knowledge", expected_intent="album_info")]),
    GoldenTestCase("k022", "knowledge", "类似推荐",
        [GoldenTurn("有没有类似《鬼吹灯》的书？", expected_track="knowledge", expected_intent="album_info")]),
    GoldenTestCase("k023", "knowledge", "分类浏览",
        [GoldenTurn("有什么好看的玄幻小说？", expected_track="knowledge", expected_intent="album_info")]),
    GoldenTestCase("k024", "knowledge", "新书上架",
        [GoldenTurn("最近有什么新书上架？", expected_track="knowledge", expected_intent="album_info")]),

    # ---- 会员相关问题（容易误判为 task 的） ----
    GoldenTestCase("k025", "knowledge", "我要查会员",
        [GoldenTurn("我要查询我的会员信息", expected_track="knowledge", expected_intent="membership_info")]),
    GoldenTestCase("k026", "knowledge", "帮我看看会员",
        [GoldenTurn("帮我看看会员等级", expected_track="knowledge", expected_intent="membership_info")]),
    GoldenTestCase("k027", "knowledge", "查看会员权益",
        [GoldenTurn("查看会员权益", expected_track="knowledge", expected_intent="membership_info")]),
    GoldenTestCase("k028", "knowledge", "了解一下会员",
        [GoldenTurn("了解会员权益", expected_track="knowledge", expected_intent="membership_info")]),

    # ---- 知识类综合 ----
    GoldenTestCase("k029", "knowledge", "如何下载",
        [GoldenTurn("书怎么下载到手机上？", expected_track="knowledge", expected_intent="platform_rule")]),
    GoldenTestCase("k030", "knowledge", "倍速播放",
        [GoldenTurn("怎么调播放速度？", expected_track="knowledge", expected_intent="platform_rule")]),
    GoldenTestCase("k031", "knowledge", "定时关闭",
        [GoldenTurn("有定时关闭功能吗？", expected_track="knowledge", expected_intent="platform_rule")]),
    GoldenTestCase("k032", "knowledge", "排行榜",
        [GoldenTurn("现在什么书最火？", expected_track="knowledge", expected_intent="album_info")]),
    GoldenTestCase("k033", "knowledge", "VIP专享",
        [GoldenTurn("哪些书是会员专享的？", expected_track="knowledge", expected_intent="membership_info")]),
    GoldenTestCase("k034", "knowledge", "积分规则",
        [GoldenTurn("积分怎么获取？", expected_track="knowledge", expected_intent="platform_rule")]),
    GoldenTestCase("k035", "knowledge", "听书时长",
        [GoldenTurn("我总共听了多长时间？", expected_track="knowledge", expected_intent="membership_info")]),
    GoldenTestCase("k036", "knowledge", "退款政策详情",
        [GoldenTurn("退款需要什么条件？", expected_track="knowledge", expected_intent="platform_rule")]),
    GoldenTestCase("k037", "knowledge", "礼品卡",
        [GoldenTurn("怎么购买礼品卡？", expected_track="knowledge", expected_intent="platform_rule")]),
    GoldenTestCase("k038", "knowledge", "播放器设置",
        [GoldenTurn("怎么设置睡眠模式？", expected_track="knowledge", expected_intent="platform_rule")]),
    GoldenTestCase("k039", "knowledge", "有声书分类",
        [GoldenTurn("有没有适合孩子听的书？", expected_track="knowledge", expected_intent="album_info")]),
    GoldenTestCase("k040", "knowledge", "会员听书范围",
        [GoldenTurn("会员能听所有书吗还是部分？", expected_track="knowledge", expected_intent="membership_info")]),
]

# ============================================================
# 4. flow_completion — 完整多轮业务流程（20 条）
# ============================================================
FLOW_COMPLETION_CASES = [
    # ---- 订单查询完整流程 ----
    GoldenTestCase("f001", "flow_completion", "订单查询-完整流程",
        [GoldenTurn("查订单ORD000000000004", expected_track="task", expected_flow="order_query",
                    expected_slots={"order_number": "ORD000000000004"})]),
    GoldenTestCase("f002", "flow_completion", "订单查询-先问再给号",
        [GoldenTurn("我想查订单", expected_track="task", expected_flow="order_query")]),
    GoldenTestCase("f003", "flow_completion", "订单查询-多个订单号",
        [GoldenTurn("帮我查三个订单ORD000000000004 ORD000000000008 ORD000000000012",
                    expected_track="task", expected_flow="order_query")]),

    # ---- 退款完整流程（多轮） ----
    GoldenTestCase("f004", "flow_completion", "退款-完整多轮",
        [
            GoldenTurn("我要退款", expected_track="task", expected_flow="refund_apply"),
            GoldenTurn("ORD000000000004", expected_track="task", expected_flow="refund_apply",
                      expected_slots={"order_number": "ORD000000000004"}),
            GoldenTurn("不喜欢", expected_track="task", expected_flow="refund_apply",
                      expected_slots={"refund_reason": "不喜欢"}),
        ]),
    GoldenTestCase("f005", "flow_completion", "退款-一步到位",
        [GoldenTurn("ORD000000000008退款，买错了", expected_track="task", expected_flow="refund_apply",
                    expected_slots={"order_number": "ORD000000000008", "refund_reason": "买错了"})]),

    # ---- 工单完整流程（多轮） ----
    GoldenTestCase("f006", "flow_completion", "工单-完整多轮",
        [
            GoldenTurn("提交一个问题", expected_track="task", expected_flow="ticket_submit"),
            GoldenTurn("APP经常闪退，特别是在播放音频的时候", expected_track="task", expected_flow="ticket_submit",
                      expected_slots={"ticket_type": "Bug反馈", "ticket_description": "APP经常闪退"}),
        ]),

    # ---- 播放记录查询 ----
    GoldenTestCase("f007", "flow_completion", "播放记录-最近播放",
        [GoldenTurn("我最近听了什么", expected_track="task", expected_flow="playback_query")]),
    GoldenTestCase("f008", "flow_completion", "播放记录-指定书名",
        [GoldenTurn("《三体》听到哪里了", expected_track="task", expected_flow="playback_query",
                    expected_slots={"album_title": "三体"})]),

    # ---- 流程中断与恢复 ----
    GoldenTestCase("f009", "flow_completion", "退款中闲聊后继续",
        [
            GoldenTurn("我要退款", expected_track="task", expected_flow="refund_apply"),
            GoldenTurn("你好", expected_track="chitchat"),
            GoldenTurn("ORD000000000004", expected_track="task", expected_flow="refund_apply",
                      expected_slots={"order_number": "ORD000000000004"}),
        ]),
    GoldenTestCase("f010", "flow_completion", "退款中查知识后继续",
        [
            GoldenTurn("我要退款", expected_track="task", expected_flow="refund_apply"),
            GoldenTurn("退款政策是什么？", expected_track="knowledge", expected_intent="platform_rule"),
            GoldenTurn("ORD000000000008", expected_track="task", expected_flow="refund_apply",
                      expected_slots={"order_number": "ORD000000000008"}),
            GoldenTurn("买错了", expected_track="task", expected_flow="refund_apply",
                      expected_slots={"refund_reason": "买错了"}),
        ]),

    # ---- 欢迎引导 ----
    GoldenTestCase("f011", "flow_completion", "新用户欢迎",
        [GoldenTurn("你好", expected_track="chitchat")]),

    # ---- 多流程切换 ----
    GoldenTestCase("f012", "flow_completion", "退款后查订单",
        [
            GoldenTurn("ORD000000000004退款，买错了", expected_track="task", expected_flow="refund_apply",
                      expected_slots={"order_number": "ORD000000000004", "refund_reason": "买错了"}),
            GoldenTurn("再查一下ORD000000000012", expected_track="task", expected_flow="order_query",
                      expected_slots={"order_number": "ORD000000000012"}),
        ]),

    # ---- 专辑详情 ----
    GoldenTestCase("f013", "flow_completion", "专辑详情查询",
        [GoldenTurn("《三体》详细信息", expected_track="knowledge", expected_intent="album_info")]),

    # ---- 多轮播放记录 ----
    GoldenTestCase("f014", "flow_completion", "连续查两本书进度",
        [
            GoldenTurn("《三体》听到哪里了", expected_track="task", expected_flow="playback_query",
                      expected_slots={"album_title": "三体"}),
            GoldenTurn("那《流浪地球》呢", expected_track="task", expected_flow="playback_query",
                      expected_slots={"album_title": "流浪地球"}),
        ]),

    # ---- 复杂退款多轮 ----
    GoldenTestCase("f015", "flow_completion", "退款-三要素分步",
        [
            GoldenTurn("退款", expected_track="task", expected_flow="refund_apply"),
            GoldenTurn("ORD000000000016", expected_track="task", expected_flow="refund_apply",
                      expected_slots={"order_number": "ORD000000000016"}),
            GoldenTurn("内容重复", expected_track="task", expected_flow="refund_apply",
                      expected_slots={"refund_reason": "内容重复"}),
        ]),

    # ---- 边界流程 ----
    GoldenTestCase("f016", "flow_completion", "退款后取消",
        [
            GoldenTurn("我要退款", expected_track="task", expected_flow="refund_apply"),
            GoldenTurn("算了不退了", expected_track="task"),
        ]),

    # ---- 单轮完整信息 ----
    GoldenTestCase("f017", "flow_completion", "工单-一步到位",
        [GoldenTurn("反馈bug：播放到38分钟就闪退", expected_track="task", expected_flow="ticket_submit",
                    expected_slots={"ticket_type": "Bug反馈", "ticket_description": "播放到38分钟就闪退"})]),

    # ---- 欢迎引导流程 ----
    GoldenTestCase("f018", "flow_completion", "首次使用咨询",
        [GoldenTurn("我第一次用，不知道怎么开始", expected_track="task", expected_flow="onboarding")]),

    GoldenTestCase("f019", "flow_completion", "退款后重试",
        [
            GoldenTurn("ORD000000000020退款，不想要了", expected_track="task", expected_flow="refund_apply",
                      expected_slots={"order_number": "ORD000000000020", "refund_reason": "不想要了"}),
            GoldenTurn("算了还是退ORD000000000024吧", expected_track="task", expected_flow="refund_apply",
                      expected_slots={"order_number": "ORD000000000024"}),
        ]),

    GoldenTestCase("f020", "flow_completion", "查完订单再查播放",
        [
            GoldenTurn("查订单ORD000000000004", expected_track="task", expected_flow="order_query",
                      expected_slots={"order_number": "ORD000000000004"}),
            GoldenTurn("我最近听了什么", expected_track="task", expected_flow="playback_query"),
        ]),
]

# ============================================================
# 5. anti_interference — 防历史干扰（20 条）
# ============================================================
ANTI_INTERFERENCE_CASES = [
    GoldenTestCase("a001", "anti_interference", "多轮task后查会员",
        [
            GoldenTurn("查订单ORD000000000004", expected_track="task", expected_flow="order_query",
                      expected_slots={"order_number": "ORD000000000004"}),
            GoldenTurn("帮我查一下ORD000000000008", expected_track="task", expected_flow="order_query",
                      expected_slots={"order_number": "ORD000000000008"}),
            GoldenTurn("我要查询我的会员信息", expected_track="knowledge", expected_intent="membership_info"),
        ]),
    GoldenTestCase("a002", "anti_interference", "退款后问会员",
        [
            GoldenTurn("ORD000000000004退款，买错了", expected_track="task", expected_flow="refund_apply",
                      expected_slots={"order_number": "ORD000000000004", "refund_reason": "买错了"}),
            GoldenTurn("会员有什么权益", expected_track="knowledge", expected_intent="membership_info"),
        ]),
    GoldenTestCase("a003", "anti_interference", "工单后问平台规则",
        [
            GoldenTurn("APP老是闪退", expected_track="task", expected_flow="ticket_submit"),
            GoldenTurn("多久能退款", expected_track="knowledge", expected_intent="platform_rule"),
        ]),
    GoldenTestCase("a004", "anti_interference", "查订单后问退款政策",
        [
            GoldenTurn("查订单ORD000000000004", expected_track="task", expected_flow="order_query",
                      expected_slots={"order_number": "ORD000000000004"}),
            GoldenTurn("退款有什么条件吗", expected_track="knowledge", expected_intent="platform_rule"),
        ]),
    GoldenTestCase("a005", "anti_interference", "多次task后查帮助",
        [
            GoldenTurn("查订单ORD000000000004", expected_track="task", expected_flow="order_query"),
            GoldenTurn("ORD000000000008", expected_track="task", expected_flow="order_query",
                      expected_slots={"order_number": "ORD000000000008"}),
            GoldenTurn("我最近听了什么", expected_track="task", expected_flow="playback_query"),
            GoldenTurn("怎么使用这个APP", expected_track="knowledge", expected_intent="platform_rule"),
        ]),
    GoldenTestCase("a006", "anti_interference", "task后闲聊",
        [
            GoldenTurn("查订单ORD000000000004", expected_track="task", expected_flow="order_query"),
            GoldenTurn("谢谢你", expected_track="chitchat"),
        ]),
    GoldenTestCase("a007", "anti_interference", "task后问候",
        [
            GoldenTurn("我最近听了什么", expected_track="task", expected_flow="playback_query"),
            GoldenTurn("你好", expected_track="chitchat"),
        ]),
    GoldenTestCase("a008", "anti_interference", "多轮会员+查询混合",
        [
            GoldenTurn("会员有什么权益", expected_track="knowledge", expected_intent="membership_info"),
            GoldenTurn("高级会员多少钱", expected_track="knowledge", expected_intent="membership_info"),
            GoldenTurn("怎么升级", expected_track="knowledge", expected_intent="membership_info"),
            GoldenTurn("查一下我的订单ORD000000000004", expected_track="task", expected_flow="order_query",
                      expected_slots={"order_number": "ORD000000000004"}),
        ]),

    # ---- 最易出错的场景：bot回复中含"订单"等词 ----
    GoldenTestCase("a009", "anti_interference", "会员FAQ后仍查会员",
        [
            GoldenTurn("会员可以退款吗", expected_track="knowledge", expected_intent="platform_rule"),
            GoldenTurn("我要查我的会员等级", expected_track="knowledge", expected_intent="membership_info"),
        ]),
    GoldenTestCase("a010", "anti_interference", "退款FAQ后查会员",
        [
            GoldenTurn("退款政策是什么", expected_track="knowledge", expected_intent="platform_rule"),
            GoldenTurn("我的会员还有多久到期", expected_track="knowledge", expected_intent="membership_info"),
        ]),
    GoldenTestCase("a011", "anti_interference", "任务中断后知识查询",
        [
            GoldenTurn("我要退款", expected_track="task", expected_flow="refund_apply"),
            GoldenTurn("怎么查看会员权益", expected_track="knowledge", expected_intent="membership_info"),
            GoldenTurn("高级会员有什么好处", expected_track="knowledge", expected_intent="membership_info"),
        ]),
    GoldenTestCase("a012", "anti_interference", "连续多任务后知识",
        [
            GoldenTurn("查订单ORD000000000004", expected_track="task", expected_flow="order_query"),
            GoldenTurn("我最近听了什么", expected_track="task", expected_flow="playback_query"),
            GoldenTurn("我要退款", expected_track="task", expected_flow="refund_apply"),
            GoldenTurn("会员有哪些类型", expected_track="knowledge", expected_intent="membership_info"),
        ]),
    GoldenTestCase("a013", "anti_interference", "流程中断后问规则",
        [
            GoldenTurn("我要提交工单", expected_track="task", expected_flow="ticket_submit"),
            GoldenTurn("平台支持哪些支付方式", expected_track="knowledge", expected_intent="platform_rule"),
        ]),
    GoldenTestCase("a014", "anti_interference", "知识后问task",
        [
            GoldenTurn("会员多少钱", expected_track="knowledge", expected_intent="membership_info"),
            GoldenTurn("可以离线听吗", expected_track="knowledge", expected_intent="platform_rule"),
            GoldenTurn("查我的订单ORD000000000004", expected_track="task", expected_flow="order_query",
                      expected_slots={"order_number": "ORD000000000004"}),
        ]),
    GoldenTestCase("a015", "anti_interference", "长时间对话后仍能路由",
        [
            GoldenTurn("你好", expected_track="chitchat"),
            GoldenTurn("查订单ORD000000000004", expected_track="task", expected_flow="order_query"),
            GoldenTurn("谢谢你", expected_track="chitchat"),
            GoldenTurn("我最近听了什么", expected_track="task", expected_flow="playback_query"),
            GoldenTurn("好的", expected_track="chitchat"),
            GoldenTurn("我要查我的会员信息", expected_track="knowledge", expected_intent="membership_info"),
        ]),
    GoldenTestCase("a016", "anti_interference", "bot回复含订单关键词后仍路由正确",
        [
            GoldenTurn("我要退款", expected_track="task", expected_flow="refund_apply"),
            # bot会回复类似"订单详情页可以申请退款" —— 这里继续问会员
            GoldenTurn("查看会员权益", expected_track="knowledge", expected_intent="membership_info"),
        ]),
    GoldenTestCase("a017", "anti_interference", "多轮混合不混淆",
        [
            GoldenTurn("会员到期时间", expected_track="knowledge", expected_intent="membership_info"),
            GoldenTurn("ORD000000000008", expected_track="task", expected_flow="order_query",
                      expected_slots={"order_number": "ORD000000000008"}),
            GoldenTurn("怎么下载离线", expected_track="knowledge", expected_intent="platform_rule"),
            GoldenTurn("《剑来》进度", expected_track="task", expected_flow="playback_query",
                      expected_slots={"album_title": "剑来"}),
            GoldenTurn("你好", expected_track="chitchat"),
        ]),
    GoldenTestCase("a018", "anti_interference", "退款流程中突然查帮助",
        [
            GoldenTurn("我要退款", expected_track="task", expected_flow="refund_apply"),
            GoldenTurn("ORD000000000004", expected_track="task", expected_flow="refund_apply",
                      expected_slots={"order_number": "ORD000000000004"}),
            GoldenTurn("退款一般多久到账", expected_track="knowledge", expected_intent="platform_rule"),
        ]),
    GoldenTestCase("a019", "anti_interference", "工单后查会员",
        [
            GoldenTurn("APP有问题", expected_track="task", expected_flow="ticket_submit"),
            GoldenTurn("会员快到期了怎么续", expected_track="knowledge", expected_intent="membership_info"),
        ]),
    GoldenTestCase("a020", "anti_interference", "多知识查询不误判为task",
        [
            GoldenTurn("会员有什么类型", expected_track="knowledge", expected_intent="membership_info"),
            GoldenTurn("怎么下载书", expected_track="knowledge", expected_intent="platform_rule"),
            GoldenTurn("有什么好书推荐", expected_track="knowledge", expected_intent="album_info"),
            GoldenTurn("积分怎么用", expected_track="knowledge", expected_intent="platform_rule"),
        ]),
]

# ============================================================
# 6. edge_case — 边界情况（20 条）
# ============================================================
EDGE_CASES = [
    GoldenTestCase("e001", "edge_case", "空文本",
        [GoldenTurn("", expected_track="clarify")]),
    GoldenTestCase("e002", "edge_case", "超长文本",
        [GoldenTurn("请问" + "这个" * 100 + "订单怎么查？", expected_track="task", expected_flow="order_query")]),
    GoldenTestCase("e003", "edge_case", "纯空格",
        [GoldenTurn("   ", expected_track="clarify")]),
    GoldenTestCase("e004", "edge_case", "纯标点",
        [GoldenTurn("？。。！", expected_track="clarify")]),
    GoldenTestCase("e005", "edge_case", "纯数字",
        [GoldenTurn("12345678", expected_track="clarify")]),
    GoldenTestCase("e006", "edge_case", "特殊字符",
        [GoldenTurn("@#$%^&*()", expected_track="clarify")]),
    GoldenTestCase("e007", "edge_case", "emoji",
        [GoldenTurn("😊😊😊", expected_track="clarify")]),
    GoldenTestCase("e008", "edge_case", "英文问句",
        [GoldenTurn("How can I check my membership?", expected_track="knowledge", expected_intent="membership_info")]),
    GoldenTestCase("e009", "edge_case", "中英混合",
        [GoldenTurn("我的VIP membership什么时候expire？", expected_track="knowledge",
                    expected_intent="membership_info")]),
    GoldenTestCase("e010", "edge_case", "换行符",
        [GoldenTurn("查询订单\nORD000000000004", expected_track="task", expected_flow="order_query",
                    expected_slots={"order_number": "ORD000000000004"})]),
    GoldenTestCase("e011", "edge_case", "HTML字符",
        [GoldenTurn("<b>查询</b>订单", expected_track="task", expected_flow="order_query")]),
    GoldenTestCase("e012", "edge_case", "SQL注入式输入",
        [GoldenTurn("'; DROP TABLE users; --", expected_track="clarify")]),
    GoldenTestCase("e013", "edge_case", "重复字符",
        [GoldenTurn("啊啊啊啊啊啊啊啊", expected_track="clarify")]),
    GoldenTestCase("e014", "edge_case", "URL输入",
        [GoldenTurn("https://example.com/order/123", expected_track="clarify")]),
    GoldenTestCase("e015", "edge_case", "极简输入-好",
        [GoldenTurn("好", expected_track="clarify")]),
    GoldenTestCase("e016", "edge_case", "极简输入-行",
        [GoldenTurn("行", expected_track="clarify")]),
    GoldenTestCase("e017", "edge_case", "极简输入-查",
        [GoldenTurn("查", expected_track="clarify")]),
    GoldenTestCase("e018", "edge_case", "仅标点+字母",
        [GoldenTurn("ord000000000004", expected_track="task", expected_flow="order_query",
                    expected_slots={"order_number": "ord000000000004"})]),
    GoldenTestCase("e019", "edge_case", "订单号小写",
        [GoldenTurn("ord000000000004", expected_track="task", expected_flow="order_query",
                    expected_slots={"order_number": "ord000000000004"})]),
    GoldenTestCase("e020", "edge_case", "带脏话的查询",
        [GoldenTurn("TMD这个破APP怎么查订单", expected_track="task", expected_flow="order_query")]),
]

# ============================================================
# 7. clarify — 澄清触发（20 条）
# ============================================================
CLARIFY_CASES = [
    GoldenTestCase("c001", "clarify", "单字-嗯",
        [GoldenTurn("嗯", expected_track="clarify")]),
    GoldenTestCase("c002", "clarify", "单字-哦",
        [GoldenTurn("哦", expected_track="clarify")]),
    GoldenTestCase("c003", "clarify", "单字-啊",
        [GoldenTurn("啊", expected_track="clarify")]),
    GoldenTestCase("c004", "clarify", "模糊指代-那个",
        [GoldenTurn("那个呢", expected_track="clarify")]),
    GoldenTestCase("c005", "clarify", "模糊指代-这个",
        [GoldenTurn("这个怎么弄", expected_track="clarify")]),
    GoldenTestCase("c006", "clarify", "模糊指代-帮我看看",
        [GoldenTurn("帮我看看", expected_track="clarify")]),
    GoldenTestCase("c007", "clarify", "模糊指代-怎么办",
        [GoldenTurn("怎么办", expected_track="clarify")]),
    GoldenTestCase("c008", "clarify", "模糊指代-然后呢",
        [GoldenTurn("然后呢", expected_track="clarify")]),
    GoldenTestCase("c009", "clarify", "模糊指代-为什么",
        [GoldenTurn("为什么", expected_track="clarify")]),
    GoldenTestCase("c010", "clarify", "纯感叹词",
        [GoldenTurn("哎", expected_track="clarify")]),
    GoldenTestCase("c011", "clarify", "无法判断-帮我",
        [GoldenTurn("帮帮我", expected_track="clarify")]),
    GoldenTestCase("c012", "clarify", "无法判断-有问题",
        [GoldenTurn("有个问题", expected_track="clarify")]),
    GoldenTestCase("c013", "clarify", "无法判断-不懂",
        [GoldenTurn("不太懂", expected_track="clarify")]),
    GoldenTestCase("c014", "clarify", "无法判断-看不懂",
        [GoldenTurn("看不懂", expected_track="clarify")]),
    GoldenTestCase("c015", "clarify", "纯表情",
        [GoldenTurn(":-)", expected_track="clarify")]),
    GoldenTestCase("c016", "clarify", "随机字母",
        [GoldenTurn("xjdjdk", expected_track="clarify")]),
    GoldenTestCase("c017", "clarify", "不完整句子-我想",
        [GoldenTurn("我想...", expected_track="clarify")]),
    GoldenTestCase("c018", "clarify", "不完整句子-有没有",
        [GoldenTurn("有没有那种", expected_track="clarify")]),
    GoldenTestCase("c019", "clarify", "歧义语句-买",
        [GoldenTurn("买一个", expected_track="clarify")]),
    GoldenTestCase("c020", "clarify", "歧义语句-给我查",
        [GoldenTurn("给我查查", expected_track="clarify")]),
]

# ============================================================
# 汇总
# ============================================================
ALL_TEST_CASES: list[GoldenTestCase] = (
    ROUTING_CASES +
    SLOT_FILLING_CASES +
    KNOWLEDGE_CASES +
    FLOW_COMPLETION_CASES +
    ANTI_INTERFERENCE_CASES +
    EDGE_CASES +
    CLARIFY_CASES
)

# 按类别分组
TEST_CASES_BY_CATEGORY: dict[str, list[GoldenTestCase]] = {
    "routing": ROUTING_CASES,
    "slot_filling": SLOT_FILLING_CASES,
    "knowledge": KNOWLEDGE_CASES,
    "flow_completion": FLOW_COMPLETION_CASES,
    "anti_interference": ANTI_INTERFERENCE_CASES,
    "edge_case": EDGE_CASES,
    "clarify": CLARIFY_CASES,
}
