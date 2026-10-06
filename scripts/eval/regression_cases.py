# -*- coding: utf-8 -*-
"""回归脚本（案例方向标签版）：原 30 题 + 新 15 题 + 新方向 8 题，走真实链路（改写 → kb.search → 生成）。

统计：核心法条召回、返回案例及其标签、回答是否引用案例 / 是否写「暂无高度相关案例」。
"""

import os
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
ROOT = EVAL_DIR.parents[1]
RESULTS = EVAL_DIR / "results"
sys.path[:0] = [str(ROOT), str(EVAL_DIR)]
os.chdir(ROOT)  # 数据路径按项目根目录解析
import csv
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import config
import lawmeta
import llm
from case_tags import tags_of
from retriever import KnowledgeBase

from testset import QUESTIONS_30, TARGETS_30, QUESTIONS_15, TARGETS_15

BASE = ROOT
OUT = RESULTS / "regression_cases_result.csv"

# 新方向题：查询改写的 12 个场景未覆盖，依赖方向标签找案例
QUESTIONS_NEW = [
    "公司搬迁到另一个区，员工不愿意去，能辞退吗？",
    "公司发了offer后又取消，候选人已经辞职了怎么办？",
    "公司出钱送员工培训，员工提前走要赔培训费吗？",
    "员工要求开离职证明，公司能写他违纪被开除吗？",
    "外卖骑手和平台算劳动关系吗？",
    "员工在公司对同事性骚扰，能开除吗？",
    "员工简历学历造假，入职后发现了能解除合同吗？",
    "红烧肉怎么做才好吃？",
]
TARGETS_NEW = [[] for _ in QUESTIONS_NEW]


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
    hit = sum(1 for tlaw, tno in targets if any(law_matches(tlaw, a) and n == tno for a, n in art))
    return f"{hit}/{len(targets)}"


def main():
    api_key = config.DEEPSEEK_API_KEY
    kb = KnowledgeBase()
    rows = []
    groups = [("原30", QUESTIONS_30, TARGETS_30), ("新15", QUESTIONS_15, TARGETS_15), ("新方向", QUESTIONS_NEW, TARGETS_NEW)]
    for group, qs, ts in groups:
        for n, (q, targets) in enumerate(zip(qs, ts), 1):
            try:
                rw = llm.rewrite_query(q, api_key)
                scenario, keywords, oral = rw.get("scenario"), rw.get("keywords") or q, rw.get("oral_query") or ""
            except Exception as e:
                scenario, keywords, oral = None, q, ""
                print("改写失败：", e)
            laws, cases = kb.search(keywords, scenario=scenario, k=5, extra_query=oral)
            answer = llm.generate_answer(q, laws, cases, api_key)
            if "资料不足" in answer:
                laws, cases = kb.search(keywords, scenario=scenario, k=15, extra_query=oral)
                answer = llm.generate_answer(q, laws, cases, api_key)
            cited = [c["title"] for c in cases if c["title"].split("——")[-1][:6] in answer or c["title"][:8] in answer]
            row = {
                "组": group, "题号": n, "问题": q, "场景": scenario, "检索词": keywords,
                "问题标签": "、".join(tags_of(f"{keywords} {oral}")),
                "法条召回": check_recall(targets, laws),
                "案例数": len(cases),
                "案例": " | ".join(f"{c['title'][:40]}[{'/'.join(c['tags'])}]" for c in cases),
                "回答引用案例": " | ".join(t[:30] for t in cited),
                "暂无相关案例": "是" if "暂无高度相关案例" in answer else "",
                "回答": answer,
            }
            rows.append(row)
            print(f"[{group}#{n}] {q[:24]} 场景={scenario} 召回={row['法条召回']} 案例={len(cases)} 引用={len(cited)} 暂无={row['暂无相关案例']}")
            print("     ", row["案例"][:160])
    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\n已写入 {OUT}")


if __name__ == "__main__":
    main()
