# -*- coding: utf-8 -*-
"""第 11 题（没交社保能否解除）召回对照测试：统计 38 条召回次数 + 记录检索词。"""

import os
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent.parent
ROOT = EVAL_DIR.parents[1]
RESULTS = EVAL_DIR / "results"
sys.path[:0] = [str(ROOT), str(EVAL_DIR)]
os.chdir(ROOT)  # 数据路径按项目根目录解析
import sys
import json

sys.stdout.reconfigure(encoding="utf-8")

import config  # noqa: F401
import lawmeta
import llm
from retriever import BM25, _tokenize

laws = json.load(open("data/laws.json", encoding="utf-8"))
law_docs = [f"{l.get('law', '')} 第{l.get('article', '')}条 {l.get('text', '')}" for l in laws]
law_bm25 = BM25([_tokenize(t) for t in law_docs])


def _top(scores, k):
    return sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]


def main():
    q = "公司没给员工交社保，员工能解除合同吗？"
    for trial in range(5):
        rw = llm.rewrite_query(q, config.DEEPSEEK_API_KEY)
        keywords = rw.get("keywords") or q
        top5 = _top(law_bm25.scores(_tokenize(keywords)), 5)
        has38 = any(
            laws[i]["law"] == "中华人民共和国劳动合同法" and lawmeta.cn_to_arabic(laws[i]["article"]) == 38
            for i in top5
        )
        print(f"第{trial + 1}次: keywords={keywords!r} | 38条召回={has38}")


if __name__ == "__main__":
    main()
