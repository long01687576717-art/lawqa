# -*- coding: utf-8 -*-
"""把 data/_cases_raw/ 下的案例原文，解析并生成 data/cases.json。

用法：
    python scripts/build_cases.py

输入：data/_cases_raw/*.txt 或 *.md（每个文件一个案例）
输出：data/cases.json（一个 JSON 数组）

字段标注格式（任选其一，可混用）：
    【标题】案例名称         或    标题：案例名称
    【案号】（2011）xx字第xx号
    【法院】xx人民法院
    【关键词】劳动合同 单方解除
    【案情】……（可多行）
    【裁判要点】……
    【来源】https://……

说明：
  - 每个文件 = 一个案例；同一文件内多次出现同一标签会自动合并。
  - 标题缺失时用文件名兜底；以 "_" 或 "README" 开头的文件会被跳过。
"""
import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA / "_cases_raw"
OUT = DATA / "cases.json"

# 各种可能的标签 → 标准字段名
FIELD_MAP = {
    "title": "title", "标题": "title", "案例名称": "title", "案例标题": "title",
    "court": "court", "法院": "court", "审理法院": "court", "裁判法院": "court",
    "case_no": "case_no", "案号": "case_no", "案件编号": "case_no", "文书案号": "case_no",
    "summary": "summary", "案情": "summary", "案情摘要": "summary", "基本案情": "summary",
    "案件事实": "summary", "案情简介": "summary",
    "ruling": "ruling", "裁判要点": "ruling", "裁判要旨": "ruling", "裁判结果": "ruling",
    "要点": "ruling", "裁判理由": "ruling",
    "keywords": "keywords", "关键词": "keywords",
    "source": "source", "来源": "source", "出处": "source", "链接": "source",
}

# 标记行：以【标签】开头，或 "标签：" 开头
MARKER_RE = re.compile(r"^\s*(?:【([^】]+)】|([^：:\n]{1,16})[:：])\s*(.*)$")


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def parse_case(text: str) -> dict:
    fields = {}
    cur = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = MARKER_RE.match(line)
        if m and (m.group(1) or m.group(2)):
            label = (m.group(1) or m.group(2)).strip()
            rest = (m.group(3) or "").strip()
            key = FIELD_MAP.get(label)
            if key:
                cur = key
                fields.setdefault(key, [])
                if rest:
                    fields[key].append(rest)
                continue
        if cur:
            fields.setdefault(cur, []).append(line)

    out = {}
    for k, parts in fields.items():
        text = "\n".join(p for p in parts if p).strip()
        if text:
            out[k] = text
    return out


def main():
    if not RAW_DIR.exists():
        print(f"[warn] 目录不存在：{RAW_DIR}，请先创建并放入案例文件")
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        return

    files = sorted(
        p for p in RAW_DIR.iterdir()
        if p.suffix.lower() in (".txt", ".md") and not p.name.startswith("_")
    )

    cases = []
    for p in files:
        parsed = parse_case(read_text(p))
        if not parsed.get("title"):
            parsed["title"] = p.stem
        if not any(k in parsed for k in ("summary", "ruling", "case_no")):
            print(f"[skip] 未识别到有效字段，跳过：{p.name}")
            continue
        cases.append(parsed)
        print(f"[ok] {p.name} -> {parsed.get('title', '')}")

    OUT.write_text(
        json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[ok] 已写入 {OUT}，共 {len(cases)} 个案例")


if __name__ == "__main__":
    main()
