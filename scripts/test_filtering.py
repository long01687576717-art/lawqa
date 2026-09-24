# -*- coding: utf-8 -*-
"""场景标签过滤测试：验证「宁可没有案例，也不能乱匹配案例」。

用法：python scripts/test_filtering.py
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jieba
from config import DEEPSEEK_API_KEY
from llm import rewrite_query

BASE = Path(__file__).resolve().parent.parent
MAX_CASES = 3
MIN_CASE_SCORE = 0.8


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


def _top_cases(scores, cases, scenario, k, min_score):
    """场景过滤 → 得分排序取前 k → 最高分低于阈值返回空。"""
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


def run(question, cases, case_bm25):
    rw = rewrite_query(question, DEEPSEEK_API_KEY)
    scenario = rw.get("scenario")
    keywords = rw.get("keywords") or question

    scores = case_bm25.scores(_tokenize(keywords))
    idx = _top_cases(scores, cases, scenario, MAX_CASES, MIN_CASE_SCORE)

    print("=" * 60)
    print("用户问题：", question)
    print("改写场景：", scenario)
    print("改写关键词：", keywords)
    print("命中案例数：", len(idx))
    for i in idx:
        print(f"   - {cases[i].get('title')}  [场景:{cases[i].get('scenario')}]")
    return len(idx)


def main():
    cases = json.loads((BASE / "data" / "cases.json").read_text(encoding="utf-8"))
    case_docs = [" ".join(str(c.get(k, "")) for k in ("title", "summary", "ruling", "keywords")) for c in cases]
    case_bm25 = BM25([_tokenize(t) for t in case_docs])

    run("老板逼我们996", cases, case_bm25)
    run("公司没交社保怎么办", cases, case_bm25)


if __name__ == "__main__":
    main()
