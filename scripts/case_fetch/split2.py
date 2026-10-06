"""第二批：公报案例 / 指导案例 / 典型案例汇总页 → 单个案例文件，内容逐字保留。

用法：python split2.py <输出目录> <现有 cases.json> <第一批目录>
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
RAW = HERE / "raw2"
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

SECTIONS = {
    "基本案情": "facts", "处理结果": "result", "裁判结果": "result", "裁判结果及理由": "result",
    "案例分析": "analysis", "裁判理由": "analysis", "典型意义": "significance",
    "裁判要点": "gist", "相关法条": "articles",
}
PARTY = re.compile(r"^(原告|被告|上诉人|被上诉人|再审申请人|申请再审人|被申请人|申请人|第三人|原审|法定代表人|委托|负责人)")


def lines_of(s, start_marker, end_markers):
    a = s.find(start_marker)
    a = a + len(start_marker) if a >= 0 else 0
    b = min([i for i in (s.find(m, a) for m in end_markers) if i > 0] or [len(s)])
    return [l.strip().replace("　", "").replace("​", "").strip()
            for l in s[a:b].split("\n") if l.strip().replace("　", "").replace("​", "").strip()]


def parse_sections(lines):
    sec, cur = {}, None
    for l in lines:
        key = SECTIONS.get(re.sub(r"^（[一二三四五六七八九十]+）", "", l.strip("【】 ")))
        if key:
            cur = key
            sec.setdefault(key, [])
            continue
        if cur:
            sec[cur].append(l)
    return {k: "\n".join(v) for k, v in sec.items()}


def parse_gongbao(s):
    all_lines = lines_of(s, "", ["法律声明"])
    k = next(i for i, l in enumerate(all_lines) if l == "案例" and i > 0 and all_lines[i - 1] == ">")
    lines = all_lines[k + 1:]
    title, i = "", 0
    while i < len(lines) and not lines[i].startswith("【") and not PARTY.match(lines[i]):
        title += lines[i]
        i += 1
    gist = []
    if i < len(lines) and lines[i].startswith("【"):
        rest = re.sub(r"^【[^】]+】", "", lines[i]).strip()
        if rest:
            gist.append(rest)
        i += 1
        while i < len(lines) and not PARTY.match(lines[i]):
            gist.append(lines[i])
            i += 1
    facts, analysis, in_analysis = [], [], False
    for l in lines[i:]:
        if not in_analysis and re.match(r"^[^，。]{0,40}?认为[：:，,]", l):
            in_analysis = True
        (analysis if in_analysis else facts).append(l)
    body = "\n".join(lines)
    m = (re.search(r"([^\s，。、：:（）]{2,30}?人民法院)(?:一审|二审|再审)?(?:经审理)?查明", body)
         or re.search(r"([^\s，。、：:（）]{2,30}?人民法院)认为", body)
         or re.search(r"向([^\s，。、]{2,30}?人民法院)提起", body))
    return {"title": title, "gist": "\n".join(gist), "facts": "\n".join(facts),
            "analysis": "\n".join(analysis), "court": m.group(1) if m else ""}


def parse_guiding(s):
    lines = lines_of(s, "打印本页", ["责任编辑"])
    no = lines[0]
    title, i = "", 1
    while i < len(lines) and not lines[i].startswith("（"):
        title += lines[i]
        i += 1
    kw = next((re.sub(r"^关键词\s*", "", l) for l in lines if l.startswith("关键词")), "")
    sec = parse_sections(lines)
    res = sec.get("result", "")
    m = re.search(r"^([^，。：；]*?法院)于[^。]*?作出([（(]\d{4}[）)][^号]+号)", res)
    date = re.search(r"(\d{4}年\d{1,2}月\d{1,2}日)发布", "".join(lines[:i + 2]))
    return {"title": title, "keywords": kw, "facts": sec.get("facts", ""), "result": res,
            "gist": sec.get("gist", ""), "analysis": sec.get("analysis", ""),
            "case_no": m.group(2) if m else "", "court": m.group(1) if m else "",
            "_no": no, "_date": date.group(1) if date else ""}


def split_batch(s):
    lines = lines_of(s, "打印本页", ["责任编辑"])
    head = re.compile(r"^案例(?:[一二三四五六七八九十]+|\d+)(?:[\.\s](.*))?$")
    blocks, cur = [], None
    for l in lines:
        if head.match(l):
            cur = [l]
            blocks.append(cur)
        elif cur is not None:
            cur.append(l)
    out = []
    for b in blocks:
        if not any(re.sub(r"^（[一二三四五六七八九十]+）", "", x.strip("【】")) == "基本案情" for x in b):
            continue
        t = head.match(b[0]).group(1) or ""
        parts, i = [t.strip()] if t.strip() else [], 1
        while i < len(b) and re.sub(r"^（[一二三四五六七八九十]+）", "", b[i].strip("【】")) not in SECTIONS:
            parts.append(b[i])
            i += 1
        out.append(("".join(parts), parse_sections(b[i:])))
    return out


def write_case(name, f):
    order = [("标题", "title"), ("案号", "case_no"), ("法院", "court"), ("关键词", "keywords"),
             ("案情", "facts"), ("裁判结果", "result"), ("裁判要点", "gist"), ("案例分析", "analysis"),
             ("典型意义", "significance"), ("来源", "source")]
    long_keys = ("facts", "result", "gist", "analysis", "significance")
    parts = []
    for label, key in order:
        v = (f.get(key) or "").strip()
        if v:
            parts.append(f"【{label}】\n{v}" if key in long_keys else f"【{label}】{v}")
    (OUT / name).write_text("\n".join(parts) + "\n", encoding="utf-8")


def safe(s, n=40):
    return re.sub(r'[\\/:*?"<>|\s，。？、“”（）()]', "", s)[:n]


def date_of(s):
    m = re.search(r"发布时间：(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else ""


def case_name(title):
    """取标题中以「案」结尾的案名部分（标题可能是「要旨——案名」或「案名——要旨」）。"""
    parts = [x.strip() for x in title.split("——")]
    return next((x for x in parts if x.endswith("案")), parts[-1])


def norm_name(t):
    return re.sub(r"[\s（）()、，]", "", t)


# 第一批已收的案名：跳过；现有库的案名：不跳过（要用原文版替换），只记录对应关系
batch1 = {norm_name(case_name(p.read_text(encoding="utf-8").split("\n", 1)[0].replace("【标题】", "")))
          for p in Path(sys.argv[3]).glob("*.txt")}
existing = json.load(open(sys.argv[2], encoding="utf-8"))
PC_ORG = {
    "pc_507291": ("服务期典型案例", "最高人民法院 事业单位工作人员脱产参加全日制学历教育后违反服务期约定纠纷典型案例"),
    "pc_463871": ("新就业形态典型案例", "最高人民法院 新就业形态劳动者权益保障典型案例"),
    "pc_453301": ("恶意欠薪犯罪典型案例", "最高人民法院、人力资源社会保障部 依法惩治恶意欠薪犯罪典型案例"),
    "pc_gb1069b6": ("工伤保险行政典型案例", "最高人民法院公报 最高人民法院发布工伤保险行政纠纷典型案例"),
}
SKIP_PC = {"pc_451201", "pc_484861", "pc_gd1842476"}  # 一函两书（非裁判案例）、广东法院批次（留待后续批次）

written, skipped, replaced, done = 0, [], [], set()
for p in sorted(RAW.glob("*.txt")):
    raw = p.read_text(encoding="utf-8")
    url = raw.split("\n", 1)[0].strip()
    kind = p.stem.split("_")[0]
    items = []
    if kind == "gb":
        f = parse_gongbao(raw)
        f["source"] = f"最高人民法院公报案例 {url}"
        items.append((f"公报案例_{safe(f['title'])}.txt", f))
    elif kind == "zd":
        f = parse_guiding(raw)
        f["source"] = f"最高人民法院 {f['_no']}（{f['_date']}发布）{url}"
        items.append((f"{f['_no']}_{safe(f['title'])}.txt", f))
    elif kind == "pc":
        if p.stem in SKIP_PC:
            continue
        short, org = PC_ORG[p.stem]
        date = date_of(raw)
        for n, (t, sec) in enumerate(split_batch(raw), 1):
            if p.stem == "pc_463871" and "劳动争议" not in t:
                continue  # 仅收劳动争议案，保险/侵权纠纷不收
            f = dict(sec, title=t, source=f"{org}{'（' + date + ' 发布）' if date else ''} {url}")
            items.append((f"{short}_{n:02d}_{safe(case_name(t))}.txt", f))
    for name, f in items:
        key = norm_name(case_name(f["title"]))
        if key in batch1 or key in done:
            skipped.append(f["title"])
            continue
        done.add(key)
        hit = [i for i, e in enumerate(existing, 1) if norm_name(e["title"].split("（")[0]) in key or key in norm_name(e["title"])]
        if hit:
            replaced.append(f"现有#{hit[0]}《{existing[hit[0]-1]['title']}》 → {name}")
        write_case(name, f)
        written += 1
        print("[ok]", name)

print(f"\n共写出 {written} 个；与第一批/本批重复跳过 {len(skipped)} 个：")
for s in skipped:
    print("  -", s)
print(f"\n可替换现有案例 {len(replaced)} 个：")
for r in replaced:
    print("  *", r)
