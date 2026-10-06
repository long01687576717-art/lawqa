# -*- coding: utf-8 -*-
"""从官方渠道抓取法规原文，解析为结构化 data/laws.json。

用法：
    python scripts/build_laws.py            # 联网抓取（已抓过的读本地留档）并生成 laws.json
    python scripts/build_laws.py --offline  # 只用 data/_raw_laws/ 留档原文重新解析

来源：
  - 法律 / 行政法规 / 司法解释：国家法律法规数据库 flk.npc.gov.cn（官方 Word 原文，只取「有效」版本）
  - 部门规章：发布机关官网原文（见 RULES）
原文逐字留档到 data/_raw_laws/<法规名>.txt（首行为来源链接），解析后逐条校验：
条号从 1 连续编号、每条内容都能在原文中逐字找到，任一不通过即报错退出。
"""
import http.cookiejar
import io
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lawmeta import cn_to_arabic  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA / "_raw_laws"
FLK = "https://flk.npc.gov.cn"

# 国家法律法规数据库收录的法规：(标题, 层级)
FLK_LAWS = [
    ("中华人民共和国劳动法", "法律"),
    ("中华人民共和国劳动合同法", "法律"),
    ("中华人民共和国社会保险法", "法律"),
    ("中华人民共和国劳动争议调解仲裁法", "法律"),
    ("中华人民共和国就业促进法", "法律"),
    ("中华人民共和国劳动合同法实施条例", "行政法规"),
    ("工伤保险条例", "行政法规"),
    ("女职工劳动保护特别规定", "行政法规"),
    ("职工带薪年休假条例", "行政法规"),
    ("最高人民法院关于审理劳动争议案件适用法律问题的解释（一）", "司法解释"),
    ("最高人民法院关于审理劳动争议案件适用法律问题的解释（二）", "司法解释"),
]

# 部门规章：(标题, 层级)；原文取自中国政府网国务院部门规章库、司法部规章库、人社部规章库，
# 这些站点有人机校验，脚本不直接抓取，原文已整理留档在 data/_raw_laws/（首行为官方链接）
RULES = [
    ("工资支付暂行规定", "部门规章"),
    ("最低工资规定", "部门规章"),
    ("企业职工带薪年休假实施办法", "部门规章"),
    ("劳务派遣暂行规定", "部门规章"),
]

ARTICLE_RE = re.compile(r"^第([一二三四五六七八九十百零]+)条[\s　]*(.*)$")
CHAPTER_RE = re.compile(r"^第[一二三四五六七八九十百零]+[章节][\s　]*\S*")


# ---------- 抓取 ----------
_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE
_opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
    urllib.request.HTTPSHandler(context=_ctx),
)
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": FLK + "/search"}


def _request(url, data=None):
    body = json.dumps(data).encode() if data is not None else None
    headers = dict(_HEADERS, **({"Content-Type": "application/json"} if body else {}))
    last = None
    for _ in range(5):  # 官网有 Cookie 校验与限流，失败稍等重试
        try:
            return _opener.open(urllib.request.Request(url, data=body, headers=headers), timeout=60).read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(4)
    raise RuntimeError(f"请求失败：{url}（{last}）")


def flk_find(title):
    """按标题精确检索，返回「有效」版本的记录（含 bbbs 编号、公布/施行日期）。"""
    query = {"searchRange": 1, "searchType": 1, "sxrq": [], "gbrq": [], "sxx": [], "gbrqYear": [],
             "flfgCodeId": [], "zdjgCodeId": [], "searchContent": title}
    rows = json.loads(_request(FLK + "/law-search/search/list", query))["rows"]
    hits = [r for r in rows if re.sub(r"<[^>]+>", "", r["title"]) == title and r["sxx"] == 3]
    if len(hits) != 1:
        raise RuntimeError(f"「{title}」的有效版本数为 {len(hits)}，需人工确认")
    return hits[0]


def flk_docx_text(bbbs):
    """下载官方 Word 原文，按段落返回纯文本。"""
    meta = json.loads(_request(f"{FLK}/law-search/download/pc?format=docx&bbbs={bbbs}"))
    raw = _request(meta["data"]["url"])
    xml = zipfile.ZipFile(io.BytesIO(raw)).read("word/document.xml").decode("utf-8")
    paras = [re.sub(r"<[^>]+>", "", p) for p in re.findall(r"(?s)<w:p[ >].*?</w:p>", xml)]
    return "\n".join(p.strip() for p in paras if p.strip())


def raw_path(title):
    return RAW_DIR / f"{title}.txt"


def fetch_flk(title):
    """返回 (正文, 来源链接, 施行日期)；已留档则直接读本地。"""
    p = raw_path(title)
    if p.exists():
        head, text = p.read_text(encoding="utf-8").split("\n", 1)
        src, eff = head.split("\t")
        return text, src, eff
    rec = flk_find(title)
    text = flk_docx_text(rec["bbbs"])
    src = f"{FLK}/detail?id={rec['bbbs']}"
    eff = rec.get("sxrq") or rec.get("gbrq") or ""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    p.write_text(f"{src}\t{eff}\n{text}", encoding="utf-8")
    time.sleep(2)
    return text, src, eff


# ---------- 解析与校验 ----------
def parse_articles(text, law, level, source, effective):
    """按「第X条」切分；章、节标题记入 chapter；首条之前的标题与公布说明不入库。"""
    articles, chapter, section, cur = [], "", "", None
    for line in text.split("\n"):
        line = line.strip()
        m = ARTICLE_RE.match(line)
        if m:
            cur = {"law": law, "level": level, "chapter": "　".join(x for x in (chapter, section) if x),
                   "article": m.group(1), "text": m.group(2).strip(), "source": source, "effective": effective}
            articles.append(cur)
            continue
        if CHAPTER_RE.match(line):
            title = re.sub(r"[\s　]+", "　", line)
            if re.match(r"^第[一二三四五六七八九十百零]+章", line):
                chapter, section = title, ""
            else:
                section = title
            continue
        if cur is not None and line:
            cur["text"] += "\n" + line
    return articles


def verify(articles, text, law):
    nums = [cn_to_arabic(a["article"]) for a in articles]
    if nums != list(range(1, len(nums) + 1)):
        bad = [n for i, n in enumerate(nums, 1) if n != i][:5]
        raise RuntimeError(f"「{law}」条号不连续：{bad}")
    plain = re.sub(r"\s", "", text)
    for a in articles:
        for seg in a["text"].split("\n"):
            if re.sub(r"\s", "", seg) not in plain:
                raise RuntimeError(f"「{law}」第{a['article']}条与原文不一致：{seg[:30]}")


def main():
    offline = "--offline" in sys.argv
    all_articles = []
    for title, level in FLK_LAWS:
        if offline and not raw_path(title).exists():
            raise SystemExit(f"离线模式缺少留档：{title}")
        text, src, eff = fetch_flk(title)
        arts = parse_articles(text, title, level, src, eff)
        verify(arts, text, title)
        print(f"[ok] {title}（{level}，施行 {eff}）：{len(arts)} 条")
        all_articles.extend(arts)
    for title, level in RULES:
        p = raw_path(title)
        if not p.exists():
            raise SystemExit(f"缺少部门规章留档：{p}")
        head, text = p.read_text(encoding="utf-8").split("\n", 1)
        src, eff = head.split("\t")
        arts = parse_articles(text, title, level, src, eff)
        verify(arts, text, title)
        print(f"[ok] {title}（{level}，施行 {eff}）：{len(arts)} 条")
        all_articles.extend(arts)

    out = DATA / "laws.json"
    out.write_text(json.dumps(all_articles, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] 已写入 {out}，共 {len(all_articles)} 条")


if __name__ == "__main__":
    main()
