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

# 场景标签规则：按顺序匹配（命中即归类）。labels 必须与 llm.py 改写提示中的核心场景一致
SCENARIO_RULES = [
    ("加班费", ["加班", "996", "超时", "延长工作时间", "隐形加班", "工时"]),
    ("未签劳动合同", ["未签订书面劳动合同", "未签劳动合同", "未签书面", "二倍工资", "补签", "倒签"]),
    ("女职工保护", ["女职工", "孕期", "产假", "哺乳期", "生育津贴", "三期"]),
    ("试用期", ["试用期"]),
    ("违法解除", ["违法解除", "末位淘汰", "不能胜任", "单方解除", "无固定期限劳动合同"]),
    ("工伤认定", ["工伤", "上下班途中"]),
    ("拖欠工资", ["拖欠", "恶意欠薪", "拒不支付劳动报酬", "欠薪"]),
    ("社会保险", ["社会保险", "社保", "养老保险", "抚恤金", "生育保险"]),
    ("经济补偿金", ["经济补偿", "协商一致解除", "期满终止", "劳动合同期满"]),
    ("竞业限制", ["竞业限制", "商业秘密"]),
    ("劳务派遣", ["劳务派遣", "派遣", "同工同酬"]),
    ("年休假", ["年休假"]),
]


def classify_scenario(text):
    """根据「标题 + 关键词」文本自动归类场景；无法归类返回「其他」。"""
    for scenario, patterns in SCENARIO_RULES:
        for p in patterns:
            if p in text:
                return scenario
    return "其他"


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
    # 场景标签：根据【标题】+【关键词】自动归类
    out["scenario"] = classify_scenario(" ".join([out.get("title", ""), out.get("keywords", "")]))
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
