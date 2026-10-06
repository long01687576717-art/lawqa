"""知识库检索：加载法条/案例数据，向量 + BM25 混合检索。"""
import json
import math
from pathlib import Path

import jieba
import numpy as np

import case_tags
import lawmeta

DATA_DIR = Path(__file__).resolve().parent / "data"
EMBED_MODEL_NAME = "BAAI/bge-small-zh-v1.5"


def _tokenize(text: str):
    # cut_for_search 会把复合词再切成细粒度，提升关键词召回（如「拖欠工资」→ 拖欠/工资）
    return [w for w in jieba.cut_for_search(text) if w.strip()]


class BM25:
    """轻量 BM25 实现，向量不可用时作为兜底检索。"""

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
        self.avgdl = (sum(self.doc_len) / self.n) if self.n else 0
        self.k1 = 1.5
        self.b = 0.75

    def scores(self, query_tokens):
        if self.n == 0:
            return np.zeros(0)
        s = np.zeros(self.n)
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


class KnowledgeBase:
    """法条 + 案例知识库，提供 search() 做混合检索。"""

    def __init__(self):
        self.laws = self._load("laws.json")
        self.cases = self._load("cases.json")
        self.citation_index = lawmeta.load_citation_index()
        self.law_mapping = lawmeta.load_law_mapping()
        self.laws = lawmeta.attach_notes(self.laws)

        self.law_docs = [self._law_text(l) for l in self.laws]
        self.case_docs = [self._case_text(c) for c in self.cases]

        self.law_bm25 = BM25([_tokenize(t) for t in self.law_docs])
        # 分层检索：核心法律（劳动法、劳动合同法）与配套法规分开排名，避免配套条文挤占核心条文
        is_core = np.array([l.get("law") in lawmeta.CORE_LAWS for l in self.laws])
        self.core_idx = np.where(is_core)[0]
        self.other_idx = np.where(~is_core)[0]
        self.case_bm25 = BM25([_tokenize(t) for t in self.case_docs])
        self.case_idf = case_tags.tag_idf(self.cases)
        self.case_title_bm25 = BM25([_tokenize(c.get("title", "")) for c in self.cases])

        self.embedder = None
        self.law_vecs = None
        self.case_vecs = None
        self._init_embedder()

    # ---- 数据加载 ----
    @staticmethod
    def _load(name):
        p = DATA_DIR / name
        if not p.exists():
            print(f"[warn] 未找到数据文件 {p}")
            return []
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _law_text(law):
        return f"{law.get('law', '')} 第{law.get('article', '')}条 {law.get('text', '')}"

    @staticmethod
    def _case_text(c):
        return case_tags.case_doc_text(c)

    # ---- 向量 ----
    def _init_embedder(self):
        try:
            from fastembed import TextEmbedding

            print("[提示] 首次运行正在下载中文向量模型（约100MB，仅一次），请稍候……")
            self.embedder = TextEmbedding(model_name=EMBED_MODEL_NAME)
            self.law_vecs = self._embed(self.law_docs)
            self.case_vecs = self._embed(self.case_docs)
            print(f"[ok] 向量模型已加载：法条 {len(self.law_docs)} 条 / 案例 {len(self.case_docs)} 个")
        except Exception as e:
            self.embedder = None
            print(f"[warn] 向量模型不可用，已降级为关键词检索（原因：{e}）")

    def _embed(self, texts):
        if not texts:
            return np.zeros((0, 0), dtype="float32")
        vecs = np.array(list(self.embedder.embed(texts)), dtype="float32")
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vecs / norms

    def _vector_scores(self, query, vecs):
        if self.embedder is None or vecs is None or vecs.shape[0] == 0:
            return None
        qv = self._embed([query])
        return (vecs @ qv.T).ravel()

    # ---- 检索 ----
    RRF_K = 60   # Reciprocal Rank Fusion 平滑参数
    K_OTHER = 4  # 配套法规（核心法律以外）每次取的条数
    ORAL_SCOPE = "core"  # 口语扩展路的检索范围：core 只查核心法律，all 查全部
    ORAL_OTHER = 2       # 口语扩展路另取的配套法规条数（与核心法律分开排名，0 表示不取）

    def _rrf_fuse(self, *score_arrays, top_n=30, k=5, subset=None):
        """RRF 融合：把多个检索方法的排序结果合并成单一排名。

        每个方法取前 top_n 名，第 rank 名（从 1 开始）贡献 1/(K+rank) 分，
        累加到对应文档，最终按总分降序取前 k 名。subset 给定时只在这些下标内排名。
        """
        rrf = {}
        for scores in score_arrays:
            if scores is None or len(scores) == 0:
                continue
            if subset is None:
                order = np.argsort(-scores)[:top_n]
            else:
                order = subset[np.argsort(-scores[subset])][:top_n]
            for rank, idx in enumerate(order):
                rrf[idx] = rrf.get(idx, 0.0) + 1.0 / (self.RRF_K + rank + 1)
        if not rrf:
            return []
        return [i for i, _ in sorted(rrf.items(), key=lambda kv: kv[1], reverse=True)[:k]]

    def search(self, query, scenario=None, k=5, extra_query=None):
        """返回 (laws, cases)。法条取 RRF top-k（+ 口语扩展路合并 + 关联条文）；案例按方向标签筛选 + BM25 排序 + 阈值淘汰。"""
        q = _tokenize(query)
        bm25_q, vec_q = self.law_bm25.scores(q), self._vector_scores(query, self.law_vecs)
        law_idx = self._rrf_fuse(bm25_q, vec_q, k=k, subset=self.core_idx)
        law_idx += self._rrf_fuse(bm25_q, vec_q, k=self.K_OTHER, subset=self.other_idx)
        laws = [self.laws[i] for i in law_idx]

        # 口语扩展路：独立检索，去重合并（避免稀释主检索词）
        if extra_query and extra_query != query:
            eq = _tokenize(extra_query)
            extra_idx = self._rrf_fuse(
                self.law_bm25.scores(eq),
                self._vector_scores(extra_query, self.law_vecs),
                k=k,
                subset=self.core_idx if self.ORAL_SCOPE == "core" else None,
            )
            laws = lawmeta.merge_two_routes(laws, [self.laws[i] for i in extra_idx])
            if self.ORAL_OTHER:  # 口语词换算出的配套法规术语（如「孕检→妊娠测试」）单独排名补充
                other = self._rrf_fuse(self.law_bm25.scores(eq), self._vector_scores(extra_query, self.law_vecs),
                                       k=self.ORAL_OTHER, subset=self.other_idx)
                laws = lawmeta.merge_two_routes(laws, [self.laws[i] for i in other], max_extra=self.ORAL_OTHER)

        # 案例：用「改写词 + 原问题口语扩展」识别方向标签并打分（改写为「无」时也能靠标签找到案例）
        case_query = f"{query} {extra_query or ''}".strip()
        case_idx = case_tags.select_cases(
            self.cases, self.case_bm25.scores(_tokenize(case_query)), case_query, scenario, idf=self.case_idf,
            title_scores=self.case_title_bm25.scores(_tokenize(case_query)),
        )
        # 关联条文联动召回：把引用 / 被引用的条文一并带出（不挤占原 top-k）
        laws = lawmeta.expand_with_citations(laws, self.laws, self.citation_index, self.law_mapping)
        return laws, [self.cases[i] for i in case_idx]
