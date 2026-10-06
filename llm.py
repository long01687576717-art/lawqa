"""调用 DeepSeek 大模型，基于检索到的法条和案例生成回答。"""
import json
import re

import config
from case_tags import case_brief
from synonyms import expand_query

# 按 api_key 缓存客户端，支持多用户各自携带自己的 key（BYOK）
_clients = {}

SYSTEM_PROMPT = """你是一个专业的中国劳动法助手。你只能根据提供的参考资料回答关于劳动法、劳动合同、劳动争议、女职工保护、工资、加班等劳动法领域的问题。如果用户问的问题与劳动法完全无关（例如：如何做菜、写代码、股票推荐、天气、非劳动纠纷的刑事或民事问题），你必须礼貌拒绝回答，并提示用户：「抱歉，我目前只专注于劳动法相关的咨询，无法回答其他领域的问题。」严禁使用你自己的预训练通用知识去回答法律之外的问题。拒答仅适用于与劳动法明显无关的问题；属于劳动法范畴但参考资料不足的问题，不得使用拒答语句，应按照第10条如实说明并建议查阅，两类表述不得同时出现。

回答劳动法问题时，遵循以下要求：
1. 只依据【参考资料】中给出的法条和案例作答，严禁编造法条序号、条文内容或案号。
2. 引用法条时写清楚法律名称和第几条；引用案例时照抄【参考案例】中给出的案例名称（编号后、冒号前的文字），不得根据案情自拟或改写案例名称。
3. 若参考资料不足以回答，请如实说明「资料不足」，不要强行给出结论。
4. 语言专业、简洁、通俗，用中文，适当分点，不要输出与问题无关的内容。
5. 最后加一句：本回答仅供参考，不构成法律意见。
6. 如果在参考资料中，案例的案由与用户提问的核心场景不符（例如用户问996，却给出了试用期案例），严禁在回答中引用该案例，直接忽略它。
7. 如果【参考案例】为空或没有与问题场景高度相关的案例，请在回答中明确写出「本案暂无高度相关案例，仅提供法条分析」，不要强行引用不相关的案例。
8. 仅当《劳动法》与《劳动合同法》就同一事项的规定确实不一致时，才说明优先适用《劳动合同法》及原因（新法优于旧法，两部法律均由全国人大常委会制定）；两者规定一致或可相互印证时，直接引用，不要写这一说明。
9. 如果某条法条附带了「调整说明」（形如"注意：……"），必须如实转述该说明，不得把已被后续法律法规调整的过时规定当作现行规定回答。
10. 问题涉及知识库未收录的专门法规或地方规定时，可以说明相关法规名称并建议用户查阅，但不得输出该法规的具体内容（条号、适用要件、天数、比例、金额等），不得用不完整规定冒充完整结论。
11. 只能引用【参考资料】中实际出现的条文；需要的条文在参考资料中未提供时，如实说明「相关条文未检索到」，不得凭记忆编造条号或条文内容；涉及库外法规时只写法规名称，不写条号。法条附带的调整说明中已写明的内容（包括其中的法规名称和条号）可以如实转述，本条限制的是参考资料之外、凭记忆补充的内容。
12. 全文使用中文，不得夹杂英文。
13. 【参考法条】中法规名称后的括号标注了层级（法律、行政法规、司法解释、部门规章）。配套法规（实施条例、司法解释、部门规章等）对法律作出具体规定（天数、比例、期限、计算标准、适用条件）时，应与法律条文一并引用；不同层级的规定不一致时，以上位法为准并说明。引用时写出法规全称和条号。"""

REWRITE_SYSTEM_PROMPT = """你是一个资深法律检索助手。请先判断用户的口语化问题属于以下哪个核心劳动法场景，再将其改写为适合检索的专业法律术语关键词。

核心场景（只能从中选一个）：加班费、未签劳动合同、违法解除、工伤认定、试用期、女职工保护、拖欠工资、经济补偿金、竞业限制、劳务派遣、年休假、社会保险。

如果用户问题完全不涉及劳动法，或不属于上述任何一个核心场景，scenario 填「无」，keywords 填空字符串。

你必须只输出一个 JSON 对象，不要输出任何解释、不要用代码块包裹，格式如下：
{"scenario": "加班费", "keywords": "违法延长工作时间 强迫劳动 加班费"}"""


def _get_client(api_key):
    """按 api_key 复用 OpenAI 客户端（BYOK：每个用户各一个）。"""
    if api_key not in _clients:
        from openai import OpenAI

        _clients[api_key] = OpenAI(api_key=api_key, base_url=config.DEEPSEEK_BASE_URL)
    return _clients[api_key]


def build_prompt(question, laws, cases):
    parts = ["【用户问题】", question, "", "【参考法条】"]
    if laws:
        for i, l in enumerate(laws, 1):
            tag = "（关联条文）" if l.get('_cited') else ""
            level = f"（{l['level']}）" if l.get('level') else ""
            line = f"{i}. 《{l.get('law', '')}》{level}第{l.get('article', '')}条{tag}：{l.get('text', '')}"
            if l.get('note'):
                line += f"【调整说明】{l.get('note')}"
            parts.append(line)
    else:
        parts.append("（无）")

    parts += ["", "【参考案例】"]
    if cases:
        for i, c in enumerate(cases, 1):
            parts.append(case_brief(i, c))
    else:
        parts.append("（无）")

    return "\n".join(parts)


def generate_answer(question, laws, cases, api_key):
    client = _get_client(api_key)
    resp = client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_prompt(question, laws, cases)},
        ],
        temperature=0.3,
        stream=False,
    )
    return resp.choices[0].message.content.strip()


def rewrite_query(question, api_key):
    """改写 + 场景判断，返回 {"scenario": ..., "keywords": ...}。

    scenario 取值：12 个核心场景之一 / "无"（非劳动法）/ None（解析失败）。
    """
    client = _get_client(api_key)
    resp = client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        temperature=0.1,
        stream=False,
    )
    rw = _parse_rewrite(resp.choices[0].message.content.strip(), question)
    # 主检索词：改写后的专业词（可能为空，由调用方用原问题兜底）
    rw["keywords"] = (rw.get("keywords") or "").strip()
    # 口语扩展检索词：原问题 + 同义词扩展，作为独立一路检索（避免稀释主检索词）
    rw["oral_query"] = expand_query(question)
    return rw


def _parse_rewrite(raw, fallback_question):
    """解析大模型返回的 JSON；解析失败则回退为「不限制场景 + 原问题」。"""
    data = None
    try:
        data = json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            try:
                data = json.loads(m.group(0))
            except Exception:
                data = None
    if not isinstance(data, dict):
        return {"scenario": None, "keywords": fallback_question}
    scenario = (data.get("scenario") or "").strip()
    keywords = (data.get("keywords") or "").strip()
    if scenario == "无" or not scenario:
        return {"scenario": "无", "keywords": ""}
    return {"scenario": scenario, "keywords": keywords or fallback_question}
