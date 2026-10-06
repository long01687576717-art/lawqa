# -*- coding: utf-8 -*-
"""检索层客观验证：用 BM25 对 30 道 HR 常见问题做检索，判断目标法条是否被召回。"""

import os
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent.parent
ROOT = EVAL_DIR.parents[1]
RESULTS = EVAL_DIR / "results"
sys.path[:0] = [str(ROOT), str(EVAL_DIR)]
os.chdir(ROOT)  # 数据路径按项目根目录解析
import json
from pathlib import Path

import jieba

from retriever import BM25, _tokenize

DATA_DIR = ROOT / "data"
OUT = RESULTS / "validate_retrieval_result.txt"


def cn_to_arabic(s: str):
    """中文数字 -> 阿拉伯数字（如 四十四 -> 44, 一百零七 -> 107）。"""
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


def law_matches(target_law: str, actual_law: str) -> bool:
    if target_law == '劳动合同法':
        return '劳动合同法' in actual_law
    if target_law == '劳动法':
        return actual_law == '中华人民共和国劳动法'  # 精确，排除劳动合同法
    return target_law in actual_law


# ---- 30 题：题目文本 + 目标法条 [(法律简称, 阿拉伯条号)]；边界题目标为空 ----
QUESTIONS = [
    ("签2年劳动合同，试用期最长能约定多久？", [("劳动合同法", 19)]),
    ("同一个员工能约定两次试用期吗？", [("劳动合同法", 19)]),
    ("试用期工资最低能发多少？", [("劳动合同法", 20)]),
    ("试用期发现员工不符合录用条件，能直接辞退吗？", [("劳动合同法", 21), ("劳动合同法", 39)]),
    ("员工入职两个月了还没签合同，公司有什么风险？", [("劳动合同法", 10), ("劳动合同法", 82)]),
    ("什么情况下必须签无固定期限劳动合同？", [("劳动合同法", 14)]),
    ("工作日、休息日、法定节假日加班费分别怎么算？", [("劳动法", 44)]),
    ("每个月加班最多能加多少小时？", [("劳动法", 41)]),
    ("员工辞职要提前多久通知？试用期呢？", [("劳动合同法", 37)]),
    ("公司拖欠工资，员工能不能马上走人并要补偿？", [("劳动合同法", 38), ("劳动合同法", 46)]),
    ("公司没给员工交社保，员工能解除合同吗？", [("劳动合同法", 38)]),
    ("员工严重违反规章制度被辞退，要给经济补偿吗？", [("劳动合同法", 39), ("劳动合同法", 46)]),
    ("员工不胜任工作，公司怎样才能合法解除？", [("劳动合同法", 40)]),
    ("绩效末位淘汰能不能直接辞退员工？", [("劳动合同法", 40)]),  # 另需 指导案例18号
    ("经济补偿金怎么计算？有没有封顶？", [("劳动合同法", 47)]),
    ("公司违法解除劳动合同要赔多少？", [("劳动合同法", 48), ("劳动合同法", 87)]),
    ("公司要裁员25人，需要走什么程序？", [("劳动合同法", 41)]),
    ("员工怀孕了，公司能以不胜任为由辞退吗？", [("劳动合同法", 42)]),
    ("员工在医疗期内合同到期了怎么办？", [("劳动合同法", 42), ("劳动合同法", 45)]),
    ("竞业限制最长多久？公司要付补偿吗？", [("劳动合同法", 23), ("劳动合同法", 24)]),
    ("劳动合同里哪些情况可以约定违约金？", [("劳动合同法", 25)]),
    ("公司出钱送员工培训，能约定服务期吗？", [("劳动合同法", 22)]),
    ("公司想给员工调岗降薪，需要员工同意吗？", [("劳动合同法", 35)]),
    ("公司制定规章制度要走什么程序才有效？", [("劳动合同法", 4)]),
    ("员工离职后，公司要在多久内开离职证明、转档案？", [("劳动合同法", 50)]),
    ("哪些岗位可以用劳务派遣？", [("劳动合同法", 66)]),
    ("员工申请劳动仲裁的时效是多久？", []),  # 边界：劳动争议调解仲裁法27，不在库
    ("员工工作满5年，每年有几天带薪年休假？", []),  # 边界：职工带薪年休假条例，不在库
    ("产假有多少天？", []),  # 边界：女职工劳动保护特别规定，不在库
    ("公司能不能要求员工签自愿放弃社保协议？", [("劳动法", 72), ("劳动合同法", 38)]),
]

K = 5


def main():
    laws = json.load(open(DATA_DIR / "laws.json", encoding="utf-8"))
    cases = json.load(open(DATA_DIR / "cases.json", encoding="utf-8"))

    # 构建法条索引：doc 文本 + 阿拉伯条号
    law_docs, law_art = [], []
    for l in laws:
        law_docs.append(f"{l.get('law','')} 第{l.get('article','')}条 {l.get('text','')}")
        law_art.append((l.get('law', ''), cn_to_arabic(l.get('article', ''))))
    law_bm25 = BM25([_tokenize(t) for t in law_docs])

    # 构建案例索引
    case_docs = [" ".join(str(c.get(k, "")) for k in ("title", "summary", "ruling", "keywords")) for c in cases]
    case_bm25 = BM25([_tokenize(t) for t in case_docs])

    lines = []
    lines.append("=" * 70)
    lines.append("法条检索验证（BM25, top-5）—— 原始问题直接检索（未做LLM改写）")
    lines.append("=" * 70)
    lines.append("")

    hit_at_least_one = 0
    hit_all = 0
    total_with_target = 0

    for i, (q, targets) in enumerate(QUESTIONS, 1):
        scores = law_bm25.scores(_tokenize(q))
        order = sorted(range(len(scores)), key=lambda j: scores[j], reverse=True)[:K]
        top = [law_art[j] for j in order]  # [(law, 条号)]

        if not targets:  # 边界题，仅记录检索到了什么
            top_str = ", ".join(f"{t[0].replace('中华人民共和国','')}{t[1]}条" for t in top)
            lines.append(f"[边界] 第{i}题：{q}")
            lines.append(f"       检索top-{K}：{top_str}")
            lines.append("")
            continue

        total_with_target += 1
        target_nums = set()
        hit_flags = []
        for tlaw, tno in targets:
            target_nums.add(tno)
            ok = any(law_matches(tlaw, alaw) and ano == tno for alaw, ano in top)
            hit_flags.append(ok)

        all_hit = all(hit_flags)
        any_hit = any(hit_flags)
        if all_hit:
            hit_all += 1
        if any_hit:
            hit_at_least_one += 1

        # 每个目标法条的排名（在top-k内为rank，否则"-"）
        rank_info = []
        for tlaw, tno in targets:
            rk = next((r for r, (alaw, ano) in enumerate(top, 1) if law_matches(tlaw, alaw) and ano == tno), None)
            rank_info.append(f"{tlaw}{tno}条@{rk if rk else '-'}")
        top_str = ", ".join(f"{t[0].replace('中华人民共和国','')}{t[1]}条" for t in top)
        mark = "✅" if all_hit else ("🟡" if any_hit else "❌")
        lines.append(f"{mark} 第{i}题：{q}")
        lines.append(f"   目标：{'、'.join(rank_info)}  |  检索top-{K}：{top_str}")
        lines.append("")

    lines.append("-" * 70)
    lines.append(f"汇总（有库内目标的 {total_with_target} 题）：")
    lines.append(f"  至少命中一条：{hit_at_least_one}/{total_with_target}")
    lines.append(f"  完全命中（多法条题全部召回）：{hit_all}/{total_with_target}")
    lines.append("")

    # ---- 案例检索（第14题 绩效末位淘汰 -> 指导案例18号 中兴通讯诉王鹏）----
    lines.append("=" * 70)
    lines.append("案例检索验证（第14题 绩效末位淘汰）")
    lines.append("=" * 70)
    q14 = "绩效末位淘汰能不能直接辞退员工？"
    c_scores = case_bm25.scores(_tokenize(q14))
    c_order = sorted(range(len(c_scores)), key=lambda j: c_scores[j], reverse=True)[:5]
    for r, j in enumerate(c_order, 1):
        c = cases[j]
        lines.append(f"  #{r} [{c.get('title','')}] 案号={c.get('case_no','')} 场景={c.get('scenario','')}")
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("DONE ->", OUT.name)


if __name__ == "__main__":
    main()
