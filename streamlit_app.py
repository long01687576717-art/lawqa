# force rebuild: 2026-09-24
# -*- coding: utf-8 -*-
"""劳动法知识库问答 —— Streamlit 版（BYOK + 轻量 BM25 检索）。

适配 Streamlit Community Cloud（免费版 1GB 内存）：
不使用 fastembed 本地向量模型，仅用 jieba 分词 + BM25 关键词检索。
"""
import json
import math
import re
from pathlib import Path

import jieba
import streamlit as st
from openai import OpenAI

import case_tags
import lawmeta
from llm import rewrite_query

# ---- 常量 ----
BASE_DIR = Path(__file__).resolve().parent          # 关键：用绝对路径定位数据目录
DATA_DIR = BASE_DIR / "data"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
TOP_K = 5
K_OTHER = 4  # 配套法规（核心法律以外）每次取的条数，与 retriever.KnowledgeBase.K_OTHER 一致

_CSS = """<style>
/* ===== 全局：LegalTech 浅色主题（深灰蓝，非纯黑） ===== */
.stApp {
    background:
        radial-gradient(1100px 520px at 12% -8%, rgba(30, 58, 138, 0.06) 0%, transparent 60%),
        radial-gradient(900px 420px at 100% 0%, rgba(212, 175, 55, 0.05) 0%, transparent 55%),
        linear-gradient(180deg, #F8FAFC 0%, #EEF2F7 100%);
}
html, body, .stApp {
    font-family: "Segoe UI", "Microsoft YaHei", system-ui, -apple-system, sans-serif;
    color: #1f2937;
}
header[data-testid="stHeader"] { background: transparent; height: 2.6rem; }
.block-container { padding-top: 1.4rem; padding-bottom: 3rem; max-width: 920px; }

/* ===== 标题（深蓝主色） ===== */
.app-title {
    font-size: 2.35rem;
    font-weight: 800;
    letter-spacing: 2px;
    line-height: 1.2;
    color: #1E3A8A;
}
.app-subtitle { color: #64748b; font-size: 0.95rem; letter-spacing: 3px; margin-top: 0.25rem; }
.gold-line {
    height: 2px;
    border: none;
    margin: 0.8rem 0 1.1rem 0;
    background: linear-gradient(90deg, #D4AF37 0%, #1E3A8A 55%, rgba(30, 58, 138, 0) 100%);
}

/* ===== 侧边栏 ===== */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #FFFFFF 0%, #F1F5F9 100%);
    border-right: 1px solid #E2E8F0;
}
.sidebar-header { font-size: 1.2rem; font-weight: 700; color: #1E3A8A; letter-spacing: 1px; margin-bottom: 0.3rem; }
section[data-testid="stSidebar"] [data-testid="stTextInput"] input {
    background: #FFFFFF !important;
    border: 1px solid #CBD5E1 !important;
    border-radius: 10px !important;
    color: #1f2937 !important;
    padding: 0.6rem 0.8rem !important;
}
section[data-testid="stSidebar"] [data-testid="stTextInput"] input:focus {
    border-color: #1E3A8A !important;
    box-shadow: 0 0 0 2px rgba(30, 58, 138, 0.12) !important;
}
.sidebar-hint {
    color: #64748b;
    font-size: 0.82rem;
    line-height: 1.7;
    border-left: 2px solid #D4AF37;
    padding-left: 0.6rem;
    margin-top: 0.5rem;
}

/* ===== 聊天气泡（用户/AI 区分明显，柔和阴影 + 圆角） ===== */
[data-testid="stChatMessage"] {
    border-radius: 16px;
    padding: 12px 16px;
    margin: 0.5rem 0;
    box-shadow: 0 4px 14px rgba(15, 23, 42, 0.08);
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-left: 3px solid #1E3A8A;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    background: #E3ECF9;
    border: 1px solid #C7D9F2;
    border-right: 3px solid #3B82F6;
}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] { color: #1f2937; }

/* ===== 展开器（参考法条/相似案例） ===== */
[data-testid="stExpander"] {
    background: rgba(255, 255, 255, 0.6);
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    margin-top: 0.4rem;
}

/* ===== 底部输入框（圆角 + 聚焦变色） ===== */
[data-testid="stChatInput"] { border-radius: 22px; }
[data-testid="stChatInput"] textarea {
    background: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 20px;
    color: #1f2937;
    padding: 0.85rem 1rem;
    line-height: 1.6;
}
[data-testid="stChatInput"] textarea:focus {
    border-color: #1E3A8A;
    box-shadow: 0 0 0 2px rgba(30, 58, 138, 0.12);
}

/* ===== 主按钮（深蓝） ===== */
button[data-testid="stBaseButton-primary"] {
    background-color: #1E3A8A !important;
    border-color: #1E3A8A !important;
    color: #FFFFFF !important;
}
button[data-testid="stBaseButton-primary"]:hover {
    background-color: #1E40AF !important;
    border-color: #1E40AF !important;
    color: #FFFFFF !important;
}
</style>"""

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

# ---- 分词 + BM25（纯 Python，无 numpy / fastembed 依赖）----
def _tokenize(text):
    return [w for w in jieba.cut_for_search(text) if w.strip()]


class BM25:
    """轻量 BM25，参考 retriever.py 中同名实现，改写为纯 Python。"""

    def __init__(self, docs):
        self.docs = docs
        self.n = len(docs)
        self.df = {}
        self.doc_len = []
        for d in docs:
            tf = {}
            for t in d:
                tf[t] = tf.get(t, 0) + 1
            for t in tf:
                self.df[t] = self.df.get(t, 0) + 1
            self.doc_len.append(len(d))
        self.avgdl = (sum(self.doc_len) / self.n) if self.n else 0.0
        self.k1 = 1.5
        self.b = 0.75

    def scores(self, query_tokens):
        s = [0.0] * self.n
        for t in query_tokens:
            if t not in self.df:
                continue
            idf = math.log((self.n - self.df[t] + 0.5) / (self.df[t] + 0.5) + 1.0)
            for i, d in enumerate(self.docs):
                tf = d.count(t)
                if tf == 0:
                    continue
                denom = tf + self.k1 * (1 - self.b + self.b * self.doc_len[i] / self.avgdl)
                s[i] += idf * (tf * (self.k1 + 1)) / denom
        return s


# ---- 数据加载（缓存）----
@st.cache_data(show_spinner=False)
def _load_json(name):
    p = DATA_DIR / name
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        return json.load(f)


@st.cache_resource(show_spinner=False)
def build_index():
    laws = _load_json("laws.json")
    cases = _load_json("cases.json")
    citation_index = lawmeta.load_citation_index()
    law_mapping = lawmeta.load_law_mapping()
    laws = lawmeta.attach_notes(laws)
    law_docs = [f"{l.get('law', '')} 第{l.get('article', '')}条 {l.get('text', '')}" for l in laws]
    case_docs = [case_tags.case_doc_text(c) for c in cases]
    law_bm25 = BM25([_tokenize(t) for t in law_docs])
    case_bm25 = BM25([_tokenize(t) for t in case_docs])
    case_idf = case_tags.tag_idf(cases)
    case_title_bm25 = BM25([_tokenize(c.get("title", "")) for c in cases])
    return laws, cases, law_bm25, case_bm25, citation_index, law_mapping, case_idf, case_title_bm25


def search(query, laws, cases, law_bm25, case_bm25, citation_index=None, law_mapping=None, scenario=None, k=TOP_K, extra_query=None, case_idf=None, case_title_bm25=None):
    q = _tokenize(query)
    # 分层检索：核心法律（劳动法、劳动合同法）与配套法规分开排名，避免配套条文挤占核心条文
    core = [i for i, l in enumerate(laws) if lawmeta.is_core(l.get("law", ""))]
    other = [i for i, l in enumerate(laws) if not lawmeta.is_core(l.get("law", ""))]
    scores = law_bm25.scores(q)
    law_idx = _top(scores, k, core) + _top(scores, K_OTHER, other)
    result_laws = [laws[i] for i in law_idx]
    # 口语扩展路：独立检索（只查核心法律），去重合并（避免稀释主检索词）
    if extra_query and extra_query != query:
        eq = _tokenize(extra_query)
        extra_idx = _top(law_bm25.scores(eq), k, core)
        result_laws = lawmeta.merge_two_routes(result_laws, [laws[i] for i in extra_idx])
    # 案例：用「改写词 + 原问题口语扩展」识别方向标签并打分（改写为「无」时也能靠标签找到案例）
    case_query = f"{query} {extra_query or ''}".strip()
    cq = _tokenize(case_query)
    case_idx = case_tags.select_cases(cases, case_bm25.scores(cq), case_query, scenario, idf=case_idf,
                                      title_scores=case_title_bm25.scores(cq) if case_title_bm25 else None)
    # 关联条文联动召回：把引用 / 被引用的条文一并带出（不挤占原 top-k）
    result_laws = lawmeta.expand_with_citations(result_laws, laws, citation_index, law_mapping)
    return result_laws, [cases[i] for i in case_idx]


def _top(scores, k, subset=None):
    if not scores:
        return []
    cand = range(len(scores)) if subset is None else subset
    return sorted(cand, key=lambda i: scores[i], reverse=True)[:k]


# ---- DeepSeek ----
def _build_prompt(question, laws, cases):
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
            parts.append(case_tags.case_brief(i, c))
    else:
        parts.append("（无）")
    return "\n".join(parts)


def _generate(client, question, laws, cases):
    resp = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_prompt(question, laws, cases)},
        ],
        temperature=0.3,
        stream=False,
    )
    return resp.choices[0].message.content.strip()


# ---- 界面 ----
CITE_RE = re.compile(r"《([^》]{2,40})》第([零一二三四五六七八九十百\d]+)条")


def _short(name):
    return name.replace("中华人民共和国", "", 1)


def _art_num(art):
    return int(art) if art.isdigit() else lawmeta.cn_to_arabic(art)


def _citations(answer):
    """回答中「《法规名》第X条」形式的引用，返回 {(法规简称, 条号数字)}。"""
    return {(_short(m.group(1)), _art_num(m.group(2))) for m in CITE_RE.finditer(answer or "")}


def _is_cited(law, cites):
    """按法规名 + 条号精确判断法条是否被回答引用。"""
    return (_short(law.get("law", "")), _art_num(law.get("article", ""))) in cites


def _law_md(l):
    """法条展示：名称 + 层级 + 条号，条文按款换行（Markdown 需行尾两个空格才换行）。"""
    level = f"（{l['level']}）" if l.get("level") else ""
    text = l.get("text", "").replace("\n", "  \n")
    return f"**《{l.get('law', '')}》{level}第{l.get('article', '')}条**  \n{text}"


def _render_refs(laws, cases, answer=None):
    if answer and "只专注于劳动法" in answer:
        return  # 拒答时不展示法条和案例
    # 只展示回答中引用的法条，未引用的检索结果不展示
    cites = _citations(answer)
    cited = [l for l in (laws or []) if _is_cited(l, cites)] if answer else (laws or [])
    if cited:
        with st.expander("📖 参考法条"):
            for l in cited:
                st.markdown(_law_md(l))
    # 渲染"相似案例"前先检查长度：为 0 时彻底隐藏标题，不硬凑
    if cases:
        with st.expander("⚖️ 相似案例"):
            for c in cases:
                st.markdown(f"**{c.get('title', '')}**")
                if c.get("case_no"):
                    meta = c["case_no"] + ((" · " + c["court"]) if c.get("court") else "")
                    st.caption(meta)
                if c.get("tags"):
                    st.caption("方向：" + " · ".join(c["tags"]))
                if c.get("ruling"):
                    label = "裁判要点" if c.get("gist") else ("裁判结果" if c.get("result") else "法院意见")
                    st.markdown(f"{label}：{c.get('ruling', '')}")
                if c.get("source"):
                    st.caption(f"来源：{c['source']}")


st.set_page_config(page_title="劳动法知识库问答", page_icon="⚖️", layout="centered")

# 注入自定义 CSS
st.markdown(_CSS, unsafe_allow_html=True)

# 标题
st.markdown(
    '<div class="app-title">⚖️ 劳动法知识库问答</div>'
    '<div class="app-subtitle">劳动法 · 案例 · 智能检索</div>'
    '<div class="gold-line"></div>',
    unsafe_allow_html=True,
)

# 侧边栏：API Key（BYOK，只存会话内存）
with st.sidebar:
    st.markdown('<div class="sidebar-header">⚖️ 法律知识库</div>', unsafe_allow_html=True)
    st.text_input(
        "🔑 DeepSeek API 密钥",
        type="password",
        key="api_key",
        help="你的 Key 只保存在本次会话内存中，不会上传或存储。",
    )
    st.markdown(
        '<div class="sidebar-hint">🔐 你的密钥仅保存在本次会话，不会被上传或存储。<br>'
        '还没有？到 platform.deepseek.com 免费申请。</div>',
        unsafe_allow_html=True,
    )
    st.caption("本工具仅供学习参考，不构成法律意见。")

api_key = (st.session_state.get("api_key") or "").strip()
if not api_key:
    st.warning("请先在侧边栏配置 DeepSeek API Key")
    st.stop()

# 加载索引（缓存）
laws, cases, law_bm25, case_bm25, citation_index, law_mapping, case_idf, case_title_bm25 = build_index()

# 聊天历史
if "messages" not in st.session_state:
    st.session_state.messages = []

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        if m["role"] == "assistant" and m.get("rewritten"):
            st.caption(f"🔍 已自动为您提取检索词：{m['rewritten']}")
        st.markdown(m["content"])
        if m["role"] == "assistant":
            _render_refs(m.get("laws"), m.get("cases"), m.get("content"))

prompt = st.chat_input("输入你的劳动法问题…")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            with st.spinner("检索并生成回答中…"):
                client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
                try:
                    rw = rewrite_query(prompt, api_key)
                    scenario = rw.get("scenario")
                    keywords = rw.get("keywords") or prompt
                    oral_query = rw.get("oral_query") or ""
                except Exception:
                    scenario, keywords, oral_query = None, prompt, ""  # 改写失败则用原问题检索
                r_laws, r_cases = search(keywords, laws, cases, law_bm25, case_bm25, citation_index, law_mapping, scenario=scenario, extra_query=oral_query, case_idf=case_idf, case_title_bm25=case_title_bm25)
                answer = _generate(client, prompt, r_laws, r_cases)
                # 改进3：若模型判断资料不足，扩大召回（k=15）二次检索再生成
                if "资料不足" in answer:
                    r_laws2, r_cases2 = search(keywords, laws, cases, law_bm25, case_bm25, citation_index, law_mapping, scenario=scenario, k=15, extra_query=oral_query, case_idf=case_idf, case_title_bm25=case_title_bm25)
                    answer = _generate(client, prompt, r_laws2, r_cases2)
                    r_laws, r_cases = r_laws2, r_cases2
            shown_keywords = keywords
            if scenario == "无" and oral_query:
                shown_keywords = oral_query
            st.caption(f"🔍 已自动为您提取检索词：{shown_keywords}")
            st.markdown(answer)
            _render_refs(r_laws, r_cases, answer)
            st.session_state.messages.append(
                {"role": "assistant", "content": answer, "laws": r_laws, "cases": r_cases, "rewritten": keywords}
            )
        except Exception as e:
            st.error(f"调用失败：{e}")
