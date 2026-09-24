# force rebuild: 2026-09-24
# -*- coding: utf-8 -*-
"""劳动法知识库问答 —— Streamlit 版（BYOK + 轻量 BM25 检索）。

适配 Streamlit Community Cloud（免费版 1GB 内存）：
不使用 fastembed 本地向量模型，仅用 jieba 分词 + BM25 关键词检索。
"""
import json
import math
from pathlib import Path

import jieba
import streamlit as st
from openai import OpenAI

from llm import rewrite_query

# ---- 常量 ----
BASE_DIR = Path(__file__).resolve().parent          # 关键：用绝对路径定位数据目录
DATA_DIR = BASE_DIR / "data"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
TOP_K = 5
MAX_CASES = 3          # 案例最多返回条数（硬性 [:3]）
MIN_CASE_SCORE = 0.8   # 案例最低相关度阈值：最高分低于此值说明该场景下无合适案例

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

SYSTEM_PROMPT = """你是一个专业的中国劳动法助手。你只能根据提供的参考资料回答关于劳动法、劳动合同、劳动争议、女职工保护、工资、加班等劳动法领域的问题。如果用户问的问题与劳动法完全无关（例如：如何做菜、写代码、股票推荐、天气、非劳动纠纷的刑事或民事问题），你必须礼貌拒绝回答，并提示用户：「抱歉，我目前只专注于劳动法相关的咨询，无法回答其他领域的问题。」严禁使用你自己的预训练通用知识去回答法律之外的问题。

回答劳动法问题时，遵循以下要求：
1. 只依据【参考资料】中给出的法条和案例作答，严禁编造法条序号、条文内容或案号。
2. 引用法条时写清楚法律名称和第几条；引用案例时写清楚案例名称。
3. 若参考资料不足以回答，请如实说明「资料不足」，不要强行给出结论。
4. 语言专业、简洁、通俗，用中文，适当分点，不要输出与问题无关的内容。
5. 最后加一句：本回答仅供参考，不构成法律意见。
6. 如果在参考资料中，案例的案由与用户提问的核心场景不符（例如用户问996，却给出了试用期案例），严禁在回答中引用该案例，直接忽略它。
7. 如果【参考案例】为空或没有与问题场景高度相关的案例，请在回答中明确写出「本案参考资料中暂无高度相关的案例」，不要强行引用不相关的案例。"""

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
    law_docs = [f"{l.get('law', '')} 第{l.get('article', '')}条 {l.get('text', '')}" for l in laws]
    case_docs = [" ".join(str(c.get(k, "")) for k in ("title", "summary", "ruling", "keywords")) for c in cases]
    law_bm25 = BM25([_tokenize(t) for t in law_docs])
    case_bm25 = BM25([_tokenize(t) for t in case_docs])
    return laws, cases, law_bm25, case_bm25


def search(query, laws, cases, law_bm25, case_bm25, scenario=None, k=TOP_K):
    q = _tokenize(query)
    law_idx = _top(law_bm25.scores(q), k)
    if scenario == "无":
        case_idx = []
    else:
        # 场景过滤 → 得分排序 → [:MAX_CASES] → 最高分低于阈值则返回空
        case_idx = _top_cases(case_bm25.scores(q), cases, scenario, MAX_CASES, MIN_CASE_SCORE)
    return [laws[i] for i in law_idx], [cases[i] for i in case_idx]


def _top(scores, k):
    if not scores:
        return []
    return sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]


def _top_cases(scores, cases, scenario, k, min_score):
    if not scores:
        return []
    if scenario:
        cand = [i for i in range(len(cases)) if cases[i].get("scenario") == scenario]
    else:
        cand = list(range(len(cases)))
    if not cand:
        return []
    cand_sorted = sorted(cand, key=lambda i: scores[i], reverse=True)[:k]
    if scores[cand_sorted[0]] < min_score:
        return []
    return cand_sorted


# ---- DeepSeek ----
def _build_prompt(question, laws, cases):
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
def _render_refs(laws, cases):
    if laws:
        with st.expander("📖 参考法条"):
            for l in laws:
                st.markdown(f"**《{l.get('law', '')}》第{l.get('article', '')}条**  \n{l.get('text', '')}")
    # 渲染"相似案例"前先检查长度：为 0 时彻底隐藏标题，不硬凑
    if cases:
        with st.expander("⚖️ 相似案例"):
            for c in cases:
                st.markdown(f"**{c.get('title', '')}**")
                if c.get("case_no"):
                    meta = c["case_no"] + ((" · " + c["court"]) if c.get("court") else "")
                    st.caption(meta)
                if c.get("ruling"):
                    st.markdown(f"裁判要点：{c.get('ruling', '')}")


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
laws, cases, law_bm25, case_bm25 = build_index()

# 聊天历史
if "messages" not in st.session_state:
    st.session_state.messages = []

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        if m["role"] == "assistant" and m.get("rewritten"):
            st.caption(f"🔍 已自动为您提取检索词：{m['rewritten']}")
        st.markdown(m["content"])
        if m["role"] == "assistant":
            _render_refs(m.get("laws"), m.get("cases"))

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
                except Exception:
                    scenario, keywords = None, prompt  # 改写失败则用原问题检索
                r_laws, r_cases = search(keywords, laws, cases, law_bm25, case_bm25, scenario=scenario)
                answer = _generate(client, prompt, r_laws, r_cases)
            st.caption(f"🔍 已自动为您提取检索词：{keywords}")
            st.markdown(answer)
            _render_refs(r_laws, r_cases)
            st.session_state.messages.append(
                {"role": "assistant", "content": answer, "laws": r_laws, "cases": r_cases, "rewritten": keywords}
            )
        except Exception as e:
            st.error(f"调用失败：{e}")
