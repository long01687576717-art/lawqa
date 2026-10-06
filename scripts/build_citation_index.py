# -*- coding: utf-8 -*-
"""生成关联条文引用索引（data/citation_index.json）。

扫描 laws.json 每条法条正文，识别「第X条」引用关系，建立双向索引：A 引用 B，则 A 与 B 互相关联。
引用目标的判定：
  - 紧跟在法规名称之后（如「劳动合同法第三十九条」「《中华人民共和国劳动合同法》第十四条」，
    或本法规中「以下简称××」约定的简称）→ 该法规；
  - 紧跟在「本法 / 本条例 / 本规定 / 本办法 / 本解释」之后，或前面没有法规名称 → 本法规；
  - 「第X条、第Y条」这类连续列举沿用前一个引用目标；
  - 引用库外法规（如「民法典第X条」）→ 不建立关联。
仅识别条号（不含款、项）。
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lawmeta import cn_to_arabic  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REF = re.compile(r"第([一二三四五六七八九十百零]+)条")
# 两个引用之间只有这些字符时，视为连续列举，沿用前一个引用目标
CHAIN_GAP = re.compile(r"^[第一二三四五六七八九十百零款项（）()、，,和或及至与\s]*$")
SELF_WORDS = ("本法", "本条例", "本规定", "本办法", "本解释")
OTHER_LAW_TAIL = re.compile(r"《[^》]{2,40}》$|[一-龥]{2,20}(法|条例|规定|办法|解释)$")


def law_aliases(laws):
    """法规全称、去掉「中华人民共和国」的简称 → 法规全称。"""
    aliases = {}
    for title in {l["law"] for l in laws}:
        aliases[title] = title
        short = title.replace("中华人民共和国", "")
        aliases.setdefault(short, title)
    return aliases


def local_aliases(text, aliases):
    """本条文中「（以下简称××）」约定的简称 → 所指法规全称。"""
    out = {}
    for m in re.finditer(r"《([^》]+)》（以下简称([^）]{1,12})）", text):
        full = aliases.get(m.group(1)) or aliases.get(m.group(1).replace("中华人民共和国", ""))
        if full:
            out[m.group(2)] = full
    return out


def resolve(prefix, self_law, aliases):
    """根据引用前面的文字判断引用目标；返回法规全称、self_law 或 None（库外法规）。"""
    p = prefix.rstrip()
    if p.endswith(SELF_WORDS):
        return self_law
    p = p.rstrip("》")
    for alias in sorted(aliases, key=len, reverse=True):  # 长名优先，避免「劳动合同法实施条例」被识别成「劳动合同法」
        if p.endswith(alias):
            return aliases[alias]
    if OTHER_LAW_TAIL.search(prefix.rstrip()):
        return None
    return self_law


def main():
    laws = json.load(open(DATA_DIR / "laws.json", encoding="utf-8"))
    aliases = law_aliases(laws)
    keys = {f"{l['law']}:{cn_to_arabic(l['article'])}" for l in laws}

    # 规章中的「以下简称」在整部法规内有效：先按法规汇总
    law_local = {}
    for l in laws:
        law_local.setdefault(l["law"], {}).update(local_aliases(l["text"], aliases))

    index = {}
    for l in laws:
        law, text = l["law"], l["text"]
        key = f"{law}:{cn_to_arabic(l['article'])}"
        names = dict(aliases, **law_local.get(law, {}))
        target, last_end = law, None
        for m in REF.finditer(text):
            gap = text[last_end:m.start()] if last_end is not None else None
            if gap is None or not CHAIN_GAP.match(gap):
                target = resolve(text[max(0, m.start() - 40):m.start()], law, names)
            last_end = m.end()
            if target is None:
                continue
            cited = f"{target}:{cn_to_arabic(m.group(1))}"
            if cited == key or cited not in keys:
                continue
            index.setdefault(key, set()).add(cited)
            index.setdefault(cited, set()).add(key)

    out = {k: sorted(v) for k, v in index.items()}
    with open(DATA_DIR / "citation_index.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    cross = sum(1 for k, vs in out.items() for v in vs if k.split(":")[0] != v.split(":")[0]) // 2
    print(f"已生成 citation_index.json：{len(out)} 条法条存在引用关系，其中跨法规关联 {cross} 对")


if __name__ == "__main__":
    main()
