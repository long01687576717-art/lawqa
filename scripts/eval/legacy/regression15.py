# -*- coding: utf-8 -*-
"""新 15 题回归脚本（与 _regression.py 同逻辑，仅换测试集与输出文件）。"""

import os
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent.parent
ROOT = EVAL_DIR.parents[1]
RESULTS = EVAL_DIR / "results"
sys.path[:0] = [str(ROOT), str(EVAL_DIR)]
os.chdir(ROOT)  # 数据路径按项目根目录解析
import csv
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import config  # noqa: F401
import lawmeta
import llm
from retriever import KnowledgeBase, BM25, _tokenize

from testset import QUESTIONS_15, TARGETS_15

BASE = ROOT
OUT = RESULTS / "regression15_v2_result.csv"
K = 5
MAX_CASES = 3
MIN_CASE_SCORE = 0.8


def law_matches(target_law, actual_law):
    if target_law == "劳动合同法":
        return "劳动合同法" in actual_law
    if target_law == "劳动法":
        return actual_law == "中华人民共和国劳动法"
    return target_law in actual_law


def check_recall(targets, laws):
    if not targets:
        return "-"
    art = [(l.get("law", ""), lawmeta.cn_to_arabic(l.get("article", ""))) for l in laws]
    hit = 0
    for tlaw, tno in targets:
        if any(law_matches(tlaw, a) and n == tno for a, n in art):
            hit += 1
    return f"{hit}/{len(targets)}"


def fmt_laws(ls):
    return "; ".join(
        f"{l.get('law', '').replace('中华人民共和国', '')}第{lawmeta.cn_to_arabic(l.get('article', ''))}条"
        + ("(关联)" if l.get("_cited") else "")
        + ("(口)" if l.get("_oral") else "")
        for l in ls)


def _top(scores, k):
    return sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]


def _top_cases(scores, scenario, k, min_score):
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


def online_search(query, scenario, k=K, extra_query=None):
    q = _tokenize(query)
    law_idx = _top(law_bm25.scores(q), k)
    result = [laws[i] for i in law_idx]
    if extra_query and extra_query != query:
        eq = _tokenize(extra_query)
        extra_idx = _top(law_bm25.scores(eq), k)
        result = lawmeta.merge_two_routes(result, [laws[i] for i in extra_idx])
    if scenario == "无":
        case_idx = []
    else:
        case_idx = _top_cases(case_bm25.scores(q), scenario, MAX_CASES, MIN_CASE_SCORE)
    result = lawmeta.expand_with_citations(result, laws, citation_index)
    return result, [cases[i] for i in case_idx]


def main():
    global laws, cases, law_bm25, case_bm25, citation_index
    print("加载知识库...", flush=True)
    kb = KnowledgeBase()
    laws = kb.laws
    cases = kb.cases
    citation_index = kb.citation_index
    law_docs = [f"{l.get('law', '')} 第{l.get('article', '')}条 {l.get('text', '')}" for l in laws]
    case_docs = [" ".join(str(c.get(k, "")) for k in ("title", "summary", "ruling", "keywords")) for c in cases]
    law_bm25 = BM25([_tokenize(t) for t in law_docs])
    case_bm25 = BM25([_tokenize(t) for t in case_docs])

    api_key = config.DEEPSEEK_API_KEY
    rows = []

    for i, (q, targets) in enumerate(zip(QUESTIONS_15, TARGETS_15), 1):
        try:
            rw = llm.rewrite_query(q, api_key)
            scenario = rw.get("scenario")
            keywords = rw.get("keywords") or q
            oral_query = rw.get("oral_query") or ""
        except Exception:
            scenario, keywords, oral_query = None, q, ""

        exp = "、".join(f"{t[0]}第{t[1]}条" for t in targets) if targets else "边界"

        for ver, search_fn in [("本地_向量BM25", kb.search), ("线上_纯BM25", online_search)]:
            laws1, cases1 = search_fn(keywords, scenario=scenario, k=K, extra_query=oral_query)
            rec1 = check_recall(targets, laws1)
            try:
                ans = llm.generate_answer(q, laws1, cases1, api_key)
            except Exception as e:
                ans = f"[生成失败] {e}"
            re2 = False
            laws_final, rec_final = laws1, rec1
            if "资料不足" in ans:
                re2 = True
                laws2, cases2 = search_fn(keywords, scenario=scenario, k=15, extra_query=oral_query)
                rec_final = check_recall(targets, laws2)
                laws_final = laws2
                try:
                    ans = llm.generate_answer(q, laws2, cases2, api_key)
                except Exception as e:
                    ans = f"[生成失败] {e}"
            rows.append({
                "题号": i, "版本": ver, "问题": q, "预期法条": exp,
                "改写场景": scenario or "（无）", "首轮检索法条": fmt_laws(laws1),
                "首轮召回": rec1, "是否二次检索": "是" if re2 else "否",
                "最终检索法条": fmt_laws(laws_final), "最终召回": rec_final,
                "是否资料不足": "是" if "资料不足" in ans else "否",
                "完整回答原文": ans,
            })

        print(f"[{i}/15] 完成", flush=True)

    cols = ["题号", "版本", "问题", "预期法条", "改写场景", "首轮检索法条", "首轮召回",
            "是否二次检索", "最终检索法条", "最终召回", "是否资料不足", "完整回答原文"]
    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print("DONE ->", OUT.name, flush=True)


if __name__ == "__main__":
    main()
