# -*- coding: utf-8 -*-
"""生成关联条文引用索引（data/citation_index.json）。

扫描 laws.json 每条法条正文，识别「第X条」「本法第X条」等引用关系，
建立双向引用索引：A 引用 B，则 A 与 B 互相关联。
仅识别数字条号 + 条（不含项/款），默认引用本法（同部法律内的条文引用）。
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lawmeta import cn_to_arabic  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PAT = re.compile(r'第([一二三四五六七八九十百零]+)条')


def main():
    laws = json.load(open(DATA_DIR / "laws.json", encoding="utf-8"))

    all_keys = {}
    for l in laws:
        art = cn_to_arabic(l.get('article', ''))
        if art is not None:
            all_keys[f"{l.get('law', '')}:{art}"] = l

    index = {}
    for l in laws:
        law = l.get('law', '')
        art = cn_to_arabic(l.get('article', ''))
        key = f"{law}:{art}"
        text = l.get('text', '')
        for m in PAT.finditer(text):
            cited = cn_to_arabic(m.group(1))
            if cited is None:
                continue
            cited_key = f"{law}:{cited}"
            if cited_key == key or cited_key not in all_keys:
                continue
            index.setdefault(key, set()).add(cited_key)
            index.setdefault(cited_key, set()).add(key)

    out = {k: sorted(v) for k, v in index.items()}
    with open(DATA_DIR / "citation_index.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"已生成 citation_index.json：{len(out)} 条法条存在引用关系")


if __name__ == "__main__":
    main()
