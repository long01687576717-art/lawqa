"""第四批（补缺口）：省级人社/法院联合典型案例 + 单篇官方案例 → 单个案例文件，内容逐字保留。

用法：python split4.py <输出目录> <现有案例目录>
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
RAW = HERE / "raw4"
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

SECTIONS = {
    "基本案情": "facts", "案情": "facts", "案情简介": "facts", "案情剧场": "facts",
    "申请人请求": "claim", "原告诉讼请求": "claim",
    "处理结果": "result", "裁判结果": "result", "审理": "result", "裁决要旨": "result", "裁判要旨": "result", "法院认为": "result",
    "案例分析": "analysis", "评析": "analysis", "案件评析": "analysis",
    "典型意义": "significance", "关键词": "keywords", "关联索引": "index",
}

# 页面 → (文件名前缀, 发布机构与日期, 类型)
SOURCES = {
    "gz_2025": ("贵州高院人社2025", "贵州省高级人民法院、贵州省人力资源和社会保障厅 劳动争议典型案例（2025-04-30）", "batch_cn"),
    "jl_2024": ("吉林人社高院2024", "吉林省人力资源和社会保障厅、吉林省高级人民法院 劳动人事争议典型案例（2024-12-26）", "batch_num"),
    "sx_1": ("陕西人社高院第一批", "陕西省人力资源和社会保障厅、陕西省高级人民法院 第一批劳动人事争议典型案例（2023-12-20）", "batch_num"),
    "fj_2023": ("福建人社高院2023", "福建省人力资源和社会保障厅、福建省高级人民法院 劳动人事争议典型案例（2023-08）", "batch_pdf"),
    "bj_deposit": ("北京人社典型案例", "北京市人力资源和社会保障局 劳动人事争议典型案例（2022-11-17）", "single"),
    "qd_dispatch": ("青岛人社典型案例", "青岛市人力资源和社会保障局 劳动关系典型案例（2022-11-30）", "single"),
    "hbv_gl": ("南京鼓楼法院", "南京市鼓楼区人民法院 法院动态（2025-07-07）", "single"),
}
TITLES = {  # 单篇案例的原标题（取自页面标题行，未改写）
    "bj_deposit": "用人单位不得以任何理由收取劳动者财物",
    "qd_dispatch": "派遣员工被退回，无工作期间也应支付报酬",
    "hbv_gl": "“我代码写完了，却输给了乙肝抗体……”",
}
END = ["法律小贴士", "中华人民共和国人力资源和社会保障部 |", "各区市人社局", "政府网站标识码", "【打印本页】", "手机扫码查看", "相关信息", "[关闭]", "上一篇："]


def clean(l):
    return l.replace("　", "").replace("​", "").replace("\xa0", " ").strip()


def sec_key(l):
    return SECTIONS.get(l.strip().strip("【】").strip()) or inline_sec(l)[0]


def inline_sec(l):
    """「【案情】正文……」这类标记与正文写在同一行的情况，返回 (段名键, 同行正文)。"""
    m = re.match(r"^【([^】]{1,6})】(.+)$", l.strip())
    if m and m.group(1) in SECTIONS:
        return SECTIONS[m.group(1)], m.group(2).strip()
    return None, ""


def lines_of(stem):
    raw = (RAW / f"{stem}.txt").read_text(encoding="utf-8")
    url, body = raw.split("\n", 1)
    lines = [clean(l) for l in body.split("\n")]
    lines = [l for l in lines if l and not re.fullmatch(r"—\s*\d+\s*—", l)]  # 去掉 PDF 页码
    return url.strip(), lines


def parse_sections(lines, join=""):
    sec, cur = {}, None
    for l in lines:
        k = sec_key(l)
        if k:
            cur = k
            sec.setdefault(k, [])
            rest = inline_sec(l)[1]
            if rest:
                sec[k].append(rest)
            continue
        if any(l.startswith(e) for e in END):
            break
        if l.startswith("（承办法官"):
            continue  # 署名行，不属于正文
        if cur:
            sec[cur].append(l)
    return {k: join.join(v).strip() for k, v in sec.items()}


def split_batch(lines, head_re, join="\n"):
    blocks, cur = [], None
    for l in lines:
        if re.match(head_re, l):
            cur = [l]
            blocks.append(cur)
        elif cur is not None:
            cur.append(l)
    out = []
    for b in blocks:
        if not any(sec_key(x) == "facts" for x in b):
            continue  # 目录
        i, parts = 1, [re.sub(head_re, "", b[0]).strip()]
        while i < len(b) and not sec_key(b[i]):
            parts.append(b[i])
            i += 1
        out.append(("".join(p for p in parts if p), parse_sections(b[i:], join)))
    return out


def write_case(name, f):
    order = [("标题", "title"), ("案号", "case_no"), ("法院", "court"), ("关键词", "keywords"),
             ("案情", "facts"), ("裁判结果", "result"), ("案例分析", "analysis"),
             ("典型意义", "significance"), ("来源", "source")]
    long_keys = ("facts", "result", "analysis", "significance")
    parts = []
    for label, key in order:
        v = (f.get(key) or "").strip()
        if v:
            parts.append(f"【{label}】\n{v}" if key in long_keys else f"【{label}】{v}")
    (OUT / name).write_text("\n".join(parts) + "\n", encoding="utf-8")


def safe(s, n=34):
    return re.sub(r'[\\/:*?"<>|\s，。？、“”（）()——…]', "", s)[:n]


def norm(t):
    return re.sub(r"\s", "", t)


existing = [norm(p.read_text(encoding="utf-8")) for p in Path(sys.argv[2]).glob("*.txt")]
written, skipped = 0, []
for stem, (short, org, kind) in SOURCES.items():
    url, lines = lines_of(stem)
    if kind == "single":
        start = next(i for i, l in enumerate(lines) if sec_key(l) == "facts")
        items = [(TITLES[stem], parse_sections(lines[start:], "\n"))]
    elif kind == "batch_cn":
        items = split_batch(lines, r"^案例[一二三四五六七八九十]+$")
    elif kind == "batch_num":
        items = split_batch(lines, r"^案例\s*\d+[\.：:]?")
    else:  # batch_pdf：PDF 折行，段内拼接；标题后的「（该案例由…提供）」不计入标题
        items = split_batch(lines, r"^案例\s*\d+\.", join="")
        items = [(re.sub(r"（该[\s\S]*?提供）$", "", t), s) for t, s in items]
    for n, (title, sec) in enumerate(items, 1):
        facts = sec.get("facts", "")
        if sec.get("claim"):
            facts += "\n请求：" + sec["claim"]
        f = dict(sec, title=title, facts=facts, source=f"{org} {url}")
        # 吉林批次：典型意义末尾附「［××仲裁委员会 ××号］」，提取为法院/仲裁机构与案号
        m = re.search(r"［(\S+?(?:委员会|法院))\s*(\S+号)］\s*$", f.get("significance", ""))
        if m:
            f["court"], f["case_no"] = m.group(1), m.group(2)
        plain = norm(facts)
        if any(any(plain[k:k + 30] in t for k in range(0, max(1, len(plain) - 30), 40)) for t in existing):
            skipped.append(f"{short}#{n} {title}")
            continue
        name = f"{short}_{n:02d}_{safe(title)}.txt" if kind != "single" else f"{short}_{safe(title)}.txt"
        write_case(name, f)
        written += 1
        print("[ok]", name)
print(f"\n共写出 {written} 个；与已收案例重复跳过 {len(skipped)} 个：")
for s in skipped:
    print("  -", s)
