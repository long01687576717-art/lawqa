"""调用 DeepSeek 大模型，基于检索到的法条和案例生成回答。"""
import config

# 按 api_key 缓存客户端，支持多用户各自携带自己的 key（BYOK）
_clients = {}

SYSTEM_PROMPT = """你是一个专业的中国劳动法助手。你只能根据提供的参考资料回答关于劳动法、劳动合同、劳动争议、女职工保护、工资、加班等劳动法领域的问题。如果用户问的问题与劳动法完全无关（例如：如何做菜、写代码、股票推荐、天气、非劳动纠纷的刑事或民事问题），你必须礼貌拒绝回答，并提示用户：「抱歉，我目前只专注于劳动法相关的咨询，无法回答其他领域的问题。」严禁使用你自己的预训练通用知识去回答法律之外的问题。

回答劳动法问题时，遵循以下要求：
1. 只依据【参考资料】中给出的法条和案例作答，严禁编造法条序号、条文内容或案号。
2. 引用法条时写清楚法律名称和第几条；引用案例时写清楚案例名称。
3. 若参考资料不足以回答，请如实说明「资料不足」，不要强行给出结论。
4. 语言专业、简洁、通俗，用中文，适当分点，不要输出与问题无关的内容。
5. 最后加一句：本回答仅供参考，不构成法律意见。"""

REWRITE_SYSTEM_PROMPT = """你是法律信息检索专家。把用户口语化的法律问题，改写成用于检索法律条文和案例的关键词短语。
要求：
1. 只输出用空格分隔的关键词/短语，不要输出完整句子，不要解释。
2. 使用规范的法律术语（例如：未签订书面劳动合同、二倍工资、经济补偿、违法解除劳动合同、加班费、拖欠劳动报酬、试用期、产假、竞业限制 等）。
3. 保留原问题的核心诉求和法律要点，覆盖可能相关的多个法律概念。"""


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
    """把口语化问题改写成法律检索关键词（仅用于检索，不用于生成回答）。"""
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
    return resp.choices[0].message.content.strip()
