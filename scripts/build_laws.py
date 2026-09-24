# -*- coding: utf-8 -*-
"""把维基文库抓取的原始 wikitext 解析为结构化 laws.json。

用法：
    python scripts/build_laws.py

输入：data/_raw_labor.txt、data/_raw_contract.txt（wikitext 原文）
输出：data/laws.json
"""
import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

# (wikitext 文件名, 法律名称, 来源链接)
LAWS = [
    ("_raw_labor.txt", "中华人民共和国劳动法", "https://zh.wikisource.org/wiki/中华人民共和国劳动法_(2018年)"),
    ("_raw_contract.txt", "中华人民共和国劳动合同法", "https://zh.wikisource.org/wiki/中华人民共和国劳动合同法_(2012年)"),
]


def clean_inline(s: str) -> str:
    """去除 wikitext 的行内标记，返回纯文本。"""
    # 去除 <onlyinclude> / </onlyinclude> 等标签
    s = re.sub(r"</?onlyinclude>", "", s)
    # 维基链接 [[目标|显示文字]] -> 显示文字；[[目标]] -> 目标
    s = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", s)
    # 模板 {{gap}}、{{...}}
    s = re.sub(r"\{\{gap\}\}", "", s)
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    # 粗体 '''...'''
    s = s.replace("'''", "")
    # 全角空格开头
    s = s.strip()
    return s


def parse_wikitext(text: str, law: str, source: str):
    articles = []
    chapter = ""
    current = None

    def flush():
        nonlocal current
        if current is not None:
            current["text"] = current["text"].strip()
            if current["text"]:
                articles.append(current)
            current = None

    for raw in text.splitlines():
        line = raw.rstrip()

        # 章标题：== 第X章　标题 ==
        m = re.match(r"^==\s*(第[一二三四五六七八九十百零]+章)[\s　]*(.*?)\s*==$", line)
        if m:
            title = (m.group(2) or "").strip()
            chapter = m.group(1) + ("　" + title if title else "")
            continue

        # 条文开头：{{gap}}'''第X条'''　内容
        m = re.match(r"^.*'''第(.+?)条'''[\s　]*(.*)$", line)
        if m:
            flush()
            current = {
                "law": law,
                "chapter": chapter,
                "article": m.group(1).strip(),
                "text": clean_inline(m.group(2)),
                "source": source,
            }
            continue

        # 续行（同一条的款/项）
        if current is not None:
            s = clean_inline(line)
            if s:
                current["text"] += s

    flush()
    return articles


def main():
    all_articles = []
    for fname, law, source in LAWS:
        path = DATA / fname
        if not path.exists():
            print(f"[skip] 缺少 {fname}")
            continue
        text = path.read_text(encoding="utf-8")
        arts = parse_wikitext(text, law, source)
        print(f"[ok] {law}：解析出 {len(arts)} 条")
        all_articles.extend(arts)

    out = DATA / "laws.json"
    out.write_text(
        json.dumps(all_articles, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[ok] 已写入 {out}，共 {len(all_articles)} 条")


if __name__ == "__main__":
    main()
