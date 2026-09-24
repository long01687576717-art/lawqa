"""调用 DeepSeek 大模型，基于检索到的法条和案例生成回答。"""
import json
import re

import config

# 按 api_key 缓存客户端，支持多用户各自携带自己的 key（BYOK）
_clients = {}

SYSTEM_PROMPT = """你是一个专业的中国劳动法助手。你只能根据提供的参考资料回答关于劳动法、劳动合同、劳动争议、女职工保护、工资、加班等劳动法领域的问题。如果用户问的问题与劳动法完全无关（例如：如何做菜、写代码、股票推荐、天气、非劳动纠纷的刑事或民事问题），你必须礼貌拒绝回答，并提示用户：「抱歉，我目前只专注于劳动法相关的咨询，无法回答其他领域的问题。」严禁使用你自己的预训练通用知识去回答法律之外的问题。

回答劳动法问题时，遵循以下要求：
1. 只依据【参考资料】中给出的法条和案例作答，严禁编造法条序号、条文内容或案号。
2. 引用法条时写清楚法律名称和第几条；引用案例时写清楚案例名称。
3. 若参考资料不足以回答，请如实说明「资料不足」，不要强行给出结论。
4. 语言专业、简洁、通俗，用中文，适当分点，不要输出与问题无关的内容。
5. 最后加一句：本回答仅供参考，不构成法律意见。
6. 如果在参考资料中，案例的案由与用户提问的核心场景不符（例如用户问996，却给出了试用期案例），严禁在回答中引用该案例，直接忽略它。
7. 如果【参考案例】为空或没有与问题场景高度相关的案例，请在回答中明确写出「本案参考资料中暂无高度相关的案例」，不要强行引用不相关的案例。"""

REWRITE_SYSTEM_PROMPT = """你是一个资深法律检索助手。请先判断用户的口语化问题属于以下哪个核心劳动法场景，再将其改写为适合检索的专业法律术语关键词。

核心场景（只能从中选一个）：加班费、未签劳动合同、违法解除、工伤认定、试用期、女职工保护、拖欠工资、经济补偿金、竞业限制、劳务派遣、年休假、社会保险。

如果用户问题完全不涉及劳动法，scenario 填「无」，keywords 填空字符串。

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
            parts.append(f"{i}. 《{l.get('law', '')}》第{l.get('article', '')}条：{l.get('text', '')}")
    else:
        parts.append("（无）")

    parts += ["", "【参考案例】"]
    if cases:
        for i, c in enumerate(cases, 1):
            parts.append(
                f"{i}. {c.get('title', '')}（{c.get('case_no', '')}）："
                f"{c.get('summary', '')} 裁判要点：{c.get('ruling', '')}"
            )
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
    return _parse_rewrite(resp.choices[0].message.content.strip(), question)


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
