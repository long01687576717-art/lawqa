# -*- coding: utf-8 -*-
"""案例匹配离线复查：复用 _coverage_eval_result.csv 记录的改写结果，只跑案例筛选，对比前后变化。"""

import os
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
ROOT = EVAL_DIR.parents[1]
RESULTS = EVAL_DIR / "results"
sys.path[:0] = [str(ROOT), str(EVAL_DIR)]
os.chdir(ROOT)  # 数据路径按项目根目录解析
import csv
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

import case_tags as ct
from retriever import BM25, _tokenize
from synonyms import expand_query

cases = json.load(open("data/cases.json", encoding="utf-8"))
bm = BM25([_tokenize(ct.case_doc_text(c)) for c in cases])
idf = ct.tag_idf(cases)
only = set(int(x) for x in sys.argv[1:])  # 可指定题号
for r in csv.DictReader(open(RESULTS / "coverage_eval_result.csv", encoding="utf-8-sig")):
    n = int(r["序号"])
    if only and n not in only:
        continue
    q, kw = r["问题"], r["检索词"] or r["问题"]
    scen = None if r["场景"] in ("", "None") else r["场景"]
    query = f"{kw} {expand_query(q)}"
    sel = ct.select_cases(cases, bm.scores(_tokenize(query)), query, scen, idf=idf)
    new = [cases[i]["title"] for i in sel]
    old = r["案例"].split(" || ") if r["案例"] else []
    mark = "" if new == old else "  ← 有变化"
    print(f"{n}. {q}{mark}")
    for t in new:
        print("    ", ("[新增] " if t not in old else "") + t[:60])
    if not new:
        print("     （无案例）")
