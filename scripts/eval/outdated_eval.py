# -*- coding: utf-8 -*-
"""旧规风险评测：针对 1995 年《劳动法若干问题的意见》中已被后法调整的条目提问，
检查回答是否把过时规定当作现行规定。

每题运行真实流程（改写 + 检索 + 生成），输出回答中引用的《意见》条目、命中的「过时说法」关键词，
结果写入 results/outdated_eval_result.json，供人工逐题复核。

用法：python scripts/eval/outdated_eval.py
"""
import json
import os
import re
import sys
import time
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

OPINION = "关于贯彻执行〈中华人民共和国劳动法〉若干问题的意见"

# (问题, 涉及的过时条目, 回答中出现即视为「可能沿用旧规」的说法)
QS = [
    ("劳动合同到期公司不续签，要给员工经济补偿吗？", [38], ["可以不支付"]),
    ("员工日工资怎么折算？月工资除以多少天？", [61], ["21.16", "21．16", "23.33", "23．33"]),
    ("公司一直没跟员工签劳动合同，员工能主张什么？", [17], ["223号"]),
    ("员工参加公司出资的培训后提前离职，公司能要求赔多少培训费？", [23], ["223号"]),
    ("试用期最长可以约定多久？", [19], ["一律不超过六个月", "一般不超过六个月"]),
    ("员工申请劳动仲裁的时效是多久？去调解委员会调解期间时效怎么算？", [89], ["三十日之后", "最长不得超过三十日"]),
    ("员工工伤了，工伤待遇按什么规定执行？", [77, 78], ["劳动保险条例"]),
    ("员工年休假应该按什么规定安排？", [72], ["1991年", "职工休假问题的通知"]),
    ("员工医疗期满后被鉴定为伤残五级，公司解除合同要付哪些钱？", [35], ["医疗补助费"]),
    ("公司被别的公司合并了，员工能要求经济补偿吗？", [37], ["民法通则"]),
    ("员工被公安机关拘留了，公司能和他解除劳动合同吗？", [28, 29, 31], ["劳动教养", "收容审查", "免予起诉"]),
    ("公司解除劳动合同的经济补偿怎么计算？", [36], ["481号"]),
]


def retry(fn, *args, tries=4):
    """网络波动时重试大模型调用。"""
    for n in range(tries):
        try:
            return fn(*args)
        except Exception as e:  # noqa: BLE001
            if n == tries - 1:
                raise
            print(f"    （调用失败，{5 * (n + 1)} 秒后重试：{type(e).__name__}）")
            time.sleep(5 * (n + 1))


# 段落中出现这些表述，说明回答是在指出旧规已被调整，而不是沿用旧规
CORRECTION = ("调整说明", "不再适用", "已经取消", "已取消", "已失效", "已废止", "不一致", "请勿", "旧规", "不应再", "过渡性", "优先适用", "上位法")


def stale_hits(answer, bad_words):
    """返回「沿用旧规」的说法：所在段落及下一段都没有纠正性表述的过时说法。"""
    hits = []
    paras = [p for p in answer.split("\n") if p.strip()]
    for i, para in enumerate(paras):
        window = para + (paras[i + 1] if i + 1 < len(paras) else "")  # 纠正说明常紧跟在下一段
        if any(c in window for c in CORRECTION):
            continue
        hits += [w for w in bad_words if w in para and w not in hits]
    return hits


CITE = re.compile(r"《([^》]{2,40})》(?:（[^）]{1,8}）)?第([零一二三四五六七八九十百\d]+)条")


def main():
    kb = KnowledgeBase()
    out, risky = [], 0
    for q, items, bad_words in QS:
        rw = retry(llm.rewrite_query, q, config.DEEPSEEK_API_KEY)
        kw, scen, oral = rw.get("keywords") or q, rw.get("scenario"), rw.get("oral_query") or ""
        laws, cases = kb.search(kw, scenario=scen, k=5, extra_query=oral)
        ans = retry(llm.generate_answer, q, laws, cases, config.DEEPSEEK_API_KEY)
        retrieved = sorted(lawmeta.cn_to_arabic(l["article"]) for l in laws if l["law"] == OPINION)
        cited = sorted({int(m.group(2)) if m.group(2).isdigit() else lawmeta.cn_to_arabic(m.group(2))
                        for m in CITE.finditer(ans) if "若干问题的意见" in m.group(1)})
        hits = stale_hits(ans, bad_words)
        flag = bool(hits)
        risky += flag
        print(f"{'⚠' if flag else '✓'} {q}\n    检索到《意见》{retrieved}；引用《意见》{cited}；沿用旧规的说法 {hits or '无'}")
        out.append({"q": q, "items": items, "retrieved": retrieved, "cited": cited, "hits": hits, "flag": flag, "answer": ans})
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "outdated_eval_result.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n需人工复核 {risky}/{len(QS)} 题（⚠ 表示引用了过时条目或出现过时说法，不一定答错）")


if __name__ == "__main__":
    main()
