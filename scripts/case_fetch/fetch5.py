from playwright.sync_api import sync_playwright
PAGES = {
    "qd_layoff": "https://hrss.qingdao.gov.cn/zq_47/ldgx_47/dxal_47/202206/t20220614_6146660.shtml",
    "ky_layoff": "http://tlky.lncourt.gov.cn/article/detail/2022/03/id/6605017.shtml",
    "dp_resign": "https://www.dpxq.gov.cn/ztzl/gzqxjxs/pgt_192579/content/post_10421254.html",
    "zj_resign": "https://rlsbt.zj.gov.cn/art/2022/1/26/art_1450623_58928153.html",
    "zjzy_retire": "https://www.zjzy.gov.cn/xwzx/jckx/kfqfy/2025/0207/26861.html",
    "wh_batch": "http://www.sdcourt.gov.cn/whzy/xwzx52/xwzx521/20866334/index.html",
    "wh_retire": "http://www.sdcourt.gov.cn/whzy/xwzx52/xwzx521/31962178/index.html",
    "cj_hpf": "https://chinajob.mohrss.gov.cn/h5/c/2020-05-28/209652.shtml",
    "yc_hpf": "http://gjj.yichang.gov.cn/content-62311-5673-1.html",
    "gz_hpf": "https://www.gzcourt.gov.cn/fzxc/spzx/2014/01/06084312086.html",
}
with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)
    p = b.new_page()
    for k, u in PAGES.items():
        try:
            p.goto(u, timeout=60000); p.wait_for_timeout(2500)
            t = p.inner_text("body")
            open(f"raw6/{k}.txt", "w", encoding="utf-8").write(u + "\n" + t)
            print(f"{k:12s} {len(t):6d}  {p.title()[:50]}")
        except Exception as e:
            print(k, "ERR", str(e)[:100])
    b.close()
