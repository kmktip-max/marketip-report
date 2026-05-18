"""광고 링크 구조 확인"""
import sys, io, time, re, json
from urllib.parse import quote, urlparse, parse_qs, unquote

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

keyword = "강아지사료"

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled"]
    )
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        locale="ko-KR", viewport={"width": 1366, "height": 768}
    )
    pg = ctx.new_page()
    pg.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")

    print("[1] naver.com 접속...")
    pg.goto("https://www.naver.com", wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)

    url = f"https://search.naver.com/search.naver?where=nexearch&query={quote(keyword)}&start=1"
    print(f"[2] goto: {url}")
    pg.goto(url, wait_until="domcontentloaded", timeout=25000)
    time.sleep(2)

    for y in [500, 1000, 1500, 2000]:
        pg.evaluate(f"window.scrollTo(0,{y})")
        time.sleep(0.3)

    print(f"[3] title: {pg.title()}")

    # ── 광고 링크만 (inflow/outlink) ──────────────────────────────────────────
    ad_links = pg.locator('a[href*="inflow/outlink"]').all()
    print(f"\n[4] inflow/outlink 링크 수: {len(ad_links)}")
    for i, lnk in enumerate(ad_links[:10]):
        href = lnk.get_attribute("href") or ""
        name = lnk.inner_text().strip().replace("\n", " ")[:25]
        # url 파라미터 추출
        try:
            qs = parse_qs(urlparse(href).query)
            actual = unquote(qs.get("url",[""])[0])
        except:
            actual = ""
        print(f"  [{i}] {name!r:28s} -> {actual[:60]}")

    # ── 전체 smartstore 링크 ──────────────────────────────────────────────────
    all_ss = pg.locator('a[href*="smartstore.naver.com"]').all()
    print(f"\n[5] 전체 smartstore 링크 수: {len(all_ss)}")

    # ── 광고 영역 selector 후보 ───────────────────────────────────────────────
    print("\n[6] 광고 영역 selector 후보:")
    for sel in [
        '[class*="ad_area"]', '[class*="ShoppingAd"]', '[class*="shopping_ad"]',
        '[data-nclick*="shad"]', '[class*="adProduct"]', '#ad_area',
        '[class*="ProductAd"]', '[class*="product_ad"]',
    ]:
        try:
            c = pg.locator(sel).count()
            if c: print(f"  OK {sel!r} -> {c}")
        except: pass

    # ── HTML 내 광고 패턴 ─────────────────────────────────────────────────────
    html = pg.content()
    inflow_count = html.count("inflow/outlink")
    print(f"\n[7] HTML 내 inflow/outlink 출현 횟수: {inflow_count}")

    # 상위 5개 광고 링크의 실제 스토어 URL 파싱
    print("\n[8] 광고 스토어 URL 파싱:")
    seen = set()
    for lnk in ad_links:
        href = lnk.get_attribute("href") or ""
        if "inflow/outlink" not in href:
            continue
        try:
            qs = parse_qs(urlparse(href).query)
            actual = unquote(qs.get("url",[""])[0])
        except:
            actual = ""
        if "smartstore.naver.com" not in actual:
            continue
        parts = urlparse(actual).path.strip("/").split("/")
        if not parts or parts[0] in ["main","inflow","i","m",""]:
            continue
        store_id = parts[0]
        if store_id in seen:
            continue
        seen.add(store_id)
        store_url = f"https://smartstore.naver.com/{store_id}"
        name = lnk.inner_text().strip().replace("\n"," ")[:20]
        print(f"  store_id={store_id}  name={name!r}  url={store_url}")

    browser.close()
    print("\nDONE")
