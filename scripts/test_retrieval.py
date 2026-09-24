# -*- coding: utf-8 -*-
"""检索效果验证：查询改写 + RRF 混合检索。

用法：python scripts/test_retrieval.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

import config
import llm
from retriever import KnowledgeBase

kb = KnowledgeBase()
has_key = bool(config.DEEPSEEK_API_KEY)

# (口语化问题, 期望命中的法律名, 期望条号)
CASES = [
    ("没签合同赔钱", "中华人民共和国劳动合同法", "八十二"),
    ("公司拖欠工资怎么办", "中华人民共和国劳动法", "五十"),
    ("试用期最长多久", "中华人民共和国劳动合同法", "十九"),
    ("加班工资怎么算", "中华人民共和国劳动法", "四十四"),
]

# 无 API key 时的模拟改写结果（模拟 DeepSeek 的输出，仅用于验证检索链路）
MOCK = {
    "没签合同赔钱": "未签订书面劳动合同 二倍工资 赔偿",
    "公司拖欠工资怎么办": "用人单位 拖欠劳动报酬 工资",
    "试用期最长多久": "试用期 期限 六个月",
    "加班工资怎么算": "延长工作时间 加班费 加班工资 百分之一百五十 百分之二百 百分之三百",
}


def rewrite_or_mock(q):
    if has_key:
        try:
            r = llm.rewrite_query(q, config.DEEPSEEK_API_KEY)
            if r:
                return r
        except Exception as e:
            print(f"  [warn] 真实改写失败，改用模拟改写（原因：{e}）")
    return MOCK.get(q, q)


print(f"API key: {'已配置（真实改写）' if has_key else '未配置（改写用模拟结果）'}")
all_pass = True
for q, expect_law, expect_art in CASES:
    rw = rewrite_or_mock(q)
    laws, _ = kb.search(rw, k=5)
    hit = any(l["law"] == expect_law and l["article"] == expect_art for l in laws)
    all_pass = all_pass and hit
    print(f"\nQ: {q}\n  改写: {rw}")
    for i, l in enumerate(laws, 1):
        mark = "  <== 命中" if (l["law"] == expect_law and l["article"] == expect_art) else ""
        print(f"  {i}. 《{l['law']}》第{l['article']}条 {l['text'][:32]}{mark}")
    print(f"  期望《{expect_law}》第{expect_art}条 -> {'✅ 命中' if hit else '❌ 未命中'}")

print(f"\n结果：{'✅ 全部通过' if all_pass else '❌ 存在未命中'}")
