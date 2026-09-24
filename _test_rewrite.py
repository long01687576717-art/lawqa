# -*- coding: utf-8 -*-
"""本地测试：rewrite_query 改写 + BM25 检索，直接打印结果。"""
import json
import math
from pathlib import Path

import jieba
from llm import rewrite_query

BASE = Path(__file__).resolve().parent

# 读 key（仅本地测试用）
key = ""
for line in (BASE / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line.startswith("DEEPSEEK_API_KEY") and "=" in line:
        key = line.split("=", 1)[1].strip().strip('"').strip("'")
        break

QUESTION = "老板强制996，不干就走人怎么办"


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

    def scores(self, q):
        s = [0.0] * self.n
        for t in q:
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


def tok(t):
    return [w for w in jieba.cut_for_search(t) if w.strip()]


cases = json.loads((BASE / "data" / "cases.json").read_text(encoding="utf-8"))
case_docs = [" ".join(str(c.get(k, "")) for k in ("title", "summary", "ruling", "keywords")) for c in cases]
case_bm25 = BM25([tok(t) for t in case_docs])

rewritten = rewrite_query(QUESTION, key)

q = tok(rewritten)
scores = case_bm25.scores(q)
idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:3]

print("1. 用户原始口语化问题：", QUESTION)
print("2. 改写后的专业法律检索词：", rewritten)
print("3. 最终检索返回的相似案例（前3）：")
for i in idx:
    print("   -", cases[i].get("title", ""))
