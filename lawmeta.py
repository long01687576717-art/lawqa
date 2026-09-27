# -*- coding: utf-8 -*-
"""法条元数据模块（纯 Python，无 numpy / fastembed 依赖）。

供「本地版」（retriever.py，向量+BM25）与「线上版」（streamlit_app.py，纯BM25）
共用的法条级元数据能力：
1. 中文数字 <-> 阿拉伯数字转换；
2. 条款调整标注（law_notes.json）：已被后续法规调整的旧条款说明；
3. 关联条文引用索引（citation_index.json）：跨条引用关系，用于联动召回。
"""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

_DIGITS = {'零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4,
           '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}


def cn_to_arabic(s):
    """中文数字 -> 阿拉伯数字，如 四十四 -> 44、一百零七 -> 107。失败返回 None。"""
    s = (s or '').strip().replace(' ', '')
    if not s:
        return None
    total = 0
    if '百' in s:
        before, s = s.split('百', 1)
        total += (_DIGITS.get(before, 1) if before else 1) * 100
    if '十' in s:
        before, s = s.split('十', 1)
        total += (_DIGITS.get(before, 1) if before else 1) * 10
    for ch in s:
        if ch in _DIGITS:
            total += _DIGITS[ch]
    return total


def law_key(law, article_arabic):
    """生成元数据表用的键：'法律全称:阿拉伯条号'。"""
    return f"{law}:{article_arabic}"


def _load_json(name):
    p = DATA_DIR / name
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load_law_notes():
    return _load_json("law_notes.json")


def load_citation_index():
    return _load_json("citation_index.json")


def attach_notes(laws, notes=None):
    """给法条 dict 列表附加 note（不改动法条 text 原文），返回新列表。"""
    if notes is None:
        notes = load_law_notes()
    if not notes:
        return laws
    out = []
    for l in laws:
        key = law_key(l.get('law', ''), cn_to_arabic(l.get('article', '')))
        if key in notes:
            d = dict(l)
            d['note'] = notes[key]
            out.append(d)
        else:
            out.append(l)
    return out


def expand_with_citations(top_laws, all_laws, index=None, max_extra=3):
    """把关联条文追加到 top_laws 后面（标记 _cited=True），返回新列表。

    关联关系由 citation_index.json 提供（双向：A 引用 B 则 A、B 互相关联）。
    追加的关联条文不挤占原 top-k，数量上限 max_extra。
    """
    if index is None:
        index = load_citation_index()
    if not index:
        return top_laws
    law_by_key = {}
    for l in all_laws:
        key = law_key(l.get('law', ''), cn_to_arabic(l.get('article', '')))
        law_by_key.setdefault(key, l)
    seen = set()
    for l in top_laws:
        seen.add(law_key(l.get('law', ''), cn_to_arabic(l.get('article', ''))))
    result = list(top_laws)
    for l in top_laws:
        key = law_key(l.get('law', ''), cn_to_arabic(l.get('article', '')))
        for rel in index.get(key, []):
            if rel in seen or rel not in law_by_key:
                continue
            seen.add(rel)
            d = dict(law_by_key[rel])
            d['_cited'] = True
            result.append(d)
            if len(result) >= len(top_laws) + max_extra:
                return result
    return result


def merge_two_routes(main_laws, extra_laws, max_extra=3):
    """合并两路检索结果：主路结果在前，口语路去重后追加（最多 max_extra 条）。

    口语路召回的法条标记 _oral=True，供 prompt 区分。
    用于避免把口语同义词混进主检索词稀释权重，而是作为独立检索路补充召回。
    """
    if not extra_laws:
        return main_laws
    seen = set()
    result = list(main_laws)
    for l in main_laws:
        seen.add(law_key(l.get('law', ''), cn_to_arabic(l.get('article', ''))))
    for l in extra_laws:
        key = law_key(l.get('law', ''), cn_to_arabic(l.get('article', '')))
        if key in seen:
            continue
        seen.add(key)
        d = dict(l)
        d['_oral'] = True
        result.append(d)
        if len(result) >= len(main_laws) + max_extra:
            break
    return result
