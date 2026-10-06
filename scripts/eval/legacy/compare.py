# -*- coding: utf-8 -*-
"""对比改进前后：核心法条召回 + 是否资料不足。

改进前数据：_validate_e2e_result.csv（检索法条 / 完整回答原文）
改进后数据：_regression_result.csv（最终召回 / 是否资料不足 / 完整回答原文）
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

sys.stdout.reconfigure(encoding="utf-8")

from testset import QUESTIONS_30, TARGETS_30

OLD = RESULTS / "validate_e2e_result.csv"
NEW = RESULTS / "regression_result.csv"


def target_items(targets):
    return [f"{t[0]}第{t[1]}条" for t in targets]


def recall_from_string(targets, laws_str):
    items = [x.strip() for x in (laws_str or "").split(";") if x.strip()]
    ts = target_items(targets)
    if not ts:
        return "-"
    hit = sum(1 for t in ts if t in items)
    return f"{hit}/{len(ts)}"


def main():
    old = list(csv.DictReader(open(OLD, encoding="utf-8-sig")))
    new = list(csv.DictReader(open(NEW, encoding="utf-8-sig")))

    print("题号 | 版本 | 预期法条 | 召回(旧→新) | 资料不足(旧→新) | 变化")
    print("-" * 90)

    for ver in ["本地_向量BM25", "线上_纯BM25"]:
        tot_old_recall_hit, tot_old_recall_all = 0, 0
        tot_new_recall_hit, tot_new_recall_all = 0, 0
        old_insuf, new_insuf = 0, 0
        print(f"--- {ver} ---")
        for i, (q, targets) in enumerate(zip(QUESTIONS_30, TARGETS_30), 1):
            orow = next(r for r in old if int(r["题号"]) == i and r["版本"] == ver)
            nrow = next(r for r in new if int(r["题号"]) == i and r["版本"] == ver)

            o_rec = recall_from_string(targets, orow["检索法条"])
            n_rec = nrow["最终召回"]
            o_ins = "资料不足" in orow["完整回答原文"]
            n_ins = nrow["是否资料不足"] == "是"

            # 召回统计（仅计算有目标的题）
            if targets:
                oh, oa = o_rec.split("/")
                nh, na = n_rec.split("/")
                tot_old_recall_hit += int(oh); tot_old_recall_all += int(oa)
                tot_new_recall_hit += int(nh); tot_new_recall_all += int(na)
            if o_ins:
                old_insuf += 1
            if n_ins:
                new_insuf += 1

            changes = []
            if targets and o_rec != n_rec:
                changes.append("召回" + ("↑" if int(n_rec.split("/")[0]) > int(o_rec.split("/")[0]) else "↓"))
            if o_ins != n_ins:
                changes.append("资料不足" + ("消除" if (o_ins and not n_ins) else "新增"))
            flag = "  <== " + " ".join(changes) if changes else ""
            print(f"{i:2d} | {ver} | {('、'.join(target_items(targets)) if targets else '边界'):<28s} | {o_rec}→{n_rec} | {'是' if o_ins else '否'}→{'是' if n_ins else '否'} |{flag}")

        print(f"   召回汇总(旧→新): {tot_old_recall_hit}/{tot_old_recall_all} → {tot_new_recall_hit}/{tot_new_recall_all}")
        print(f"   资料不足题数(旧→新): {old_insuf} → {new_insuf}")
        print()


if __name__ == "__main__":
    main()
