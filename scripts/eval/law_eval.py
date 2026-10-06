# -*- coding: utf-8 -*-
"""法条召回离线对比：复用已记录的改写结果（检索词、场景），在旧库 / 新库上跑 kb.search，统计目标条文召回。

用法：python _law_eval.py [old|new] [k]
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
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import lawmeta
import retriever
from synonyms import expand_query
from testset import QUESTIONS_30, TARGETS_30, QUESTIONS_15, TARGETS_15

BASE = ROOT
FULL = {
    "劳动法": "中华人民共和国劳动法", "劳动合同法": "中华人民共和国劳动合同法",
    "社保法": "中华人民共和国社会保险法", "仲裁法": "中华人民共和国劳动争议调解仲裁法",
    "就业法": "中华人民共和国就业促进法", "实施条例": "中华人民共和国劳动合同法实施条例",
    "工伤": "工伤保险条例", "女职工": "女职工劳动保护特别规定", "年假条例": "职工带薪年休假条例",
    "解释一": "最高人民法院关于审理劳动争议案件适用法律问题的解释（一）",
    "工资支付": "工资支付暂行规定", "最低工资": "最低工资规定", "年假办法": "企业职工带薪年休假实施办法",
    "派遣": "劳务派遣暂行规定",
}

# 64 道企业问题中可设定目标条文的题（条号已对照官方原文核实）
TARGETS_64 = {
    1: [("就业法", 27)], 3: [("就业法", 30)], 4: [("劳动合同法", 9)],
    7: [("劳动合同法", 82), ("实施条例", 6)], 8: [("劳动合同法", 14)], 9: [("劳动合同法", 46)],
    10: [("劳动合同法", 34)], 11: [("劳动合同法", 19)], 12: [("劳动合同法", 20), ("实施条例", 15)],
    13: [("劳动合同法", 39)], 14: [("劳动法", 39)], 15: [("劳动法", 44)], 16: [("年假条例", 3)],
    17: [("年假条例", 5), ("年假办法", 10)], 20: [("劳动法", 51)], 21: [("女职工", 7)], 22: [("女职工", 9)],
    23: [("工资支付", 7)], 25: [("工资支付", 16)], 26: [("最低工资", 12)], 29: [("社保法", 58)],
    32: [("工伤", 17)], 33: [("工伤", 62), ("社保法", 41)], 34: [("工伤", 14)], 35: [("劳动合同法", 42)],
    36: [("工伤", 33)], 37: [("劳动合同法", 43)], 38: [("劳动合同法", 40)], 39: [("劳动合同法", 41)],
    40: [("劳动合同法", 47)], 41: [("劳动合同法", 87)], 42: [("劳动合同法", 39)], 43: [("劳动合同法", 37)],
    44: [("劳动合同法", 50), ("实施条例", 24)], 46: [("解释一", 36)], 47: [("解释一", 38)],
    49: [("劳动合同法", 22)], 50: [("派遣", 4)], 51: [("派遣", 12)], 52: [("劳动合同法", 68)],
    54: [("解释一", 32)], 56: [("女职工", 6)], 57: [("劳动合同法", 42), ("女职工", 5)], 58: [("劳动合同法", 4)],
    59: [("解释一", 50)], 60: [("仲裁法", 27)], 61: [("仲裁法", 6)], 62: [("女职工", 11)],
    63: [("劳动合同法", 40)], 64: [("劳动合同法", 39)],
}


def load_cases():
    """返回 [(组, 问题, 检索词, 场景, 目标条文列表)]，检索词与场景取自已记录的真实改写结果。"""
    out = []
    reg = {(r["组"], int(r["题号"])): r for r in csv.DictReader(open(RESULTS / "regression_cases_result.csv", encoding="utf-8-sig"))}
    for grp, qs, ts in (("原30", QUESTIONS_30, TARGETS_30), ("新15", QUESTIONS_15, TARGETS_15)):
        for n, (q, t) in enumerate(zip(qs, ts), 1):
            r = reg[(grp, n)]
            if t:
                out.append((grp, q, r["检索词"] or q, r["场景"], [(FULL[a], no) for a, no in t]))
    for r in csv.DictReader(open(RESULTS / "coverage_eval_result.csv", encoding="utf-8-sig")):
        n = int(r["序号"])
        if n in TARGETS_64:
            out.append(("企业64", r["问题"], r["检索词"] or r["问题"], r["场景"], [(FULL[a], no) for a, no in TARGETS_64[n]]))
    return out


def build_kb(version):
    if version == "old":  # 旧库：从 git HEAD 取出改造前的法条数据
        tmp = Path(tempfile.mkdtemp())
        for f in ("laws.json", "citation_index.json", "law_mapping.json", "law_notes.json"):
            data = subprocess.run(["git", "show", f"HEAD:data/{f}"], capture_output=True, cwd=BASE).stdout
            (tmp / f).write_bytes(data)
        shutil.copy(BASE / "data" / "cases.json", tmp / "cases.json")
        retriever.DATA_DIR = tmp
        lawmeta.DATA_DIR = tmp
    return retriever.KnowledgeBase()


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else "new"
    k = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    import os
    for name, cast in (("K_OTHER", int), ("ORAL_SCOPE", str)):
        if os.environ.get(name):
            setattr(retriever.KnowledgeBase, name, cast(os.environ[name]))
    if os.environ.get("MAX_EXTRA"):
        orig = lawmeta.expand_with_citations
        lawmeta.expand_with_citations = lambda *a, **kw: orig(*a, **dict(kw, max_extra=int(os.environ["MAX_EXTRA"])))
    kb = build_kb(version)
    print(f"参数：K_OTHER={kb.K_OTHER} ORAL_SCOPE={kb.ORAL_SCOPE} MAX_EXTRA={os.environ.get('MAX_EXTRA', 4)}")
    stats, misses = {}, []
    for grp, q, kw, scen, targets in load_cases():
        scen = None if scen in ("", "None") else scen
        laws, _ = kb.search(kw, scenario=scen, k=k, extra_query=expand_query(q))
        got = {(l["law"], lawmeta.cn_to_arabic(l["article"])) for l in laws}
        hit = sum(1 for t in targets if t in got)
        s = stats.setdefault(grp, [0, 0, 0, 0])
        s[0] += hit; s[1] += len(targets); s[2] += hit == len(targets); s[3] += 1
        if hit < len(targets):
            misses.append(f"[{grp}] {q[:22]} 缺 {[f'{t[0][-6:]}{t[1]}' for t in targets if t not in got]}（共返回 {len(laws)} 条）")
    print(f"== 版本 {version}，k={k}")
    for grp, (h, t, full, n) in stats.items():
        print(f"  {grp}: 条文召回 {h}/{t}（{h / t:.0%}），全召回题 {full}/{n}")
    print("  未召回明细：")
    for m in misses:
        print("   ", m)


if __name__ == "__main__":
    main()
