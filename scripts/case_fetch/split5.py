"""第五批（补缺口，原文抓取见 fetch5.py，存于 raw6/）：按起止标记从官方页面原文中截取各段，逐字写成案例文件。"""
import re
import sys
from pathlib import Path

RAW = Path("raw6")
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
EXIST = Path(sys.argv[2])


def lines(stem):
    url, body = (RAW / f"{stem}.txt").read_text(encoding="utf-8").split("\n", 1)
    ls = [l.replace("\u3000", " ").replace("\xa0", " ").strip() for l in body.split("\n")]
    return url.strip(), [l for l in ls if l]


def cut(ls, start, end, skip=()):
    """取 start 行之后、end 行之前的段落（start/end 为整行或行首匹配）。"""
    i = next(k for k, l in enumerate(ls) if l == start or l.startswith(start)) + 1
    j = next(k for k in range(i, len(ls)) if ls[k] == end or ls[k].startswith(end)) if end else len(ls)
    return "\n".join(l for l in ls[i:j] if l not in skip)


CASES = []

url, L = lines("qd_layoff")
CASES.append(dict(name="青岛人社典型案例_用人单位滥用经济性裁员构成违法解除劳动合同", title="用人单位滥用经济性裁员构成违法解除劳动合同",
    facts=cut(L, "【案情简介】", "【裁决结果】"), result=cut(L, "【裁决结果】", "【案件评析】"),
    analysis=cut(L, "【案件评析】", "中华人民共和国人力资源和社会保障部 |"),
    tags="单位解除合同 经济补偿与赔偿金", source=f"青岛市人力资源和社会保障局 劳动关系典型案例（2018-12-17） {url}"))

url, L = lines("ky_layoff")
CASES.append(dict(name="开原法院案例评析_隔离期间遭裁员法院这样判了", title="隔离期间遭裁员？法院这样判了", court="杭州市萧山区人民法院",
    facts=cut(L, "案情回顾", "萧山法院审理后认为"), result=cut(L, "“我们与胡某解除劳动关系", "【法官说法】"),
    analysis=cut(L, "杭州市萧山区人民法院民四庭副庭长", "【代表委员点评】"),
    tags="单位解除合同 经济补偿与赔偿金 休息休假",
    source=f"辽宁省开原市人民法院 案例评析（2022-03-25，来源：最高人民法院新闻局 人民法院新闻传媒总社） {url}"))

url, L = lines("dp_resign")
CASES.append(dict(name="深圳大鹏新区典型案例_提离职未满30天公司提前让我走这合法吗", title="提离职未满30天，公司提前让我走，这合法吗？",
    facts=cut(L, "案情摘要：", "案情分析"), analysis=cut(L, "案情分析", "处理结果："), result=cut(L, "处理结果：", "转载来源："),
    tags="劳动者解除与离职 离职手续与证明",
    source=f"深圳市大鹏新区 根治欠薪进行时 典型案例（2023-02-10，信息来源：深圳人社） {url}"))

url, L = lines("zjzy_retire")
CASES.append(dict(name="镇江中院_已达法定退休年龄但未享受养老保险待遇能否认定劳动关系", title="已达法定退休年龄但未享受养老保险待遇，能否认定劳动关系？", court="镇江经开区法院",
    facts=cut(L, "基本案情", "法院判决"), result=cut(L, "法院判决", "裁判观点"),
    analysis=cut(L, "裁判观点", "典型意义"), significance=cut(L, "典型意义", "责任编辑："),
    tags="劳动关系认定 特殊用工 工时与加班", source=f"江苏省镇江市中级人民法院 基层快讯（2025-02-08） {url}"))

url, L = lines("cj_hpf")
CASES.append(dict(name="中国就业网案例分析_补缴住房公积金的仲裁请求是否支持", title="补缴住房公积金的仲裁请求是否支持",
    facts=cut(L, "基本案情", "申请人请求") + "\n请求：" + cut(L, "申请人请求", "裁决结果"),
    result=cut(L, "裁决结果", "案件评析"), analysis=cut(L, "案件评析", "住房"),
    tags="住房公积金 仲裁时效与举证",
    source=f"中国就业网（人力资源和社会保障部中国就业培训技术指导中心主办） 案例分析（2020-05-28） {url}"))

url, L = lines("yc_hpf")
f = cut(L, "1.基本案情：", "2.行政执法人员释法：").split("\n")
CASES.append(dict(name="宜昌公积金中心以案释法_单位应当为全体在职职工缴存住房公积金", title="宜昌住房公积金中心以案释法典型案例（十）单位应当为全体在职职工缴存住房公积金",
    facts="\n".join(f[:-1]), result=f[-1], analysis=cut(L, "2.行政执法人员释法：", "（案例提供：中心执法科）"),
    tags="住房公积金", source=f"宜昌住房公积金中心 维权案例（2023-09-27） {url}"))

url, L = lines("wh_batch")
WH = [("一", "入职时超过法定退休年龄的劳动者与用人单位之间不能形成劳动关系", "劳动关系认定 特殊用工"),
      ("二", "社保挂靠属于虚构劳动关系的违法行为", "社会保险 劳动关系认定"),
      ("三", "外卖骑手与网络平台劳动关系的认定", "平台用工 劳动关系认定"),
      ("四", "如何认定网约货车司机与物流公司是否存在劳动关系？", "平台用工 劳动关系认定"),
      ("五", "“三期”女职工严重违反规章制度亦可被解除劳动合同", "女职工保护 规章制度与违纪 单位解除合同"),
      ("六", "劳动者是否违反公司规章制度的认定", "规章制度与违纪 单位解除合同 仲裁时效与举证"),
      ("七", "补缴社会保险费、住房公积金不属于劳动争议", "住房公积金 社会保险")]
nums = "一二三四五六七"
for n, title, tags in WH:
    s = L.index(f"案例{n}", L.index("●案例七 补缴社会保险费、住房公积金不属于劳动争议") + 1)
    nxt = f"案例{nums[nums.index(n) + 1]}" if n != "七" else "【关闭】"
    e = L.index(nxt, s + 1)
    B = L[s:e]
    CASES.append(dict(name=f"威海中院人社典型案例2024_{nums.index(n) + 1:02d}_{re.sub(r'[“”？、，]', '', title)[:30]}", title=title,
        facts=cut(B, "基本案情", "裁判结果"), result=cut(B, "裁判结果", "裁判要旨"),
        gist=cut(B, "裁判要旨", "典型意义"), significance=cut(B, "典型意义", None),
        tags=tags, source=f"威海市中级人民法院、威海市人力资源和社会保障局 劳动争议典型案例（2024-05-02） {url}"))

norm = lambda t: re.sub(r"\s", "", t)
existing = [norm(p.read_text(encoding="utf-8")) for p in EXIST.glob("*.txt")]
raw_all = {stem: norm((RAW / f"{stem}.txt").read_text(encoding="utf-8")) for stem in ("qd_layoff", "ky_layoff", "dp_resign", "zjzy_retire", "cj_hpf", "yc_hpf", "wh_batch")}
ORDER = [("标题", "title"), ("法院", "court"), ("案情", "facts"), ("裁判结果", "result"), ("裁判要点", "gist"),
         ("案例分析", "analysis"), ("典型意义", "significance"), ("标签", "tags"), ("来源", "source")]
LONG = {"facts", "result", "gist", "analysis", "significance"}
for c in CASES:
    # 逐字校验：每段每行都必须能在官方原文中找到（「请求：」为沿用的段名前缀）
    for k in LONG:
        if not c.get(k):
            continue
        for seg in (c.get(k) or "").split("\n"):
            seg = norm(seg.removeprefix("请求："))
            assert seg and any(seg in t for t in raw_all.values()), (c["title"], k, seg[:30])
    plain = norm(c["facts"])
    dup = any(any(plain[i:i + 30] in t for i in range(0, max(1, len(plain) - 30), 40)) for t in existing)
    if dup:
        print("[重复，跳过]", c["title"]); continue
    parts = [f"【{lab}】\n{c[k].strip()}" if k in LONG else f"【{lab}】{c[k].strip()}" for lab, k in ORDER if c.get(k)]
    (OUT / f"{c['name']}.txt").write_text("\n".join(parts) + "\n", encoding="utf-8")
    print("[ok]", c["name"], {k: len(c.get(k) or "") for k in ("facts", "result", "gist", "analysis", "significance")})
