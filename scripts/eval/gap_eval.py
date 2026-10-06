# -*- coding: utf-8 -*-
"""缺口题评测：病假医疗期、经济性裁员、辞职、公积金、退休返聘、节假日、工时、招聘婚育等方向。

首次运行调用大模型做查询改写并缓存到 results/gap_rewrite.csv，之后复用缓存离线检索；
统计目标条文召回，并列出前 3 个案例及是否命中预期案例关键词。

用法：python scripts/eval/gap_eval.py [--refresh]   # --refresh 重新调用大模型改写
"""
import csv
import os
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
ROOT = EVAL_DIR.parents[1]
RESULTS = EVAL_DIR / "results"
sys.path[:0] = [str(ROOT), str(EVAL_DIR)]
os.chdir(ROOT)  # 数据路径按项目根目录解析
sys.stdout.reconfigure(encoding="utf-8")

import config
import lawmeta
import llm
from retriever import KnowledgeBase
from synonyms import expand_query

CACHE = RESULTS / "gap_rewrite.csv"
LAWS = {
    "劳动法": "中华人民共和国劳动法", "劳动合同法": "中华人民共和国劳动合同法",
    "妇女法": "中华人民共和国妇女权益保障法", "就业法": "中华人民共和国就业促进法",
    "公积金": "住房公积金管理条例", "年节": "全国年节及纪念日放假办法", "工时": "国务院关于职工工作时间的规定",
    "医疗期": "企业职工患病或非因工负伤医疗期规定", "裁员": "企业经济性裁减人员规定",
    "意见": "关于贯彻执行〈中华人民共和国劳动法〉若干问题的意见",
    "解释一": "最高人民法院关于审理劳动争议案件适用法律问题的解释（一）",
}

# (问题, 目标条文, 预期案例标题关键词；空表示该方向暂不要求案例)
GAP = [
    ("员工请病假，公司病假工资最低能发多少？", [("意见", 59)], ""),
    ("员工在公司干了3年，生病了能休多长的医疗期？", [("医疗期", 3)], ""),
    ("员工医疗期满了还不能上班，公司能解除合同吗？", [("劳动合同法", 40)], ""),
    ("公司经营困难要裁员20人，需要走什么程序？", [("劳动合同法", 41), ("裁员", 4)], "裁员"),
    ("公司裁员能裁正在休产假的员工吗？", [("劳动合同法", 42)], ""),
    ("员工提交辞职信，公司不批准，员工能直接走吗？", [("劳动合同法", 37)], "提离职"),
    ("公司不给员工交住房公积金，合法吗？", [("公积金", 20)], "公积金"),
    ("住房公积金单位缴存比例最低是多少？", [("公积金", 18)], ""),
    ("员工离职后要求公司补缴公积金，可以申请劳动仲裁吗？", [], "公积金"),
    ("招聘时能要求女应聘者做孕检吗？", [("妇女法", 43)], ""),
    ("招聘时能问应聘者的婚育情况吗？", [("妇女法", 43)], ""),
    ("国庆节安排员工加班，工资按几倍算？", [("劳动法", 44), ("年节", 2)], ""),
    ("每周标准工作时间是多少小时？", [("工时", 3)], ""),
    ("返聘已经领退休金的员工，双方是什么关系？", [("解释一", 32)], "退休"),
    ("员工到了退休年龄但没领养老金，还是劳动关系吗？", [], "退休年龄"),
]


def rewrite_all(refresh):
    cache = {}
    if CACHE.exists() and not refresh:
        cache = {r["问题"]: r for r in csv.DictReader(open(CACHE, encoding="utf-8-sig"))}
    for q, _, _ in GAP:
        if q in cache:
            continue
        rw = llm.rewrite_query(q, config.DEEPSEEK_API_KEY)
        cache[q] = {"问题": q, "场景": rw.get("scenario") or "", "检索词": rw.get("keywords") or ""}
        print("改写：", q, "->", cache[q]["场景"], cache[q]["检索词"])
    RESULTS.mkdir(exist_ok=True)
    with open(CACHE, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["问题", "场景", "检索词"])
        w.writeheader()
        w.writerows(cache[q] for q, _, _ in GAP)
    return cache


def main():
    cache = rewrite_all("--refresh" in sys.argv)
    kb = KnowledgeBase()
    hit_all = need_all = case_ok = case_need = 0
    for n, (q, targets, case_kw) in enumerate(GAP, 1):
        r = cache[q]
        scen = None if r["场景"] in ("", "None", "无") else r["场景"]
        laws, cases = kb.search(r["检索词"] or q, scenario=scen, k=5, extra_query=expand_query(q))
        got = {(l["law"], lawmeta.cn_to_arabic(l["article"])) for l in laws}
        miss = [f"{a}{no}" for a, no in targets if (LAWS[a], no) not in got]
        hit_all += len(targets) - len(miss)
        need_all += len(targets)
        titles = [c["title"] for c in cases]
        ok = any(case_kw in t for t in titles) if case_kw else None
        case_need += bool(case_kw)
        case_ok += bool(ok)
        flag = "" if not miss else f"  缺 {miss}"
        print(f"{n:02d}. {q}（场景：{scen or '无'}）法条 {len(targets) - len(miss)}/{len(targets)}{flag}")
        for t in titles:
            print("      ·", t)
        if case_kw:
            print("      预期案例「%s」：%s" % (case_kw, "命中" if ok else "未命中"))
    print(f"\n法条召回 {hit_all}/{need_all}；预期案例命中 {case_ok}/{case_need}")


if __name__ == "__main__":
    main()
