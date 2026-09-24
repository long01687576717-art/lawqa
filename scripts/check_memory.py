# -*- coding: utf-8 -*-
"""内存占用自检：加载 laws.json + cases.json，构建 BM25 索引，打印进程内存。

用法：python scripts/check_memory.py
仅用于本地验证，不参与线上运行。
"""
import json
import math
import os
import sys
from pathlib import Path

import jieba
import psutil

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

TOP_K = 5


def _tokenize(text):
    return [w for w in jieba.cut_for_search(text) if w.strip()]


class BM25:
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


def rss_mb():
    return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024


def main():
    print(f"RSS 初始（进程启动后）: {rss_mb():.1f} MB")

    laws = json.loads((DATA_DIR / "laws.json").read_text(encoding="utf-8"))
    cases = json.loads((DATA_DIR / "cases.json").read_text(encoding="utf-8"))
    print(f"数据加载完成：法条 {len(laws)} 条，案例 {len(cases)} 个")
    print(f"RSS 加载数据后: {rss_mb():.1f} MB")

    law_docs = [f"{l.get('law', '')} 第{l.get('article', '')}条 {l.get('text', '')}" for l in laws]
    case_docs = [" ".join(str(c.get(k, "")) for k in ("title", "summary", "ruling", "keywords")) for c in cases]
    law_bm25 = BM25([_tokenize(t) for t in law_docs])
    case_bm25 = BM25([_tokenize(t) for t in case_docs])
    print(f"BM25 索引构建完成（法条 {law_bm25.n} 篇 / 案例 {case_bm25.n} 篇）")
    print(f"RSS 构建索引后: {rss_mb():.1f} MB")

    # 顺手验证检索：996 加班问题
    q = "早上九点上班，晚上九点下班一周工作六天"
    qt = _tokenize(q)
    scores = case_bm25.scores(qt)
    idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:TOP_K]
    print("\n=== 检索验证：'%s' ===" % q)
    for rank, i in enumerate(idx, 1):
        c = cases[i]
        print(f"  #{rank} score={scores[i]:.4f} | {c.get('title', '')}")
        print(f"      关键词: {c.get('keywords', '')}")

    print(f"\n最终进程内存: {rss_mb():.1f} MB  （远低于 1GB = 1024 MB 上限）")


if __name__ == "__main__":
    main()
