# -*- coding: utf-8 -*-
"""端到端验证：30 道 HR 常见问题，分别跑两个版本的检索逻辑，完整回答存 CSV。
- 本地版：retriever.KnowledgeBase.search（向量 + BM25 的 RRF 融合）
- 线上版：纯 BM25（对齐 streamlit_app.py 的 search 逻辑）
只采集原始数据，不判定（判定由人工核对 laws.json 后完成）。
"""

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
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import config  # noqa: F401
import llm
from retriever import KnowledgeBase, BM25, _tokenize

BASE = ROOT
OUT_CSV = RESULTS / "validate_e2e_result.csv"

QUESTIONS = [
    "签2年劳动合同，试用期最长能约定多久？",
    "同一个员工能约定两次试用期吗？",
    "试用期工资最低能发多少？",
    "试用期发现员工不符合录用条件，能直接辞退吗？",
    "员工入职两个月了还没签合同，公司有什么风险？",
    "什么情况下必须签无固定期限劳动合同？",
    "工作日、休息日、法定节假日加班费分别怎么算？",
    "每个月加班最多能加多少小时？",
    "员工辞职要提前多久通知？试用期呢？",
    "公司拖欠工资，员工能不能马上走人并要补偿？",
    "公司没给员工交社保，员工能解除合同吗？",
    "员工严重违反规章制度被辞退，要给经济补偿吗？",
    "员工不胜任工作，公司怎样才能合法解除？",
    "绩效末位淘汰能不能直接辞退员工？",
    "经济补偿金怎么计算？有没有封顶？",
    "公司违法解除劳动合同要赔多少？",
    "公司要裁员25人，需要走什么程序？",
    "员工怀孕了，公司能以不胜任为由辞退吗？",
    "员工在医疗期内合同到期了怎么办？",
    "竞业限制最长多久？公司要付补偿吗？",
    "劳动合同里哪些情况可以约定违约金？",
    "公司出钱送员工培训，能约定服务期吗？",
    "公司想给员工调岗降薪，需要员工同意吗？",
    "公司制定规章制度要走什么程序才有效？",
    "员工离职后，公司要在多久内开离职证明、转档案？",
    "哪些岗位可以用劳务派遣？",
    "员工申请劳动仲裁的时效是多久？",
    "员工工作满5年，每年有几天带薪年休假？",
    "产假有多少天？",
    "公司能不能要求员工签\"自愿放弃社保\"协议？",
]

EXPECTED = [
    "劳动合同法第 19 条",
    "劳动合同法第 19 条",
    "劳动合同法第 20 条",
    "劳动合同法第 21 条、第 39 条",
    "劳动合同法第 10 条、第 82 条",
    "劳动合同法第 14 条",
    "劳动法第 44 条",
    "劳动法第 41 条",
    "劳动合同法第 37 条",
    "劳动合同法第 38 条、第 46 条",
    "劳动合同法第 38 条",
    "劳动合同法第 39 条、第 46 条",
    "劳动合同法第 40 条",
    "劳动合同法第 40 条 + 指导案例 18 号",
    "劳动合同法第 47 条",
    "劳动合同法第 48 条、第 87 条",
    "劳动合同法第 41 条",
    "劳动合同法第 42 条",
    "劳动合同法第 42 条、第 45 条",
    "劳动合同法第 23 条、第 24 条",
    "劳动合同法第 25 条",
    "劳动合同法第 22 条",
    "劳动合同法第 35 条",
    "劳动合同法第 4 条",
    "劳动合同法第 50 条",
    "劳动合同法第 66 条",
    "边界题：应适用《劳动争议调解仲裁法》第 27 条，不在知识库内",
    "边界题：劳动法第 45 条只作原则规定，具体天数在《职工带薪年休假条例》",
    "边界题：劳动法第 62 条写的是不少于 90 天，现行 98 天出自《女职工劳动保护特别规定》",
    "劳动法第 72 条、劳动合同法第 38 条",
]


def cn_to_arabic(s: str):
    d = {'零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4,
         '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
    s = (s or '').strip().replace(' ', '')
    if not s:
        return None
    total = 0
    if '百' in s:
        before, s = s.split('百', 1)
        total += (d.get(before, 1) if before else 1) * 100
    if '十' in s:
        before, s = s.split('十', 1)
        total += (d.get(before, 1) if before else 1) * 10
    for ch in s:
        if ch in d:
            total += d[ch]
    return total


def fmt_laws(ls):
    return '; '.join(
        f"{l.get('law', '').replace('中华人民共和国', '')}第{cn_to_arabic(l.get('article', ''))}条"
        for l in ls)


def fmt_cases(cs):
    return '; '.join(c.get('title', '') for c in cs)


def bm25_top(scores, k):
    if not len(scores):
        return []
    return sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]


def bm25_top_cases(scores, scenario, k, min_score):
    if scenario:
        cand = [i for i in range(len(cases)) if cases[i].get('scenario') == scenario]
    else:
        cand = list(range(len(cases)))
    if not cand:
        return []
    cand_sorted = sorted(cand, key=lambda i: scores[i], reverse=True)[:k]
    if scores[cand_sorted[0]] < min_score:
        return []
    return cand_sorted


def online_search(query, scenario, k=5):
    """线上版：纯 BM25（对齐 streamlit_app.search）。"""
    q = _tokenize(query)
    law_idx = bm25_top(law_bm25.scores(q), k)
    if scenario == "无":
        case_idx = []
    else:
        case_idx = bm25_top_cases(case_bm25.scores(q), scenario, 3, 0.8)
    return [laws[i] for i in law_idx], [cases[i] for i in case_idx]


def main():
    print("加载知识库 + 向量模型...", flush=True)
    kb = KnowledgeBase()
    global laws, cases, law_bm25, case_bm25
    laws = kb.laws
    cases = kb.cases
    law_docs = [f"{l.get('law', '')} 第{l.get('article', '')}条 {l.get('text', '')}" for l in laws]
    case_docs = [" ".join(str(c.get(k, "")) for k in ("title", "summary", "ruling", "keywords")) for c in cases]
    law_bm25 = BM25([_tokenize(t) for t in law_docs])
    case_bm25 = BM25([_tokenize(t) for t in case_docs])

    api_key = config.DEEPSEEK_API_KEY
    rows = []

    for i, (q, exp) in enumerate(zip(QUESTIONS, EXPECTED), 1):
        # 查询改写（两版本共享同一次改写，隔离“检索算法”这个变量）
        try:
            rw = llm.rewrite_query(q, api_key)
            scenario = rw.get('scenario')
            keywords = rw.get('keywords') or q
        except Exception as e:
            scenario, keywords = None, q
            rw = {'scenario': None, 'keywords': q, '_error': str(e)}
        scenario_str = scenario or "（无/解析失败）"

        # 本地版检索（向量 + BM25 RRF）
        lawsA, casesA = kb.search(keywords, scenario=scenario, k=5)
        # 线上版检索（纯 BM25）
        lawsB, casesB = online_search(keywords, scenario=scenario, k=5)

        # 两版本各自生成
        try:
            ansA = llm.generate_answer(q, lawsA, casesA, api_key)
        except Exception as e:
            ansA = f"[生成失败] {e}"
        try:
            ansB = llm.generate_answer(q, lawsB, casesB, api_key)
        except Exception as e:
            ansB = f"[生成失败] {e}"

        rows.append({
            "题号": i, "版本": "本地_向量BM25", "问题": q, "预期依据": exp,
            "改写场景": scenario_str, "改写关键词": keywords,
            "检索法条": fmt_laws(lawsA), "检索案例": fmt_cases(casesA),
            "完整回答原文": ansA, "判定结果": "", "判定理由": "",
        })
        rows.append({
            "题号": i, "版本": "线上_纯BM25", "问题": q, "预期依据": exp,
            "改写场景": scenario_str, "改写关键词": keywords,
            "检索法条": fmt_laws(lawsB), "检索案例": fmt_cases(casesB),
            "完整回答原文": ansB, "判定结果": "", "判定理由": "",
        })

        print(f"[{i}/30] 完成 {q[:20]}...", flush=True)

    cols = ["题号", "版本", "问题", "预期依据", "改写场景", "改写关键词",
            "检索法条", "检索案例", "完整回答原文", "判定结果", "判定理由"]
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print("DONE ->", OUT_CSV.name, flush=True)


if __name__ == "__main__":
    main()
