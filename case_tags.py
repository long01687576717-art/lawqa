"""案例方向标签：标签表、问题识别、案例筛选，以及给大模型的案例摘要。

两层方向：
- 大方向：llm.py 查询改写给出的 12 个核心场景（不改动，保证法条召回稳定）；
- 细分标签：本文件的 TAGS，案例可打多个标签，问题按关键词本地识别标签（不经大模型）。
案例筛选 = 「大方向对应的标签」或「问题识别出的标签」与案例标签有重合 → BM25 + 标签命中加分排序。
"""
import math
import re

# 标签 → 识别关键词（同时用于案例自动打标和用户问题识别，按 HR 常见问法设计）
TAGS = {
    "劳动关系认定": ["确认劳动关系", "认定劳动关系", "存在劳动关系", "劳动关系认定", "劳动关系的认定", "是不是劳动关系",
                 "算劳动关系", "合作协议", "承揽", "个体工商户", "承包合同", "劳务关系", "混同用工", "用工主体", "用工事实"],
    "平台用工": ["平台企业", "平台用工", "网络平台", "互联网平台", "骑手", "外卖", "网约", "主播", "代驾", "家政",
             "新就业形态", "配送员"],
    "未签合同二倍工资": ["未签", "没签", "不签合同", "未订立书面劳动合同", "未与劳动者订立书面劳动合同", "二倍工资", "双倍工资", "补签", "倒签"],
    "试用期": ["试用期", "录用条件", "转正"],
    "招聘与录用": ["录用通知", "offer", "Offer", "聘用通知", "取消录用", "简历", "学历造假", "虚假学历", "假学历", "伪造学历", "背景调查", "就业信息", "预约合同", "缔约过失", "押金",
               "扣押", "身份证", "入职体检", "冒用"],
    "调岗调薪": ["调岗", "调整岗位", "调整工作岗位", "降薪", "降职", "调薪", "工作地点", "搬迁", "待岗", "变更劳动合同"],
    "规章制度与违纪": ["规章制度", "员工手册", "严重违反", "违纪", "旷工", "迟到", "考勤", "劳动纪律", "替岗"],
    "工时与加班": ["加班", "996", "工时", "不定时工作制", "综合计算工时", "延长工作时间", "值班", "线上工作", "隐形加班", "节假日", "工作时间"],
    "工资支付与欠薪": ["欠薪", "拖欠", "克扣", "劳动报酬", "最低工资", "奖金", "年终奖", "提成", "工资支付", "停工停产", "包薪", "拒不支付", "工资异议"],
    "休息休假": ["年休假", "年假", "带薪年休假", "病假", "医疗期", "护理假", "育儿假", "婚假", "休假"],
    "女职工保护": ["女职工", "怀孕", "孕期", "产假", "哺乳", "三期", "生育", "恋爱结婚"],
    "单位解除合同": ["违法解除", "辞退", "开除", "解雇", "末位淘汰", "不能胜任", "客观情况发生重大变化", "单方解除", "裁员", "通知工会",
               "不胜任"],
    "绩效考核与不胜任": ["不胜任", "不能胜任", "末位", "绩效", "考核", "KPI"],
    "劳动者解除与离职": ["被迫解除", "辞职", "离职", "提前通知", "提前离职", "不批准", "不批"],
    "经济补偿与赔偿金": ["经济补偿", "补偿金", "赔偿金", "N+1", "工作年限"],
    "合同到期与续订": ["合同到期", "期满", "终止劳动合同", "续订", "续签", "无固定期限", "退休", "延迟退休", "换签"],
    "竞业限制": ["竞业限制", "竞业", "同业竞争", "竞争关系"],
    "保密与商业秘密": ["保密", "商业秘密", "保密费"],
    "服务期与违约金": ["服务期", "培训费", "违约金", "专项培训", "学历教育"],
    "社会保险": ["社保", "社会保险", "养老保险", "医疗保险", "抚恤金", "生育津贴", "视同缴费"],
    "住房公积金": ["公积金"],
    "工伤": ["工伤", "上下班途中", "停工留薪", "伤残", "因工", "职业病"],
    "劳务派遣与外包": ["劳务派遣", "派遣", "用工单位", "外包", "劳务公司", "分包", "转包", "挂靠"],
    "特殊用工": ["非全日制", "小时工", "兼职", "实习", "退休返聘", "返聘", "退休年龄", "退休金", "养老金", "超龄", "外国人", "高管", "高级管理人员"],
    "离职手续与证明": ["离职证明", "工作交接", "离职手续", "档案", "解除劳动合同证明"],
    "劳动者赔偿责任": ["赔偿损失", "重大过失", "造成损失", "给单位造成", "对赌"],
    "就业歧视与人格权": ["歧视", "平等就业", "性骚扰", "霸凌", "隐私", "乙肝", "病原携带", "传染病", "婚育"],
    "仲裁时效与举证": ["仲裁时效", "诉讼时效", "时效", "举证责任", "举证", "证据"],
    "事业单位人事争议": ["事业单位", "聘用合同", "人事争议"],
}

# 改写给出的大方向 → 对应标签
SCENARIO_TAGS = {
    "加班费": ["工时与加班"],
    "未签劳动合同": ["未签合同二倍工资", "劳动关系认定"],
    "违法解除": ["单位解除合同", "规章制度与违纪"],
    "工伤认定": ["工伤"],
    "试用期": ["试用期"],
    "女职工保护": ["女职工保护"],
    "拖欠工资": ["工资支付与欠薪"],
    "经济补偿金": ["经济补偿与赔偿金", "合同到期与续订"],
    "竞业限制": ["竞业限制", "保密与商业秘密"],
    "劳务派遣": ["劳务派遣与外包"],
    "年休假": ["休息休假"],
    "社会保险": ["社会保险"],
}
TAG_TO_SCENARIO = {t: s for s, ts in SCENARIO_TAGS.items() for t in ts}

BM25_WEIGHT = 5.0         # 候选内归一化 BM25（0~1）的权重（4~6 区间内关键题结果一致，取中值）
QUERY_TAG_WEIGHT = 1.0    # 与「问题识别标签」重合时，按标签稀有度（IDF）加分的权重
SCENARIO_TAG_WEIGHT = 0.5 # 与「大方向标签」重合时，取重合标签中最高的稀有度（IDF）加分（不累加，避免标签多的案例占便宜）
MIN_BM25 = 10.0           # BM25 原始分下限：低于此值说明案例与问题在文字上几乎不相关
TITLE_WEIGHT = 2.0        # 标题相关度（候选内归一化，0~1）的权重：典型案例标题多为裁判要旨，信息最集中
MAX_CASES = 3


def tags_of(text):
    """按关键词识别文本涉及的标签（保持 TAGS 中的顺序）。"""
    text = text or ""
    return [t for t, kws in TAGS.items() if any(k in text for k in kws)]


def primary_scenario(tags):
    """案例的大方向：取第一个能对应到 12 个场景的标签；都对应不上则为「其他」。"""
    return next((TAG_TO_SCENARIO[t] for t in tags if t in TAG_TO_SCENARIO), "其他")


def case_doc_text(c):
    """案例参与 BM25 检索的文本（不含篇幅很长的案例分析，避免稀释）。"""
    return " ".join(
        str(c.get(k, "")) for k in ("title", "keywords", "gist", "summary", "result", "significance")
    ) + " " + " ".join(c.get("tags", []))


def tag_idf(cases):
    """标签稀有度：案例越少的标签越能代表具体意图（如「离职手续与证明」比「单位解除合同」更具体）。"""
    n = len(cases) or 1
    df = {}
    for c in cases:
        for t in set(c.get("tags", [])):
            df[t] = df.get(t, 0) + 1
    return {t: math.log(n / d) for t, d in df.items()}


def select_cases(cases, scores, query_text, scenario, k=MAX_CASES, idf=None, title_scores=None):
    """按「标签重合」筛候选，再按「归一化 BM25 + 标题相关度 + 标签稀有度加分」排序，返回案例下标列表。

    - scenario 为「无」且问题识别不出任何标签：视为非劳动法问题，不返回案例；
    - BM25 原始分低于 MIN_BM25 的候选淘汰；全部淘汰则返回空（宁缺毋滥）。
    """
    if scores is None or len(scores) == 0:
        return []
    q_tags = set(tags_of(query_text))
    s_tags = set(SCENARIO_TAGS.get(scenario, []))
    if not q_tags and not s_tags:
        if scenario == "无":
            return []
        cand = list(range(len(cases)))  # 改写失败且识别不出标签：不限方向
    else:
        cand = [i for i, c in enumerate(cases) if set(c.get("tags", [])) & (q_tags | s_tags)]
    cand = [i for i in cand if float(scores[i]) >= MIN_BM25]
    if not cand:
        return []

    idf = idf if idf is not None else tag_idf(cases)
    top_bm25 = max(float(scores[i]) for i in cand)
    top_title = max((float(title_scores[i]) for i in cand), default=0) if title_scores is not None else 0

    def total(i):
        ct = set(cases[i].get("tags", []))
        title = TITLE_WEIGHT * float(title_scores[i]) / top_title if top_title > 0 else 0
        return (BM25_WEIGHT * float(scores[i]) / top_bm25 + title
                + QUERY_TAG_WEIGHT * sum(idf.get(t, 0) for t in ct & q_tags)
                + SCENARIO_TAG_WEIGHT * max((idf.get(t, 0) for t in ct & s_tags), default=0))

    return sorted(cand, key=total, reverse=True)[:k]


PARTY_LINE = re.compile(
    r"^((原审)?(原告|被告|第三人)|上诉人|被上诉人|再审申请人|申请再审人|被申请人|申请人|法定代表人|负责人|委托(诉讼)?代理人)"
    r"([（(][^）)]{0,15}[）)])?[：:]")


def _cut(text, n):
    text = (text or "").replace("\n", " ").strip()
    return text if len(text) <= n else text[:n] + "……"


def _facts(summary):
    """案情去掉开头的当事人身份行（公报案例常见），只做取舍、不改写。"""
    lines = (summary or "").split("\n")
    kept = [l for l in lines if not PARTY_LINE.match(l.strip())]
    return "\n".join(kept) or summary


def case_brief(i, c):
    """给大模型的案例摘要：案情 + 裁判要点/结果 + 典型意义（原文截取，不含全文分析）。"""
    head = f"{i}. {c.get('title', '')}"
    meta = "，".join(x for x in (c.get("court", ""), c.get("case_no", "")) if x)
    if meta:
        head += f"（{meta}）"
    parts = [head + "：", f"案情：{_cut(_facts(c.get('summary')), 500)}"]
    if c.get("gist"):
        parts.append(f"裁判要点：{_cut(c.get('gist'), 300)}")
    if c.get("result"):
        parts.append(f"裁判结果：{_cut(c.get('result'), 300)}")
    if not c.get("gist") and not c.get("result") and c.get("analysis"):
        parts.append(f"法院意见：{_cut(c.get('analysis'), 400)}")
    if c.get("significance"):
        parts.append(f"典型意义：{_cut(c.get('significance'), 250)}")
    return " ".join(parts)
