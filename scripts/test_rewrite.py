# -*- coding: utf-8 -*-
"""独立测试脚本：模拟用户提问，展示「原始问题 → 改写检索词 → 检索命中案例」。

用法：python scripts/test_rewrite.py
"""
import json
import math
import sys
from pathlib import Path

# 让脚本能 import 项目根目录的 config.py / llm.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jieba
from config import DEEPSEEK_API_KEY
from llm import rewrite_query

BASE = Path(__file__).resolve().parent.parent
QUESTION = "老板逼我们996，说不干就滚蛋"
MAX_CASES = 3          # 案例最多返回条数（硬性 [:3]）
MIN_CASE_SCORE = 0.5   # 案例最低相关度阈值


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


def _tokenize(text):
    return [w for w in jieba.cut_for_search(text) if w.strip()]


def _top_cases(scores, k, min_score):
    idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    return [i for i in idx if scores[i] >= min_score]


def main():
    cases = json.loads((BASE / "data" / "cases.json").read_text(encoding="utf-8"))
    case_docs = [" ".join(str(c.get(k, "")) for k in ("title", "summary", "ruling", "keywords")) for c in cases]
    case_bm25 = BM25([_tokenize(t) for t in case_docs])

    # 1. 原始问题
    print("1. 原始问题：", QUESTION)

    # 2. 改写
    rewritten = rewrite_query(QUESTION, DEEPSEEK_API_KEY)
    print("2. 改写后的专业法律检索词：", rewritten)

    # 3. 检索命中案例（排序 → [:MAX_CASES] → 阈值过滤）
    scores = case_bm25.scores(_tokenize(rewritten))
    idx = _top_cases(scores, MAX_CASES, MIN_CASE_SCORE)
    print(f"3. 最终检索命中的案例（共 {len(idx)} 个）：")
    for i in idx:
        print(f"   - {cases[i].get('title', '')}")


if __name__ == "__main__":
    main()
