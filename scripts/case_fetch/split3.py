"""第三批：省级人社/法院典型案例 + 最高法零散案例 → 单个案例文件，内容逐字保留。

用法：python split3.py <输出目录> <已收案例目录1> [<已收案例目录2> ...]
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
RAW = HERE / "raw3"
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

SECTIONS = {
    "基本案情": "facts", "案情简介": "facts",
    "申请人请求": "claim", "原告诉讼请求": "claim", "仲裁请求": "claim",
    "处理结果": "result", "裁判结果": "result", "裁判结果及理由": "result", "裁决结果": "result",
    "案例分析": "analysis", "案例评析": "analysis", "裁判理由": "analysis",
    "典型意义": "significance", "仲裁委员会提示": "significance", "仲裁委提示": "significance",
    "裁判要旨": "gist", "裁判要点": "gist", "关联索引": "index",
}

# 页面 → (文件名前缀, 发布机构, 案例标题正则, 正文结束标记, 是否只收劳动类)
BATCHES = {
    "bj_2025": ("北京仲裁2025", "北京市人力资源和社会保障局 2025年北京市劳动人事争议仲裁十大典型案例（2025-12-26）"),
    "bj_2024": ("北京仲裁2024", "北京市人力资源和社会保障局 2024年北京市劳动人事争议仲裁十大典型案例（2024-12-17）"),
    "bj_2023": ("北京仲裁2023", "北京市人力资源和社会保障局 2023年北京市劳动人事争议仲裁典型案例（2023-12-29）"),
    "bj_2022": ("北京仲裁2022", "北京市人力资源和社会保障局 2022年北京市劳动人事争议仲裁典型案例（2022-12-22）"),
    "bj_2021": ("北京仲裁2021", "北京市人力资源和社会保障局 2021年北京市劳动人事争议仲裁十大典型案例（2021-11-05）"),
    "tj_2024": ("天津人社高院2024", "天津市人力资源和社会保障局、天津市高级人民法院 劳动人事争议典型案例（2024-06-06）"),
    "hn_190441": ("河南高院人社2022", "河南省高级人民法院、河南省人力资源和社会保障厅 十件劳动争议典型案例（2022-04-29）"),
    "gd_1842476": ("广东法院2024", "广东省高级人民法院 劳动争议典型案例（2024-04-30）"),
    "zgf_484101": ("最高法核心价值观第四批", "最高人民法院 第四批人民法院大力弘扬社会主义核心价值观典型民事案例（2025-12-16）"),
    "zgf_446321": ("入库参考案例", "最高人民法院 入库参考案例"),
}
HEAD = re.compile(r"^(?:案例\s*(\d+|[一二三四五六七八九十]+)\s*[\.．：:]?\s*|(\d{2})、)(.*)$")
END = ["手机扫码查看", "〖关闭窗口〗", "返回顶部", "责任编辑"]
LABOR = re.compile(r"劳动|录用|用人单位|工伤|工资|职工")


def clean(l):
    return l.replace("　", "").replace("​", "").replace("\xa0", " ").strip()


def body_lines(raw):
    lines = [clean(l) for l in raw.split("\n")[1:]]
    lines = [l for l in lines if l]
    end = next((i for i, l in enumerate(lines) if any(l.startswith(m) for m in END)), len(lines))
    return lines[:end]


def sec_key(l):
    return SECTIONS.get(re.sub(r"^（[一二三四五六七八九十]+）", "", l.strip("【】 ")))


def parse_sections(lines):
    sec, cur = {}, None
    for l in lines:
        key = sec_key(l)
        if key:
            cur = key
            sec.setdefault(key, [])
            continue
        if cur:
            sec[cur].append(l)
    return {k: "\n".join(v) for k, v in sec.items()}


def split_batch(lines):
    blocks, cur = [], None
    for l in lines:
        if HEAD.match(l):
            cur = [l]
            blocks.append(cur)
        elif cur is not None:
            cur.append(l)
    out = []
    for b in blocks:
        if not any(sec_key(x) == "facts" for x in b):
            continue  # 目录行
        parts, i = [HEAD.match(b[0]).group(3).strip()], 1
        while i < len(b) and not sec_key(b[i]):
            parts.append(b[i])
            i += 1
        title = "".join(p for p in parts if p)
        out.append((title, parse_sections(b[i:])))
    return out


def parse_ruku(lines):
    i = lines.index(next(l for l in lines if l.startswith("入库编号")))
    title = "".join(lines[i - 2:i]) if lines[i - 1].startswith("——") else lines[i - 1]
    kw = re.sub(r"^关键词\s*", "", next((l for l in lines if l.startswith("关键词")), ""))
    sec = parse_sections(lines[i:])
    idx = sec.pop("index", "")
    m = re.search(r"([^：\n]*?人民法院)([（(]\d{4}[）)][^号]+号)", idx.split("\n")[-1] if idx else "")
    return title, dict(sec, keywords=kw, case_no=m.group(2) if m else "", court=m.group(1) if m else "",
                       _no=lines[i])


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


def safe(s, n=36):
    return re.sub(r'[\\/:*?"<>|\s，。？、“”（）()——]', "", s)[:n]


def norm(t):
    return re.sub(r"\s|　|​|\xa0", "", t)


# 已收案例的案情原文：用 30 字片段比对，发现跨来源转载的同一案例
seen_text = [norm(p.read_text(encoding="utf-8")) for d in sys.argv[2:] for p in Path(d).glob("*.txt")]

written, skipped = 0, []
for stem, (short, org) in BATCHES.items():
    raw = (RAW / f"{stem}.txt").read_text(encoding="utf-8")
    url = raw.split("\n", 1)[0].strip()
    lines = body_lines(raw)
    if stem == "zgf_446321":
        title, f = parse_ruku(lines)
        items = [(title, f)]
        org = f"{org}（{f.pop('_no')}）"
    else:
        items = split_batch(lines)
    for n, (title, sec) in enumerate(items, 1):
        if stem == "zgf_484101" and not LABOR.search(title):
            continue  # 核心价值观批次只收劳动类案例
        facts = sec.get("facts", "")
        if sec.get("claim"):
            facts += "\n请求：" + sec["claim"]
        f = dict(sec, title=title, facts=facts, source=f"{org} {url}")
        plain = norm(facts)
        if any(any(plain[k:k + 30] in t for k in range(0, max(1, len(plain) - 30), 40)) for t in seen_text):
            skipped.append(f"{short}#{n} {title}")
            continue
        name = f"{short}_{n:02d}_{safe(title)}.txt"
        write_case(name, f)
        written += 1
        print("[ok]", name)

print(f"\n共写出 {written} 个；与已收案例重复跳过 {len(skipped)} 个：")
for s in skipped:
    print("  -", s)
