"""把 raw/*.txt（官网页面纯文本）按原文段落拆成单个案例，内容逐字保留。"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

# 页面 id → (批次简称, 发布机构/名称)
BATCHES = {
    "319151": ("人社最高法第二批", "人力资源社会保障部、最高人民法院 劳动人事争议典型案例（第二批）"),
    "401172": ("人社最高法第三批", "人力资源社会保障部、最高人民法院 劳动人事争议典型案例（第三批）"),
    "462311": ("人社最高法第四批", "人力资源社会保障部、最高人民法院 劳动人事争议典型案例（第四批）"),
    "423922": ("涉欠薪典型案例", "最高人民法院、人力资源社会保障部、中华全国总工会 涉欠薪纠纷典型案例"),
    "431252": ("最高法劳动争议典型案例2024", "最高人民法院 劳动争议典型案例"),
    "472681": ("最高法劳动争议典型案例2025", "最高人民法院 劳动争议典型案例"),
    "450721": ("指导性案例", "最高人民法院 指导性案例237号"),
    "450731": ("指导性案例", "最高人民法院 指导性案例238号"),
    "450741": ("指导性案例", "最高人民法院 指导性案例239号"),
    "450751": ("指导性案例", "最高人民法院 指导性案例240号"),
}

SECTIONS = {
    "基本案情": "facts", "申请人请求": "claim", "原告诉讼请求": "claim", "原告请求": "claim",
    "处理结果": "result", "裁判结果": "result", "裁决结果": "result",
    "案例分析": "analysis", "裁判理由": "analysis",
    "典型意义": "significance", "裁判要点": "gist", "相关法条": "articles",
}
HEAD_A = re.compile(r"^案例(\d+)\.(.*)$")
HEAD_B = re.compile(r"^案例([一二三四五六七八九十]+)$")


def clean_lines(s):
    a, b = s.find("打印本页"), s.find("责任编辑")
    body = s[a + 4:b if b > 0 else None]
    return [l.strip().replace("　", "").strip() for l in body.split("\n") if l.strip()]


def date_of(s):
    m = re.search(r"发布时间：(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else ""


def parse_sections(lines):
    sec, cur = {}, None
    for l in lines:
        key = SECTIONS.get(l.strip("【】 "))
        if key:
            cur = key
            sec.setdefault(key, [])
            continue
        if cur:
            sec[cur].append(l)
    return {k: "\n".join(v) for k, v in sec.items()}


def split_batch(lines):
    """按「案例N.」或「案例一」切块，只保留含「基本案情」的块（跳过目录）。"""
    blocks, cur = [], None
    for l in lines:
        if HEAD_A.match(l) or HEAD_B.match(l):
            cur = [l]
            blocks.append(cur)
        elif cur is not None:
            cur.append(l)
    out = []
    for b in blocks:
        if not any(x.strip("【】") == "基本案情" for x in b):
            continue
        m = HEAD_A.match(b[0])
        title_parts = [m.group(2)] if m and m.group(2) else []
        i = 1
        while i < len(b) and b[i].strip("【】") not in SECTIONS:
            title_parts.append(b[i])
            i += 1
        out.append(("".join(title_parts).strip(), b[i:]))
    return out


def parse_guiding(lines):
    # 标题可能跨多行，取「指导性案例N号」之后、「（最高人民法院审判委员会…」之前的各行
    title, i = "", 1
    while i < len(lines) and not lines[i].startswith("（"):
        title += lines[i]
        i += 1
    kw = next((l.replace("关键词", "", 1).strip() for l in lines if l.startswith("关键词")), "")
    sec = parse_sections(lines)
    # 案号、法院：从「裁判结果」原文中提取第一处
    res = sec.get("result", "")
    m = re.search(r"^(.*?人民法院)于.*?作出(（\d{4}）[^号]+号)", res)
    return title, kw, sec, (m.group(2) if m else ""), (m.group(1) if m else "")


def write_case(name, fields):
    order = [("标题", "title"), ("案号", "case_no"), ("法院", "court"), ("关键词", "keywords"),
             ("案情", "facts"), ("裁判结果", "result"), ("裁判要点", "gist"), ("案例分析", "analysis"),
             ("典型意义", "significance"), ("来源", "source")]
    parts = []
    for label, key in order:
        v = fields.get(key, "").strip()
        if v:
            parts.append(f"【{label}】\n{v}" if "\n" in v or key in ("facts", "result", "gist", "analysis", "significance") else f"【{label}】{v}")
    (OUT / name).write_text("\n".join(parts) + "\n", encoding="utf-8")


def safe(s, n=40):
    return re.sub(r'[\\/:*?"<>|\s，。？、“”（）()]', "", s)[:n]


existing_full = json.load(open(sys.argv[2], encoding="utf-8"))
for e in existing_full:
    e["_text"] = re.sub(r"\s", "", e.get("summary", "") + e.get("ruling", ""))
dups, count = [], 0
for pid, (short, org) in BATCHES.items():
    raw = (HERE / "raw" / f"{pid}.txt").read_text(encoding="utf-8")
    url = raw.split("\n", 1)[0].strip()
    date = date_of(raw)
    lines = clean_lines(raw)
    if short == "指导性案例":
        title, kw, sec, case_no, court = parse_guiding(lines)
        items = [(title, sec, kw, case_no, court)]
    else:
        items = [(t, parse_sections(b), "", "", "") for t, b in split_batch(lines)]
    for n, (title, sec, kw, case_no, court) in enumerate(items, 1):
        facts = sec.get("facts", "")
        if sec.get("claim"):
            facts += "\n请求：" + sec["claim"]
        f = {
            "title": title, "case_no": case_no, "court": court, "keywords": kw, "facts": facts,
            "result": sec.get("result", ""), "gist": sec.get("gist", ""),
            "analysis": sec.get("analysis", ""), "significance": sec.get("significance", ""),
            "source": f"{org}（{date} 发布）{url}",
        }
        # 与现有案例库去重：案情原文中任意 25 字片段出现在现有案例的案情/裁判要点中即视为重复
        plain = re.sub(r"\s", "", facts)
        dup = next((e["title"] for e in existing_full
                    if any(plain[k:k + 25] in e["_text"] for k in range(0, max(1, len(plain) - 25), 15))), None)
        if dup:
            dups.append(f"{short}#{n} {title} ≈ 现有《{dup}》")
            continue
        tail = title.split("——")[-1].split("──")[-1]
        name = f"{short}_{n:02d}_{safe(tail)}.txt" if short != "指导性案例" else f"指导性案例{org[-4:-1]}_{safe(title)}.txt"
        write_case(name, f)
        count += 1
        print(f"[ok] {name}")

print(f"\n共写出 {count} 个；与现有案例重复跳过 {len(dups)} 个：")
for d in dups:
    print("  -", d)
