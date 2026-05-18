"""최종 동작 방식: naver.com 검색창 입력 → search.naver.com 쇼핑 결과"""
import sys, io, time, re, random, json
from urllib.parse import quote, urlparse, parse_qs, unquote

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,6}')
PHONE_RE = re.compile(r'0\d{1,2}[\s\-]?\d{3,4}[\s\-]?\d{4}')

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

keyword = "강아지사료"

def extract_real_url(href):
    """광고 redirect URL에서 실제 URL 추출"""
    if not href: return href
    if "inflow/outlink" in href or "outlink" in href:
        try:
            qs = parse_qs(urlparse(href).query)
            inner = qs.get("url", [None])[0] or qs.get("link", [None])[0]
            if inner: return unquote(inner)
        except: pass
    return href

def get_store_url(href):
    """스마트스토어 스토어 홈 URL 반환"""
    real = extract_real_url(href)
    if not real: return None, None
    if "smartstore.naver.com" in real:
        parts = urlparse(real).path.strip("/").split("/")
        if parts and parts[0] not in ["main","inflow","i","m","v","product","products"]:
            sid = parts[0]
            return f"https://smartstore.naver.com/{sid}", sid
    return real.split("?")[0], None

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        headless=True,
        args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu",
              "--disable-blink-features=AutomationControlled","--window-size=1366,768"]
    )
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        locale="ko-KR", viewport={"width":1366,"height":768},
    )
    pg = ctx.new_page()
    Stealth().apply_stealth_sync(pg)

    # Step 1: naver.com 방문 + 검색창 입력
    print("[1] naver.com 방문...")
    pg.goto("https://www.naver.com", wait_until="domcontentloaded", timeout=20000)
    time.sleep(random.uniform(1.5, 2.5))

    print(f"[2] 검색: {keyword}")
    sb = pg.locator('input[name="query"]').first
    sb.click()
    time.sleep(0.3)
    sb.fill("")
    time.sleep(0.2)
    for ch in keyword:
        sb.type(ch, delay=random.randint(50, 130))
    time.sleep(0.5)
    sb.press("Enter")
    pg.wait_for_load_state("domcontentloaded", timeout=15000)
    time.sleep(2)
    print(f"  URL: {pg.url[:80]}")

    # Step 2: 쇼핑 탭으로 이동
    print("[3] 쇼핑 탭 이동...")
    try:
        # search.naver.com에서 쇼핑 탭 찾기
        shop_tab = pg.locator('a[href*="where=shopping"], a:has-text("쇼핑")').first
        if shop_tab.count() > 0:
            shop_tab.click()
            pg.wait_for_load_state("domcontentloaded", timeout=15000)
            time.sleep(2)
            print(f"  쇼핑탭 URL: {pg.url[:80]}")
        else:
            # 직접 쇼핑 검색 URL
            pg.goto(f"https://search.naver.com/search.naver?where=shopping&query={quote(keyword)}", wait_until="domcontentloaded", timeout=20000)
            time.sleep(2)
            print(f"  직접이동 URL: {pg.url[:80]}")
    except Exception as e:
        print(f"  탭 클릭 실패: {e}")

    # Step 3: 스크롤 + 링크 추출
    print("[4] 스크롤 및 링크 추출...")
    for y in [500, 1000, 1500, 2000]:
        pg.evaluate(f"window.scrollTo(0,{y})")
        time.sleep(0.8)

    html = pg.content()
    print(f"  page size: {len(html)}")
    blocked = "접속이 일시적으로 제한" in html
    print(f"  blocked: {blocked}")

    if not blocked:
        ss_links = pg.locator('a[href*="smartstore.naver.com/"]').all()
        print(f"  smartstore links: {len(ss_links)}")

        results = []
        seen = set()
        for link in ss_links:
            href = link.get_attribute("href") or ""
            store_url, store_id = get_store_url(href)
            if not store_url: continue
            key = store_id or store_url
            if key in seen: continue
            seen.add(key)

            name = link.inner_text().strip().replace("\n"," ") or (store_id or "")
            try:
                parent_html = link.evaluate('el => el.closest("li,div,article")?.innerHTML || ""')
            except:
                parent_html = ""
            is_ad = any(x in parent_html for x in ["광고","adBadge","ad_badge","isAd"])
            grade = next((g for g in ["프리미엄","빅파워","파워"] if g in parent_html), "")

            results.append({
                "store_name": name, "store_url": store_url,
                "is_ad": "광고" if is_ad else "비광고", "grade": grade
            })

        print(f"\n  수집: {len(results)}개")
        for r in results[:10]:
            print(f"    {r['store_name'][:22]:24s} | {r['is_ad']:4s} | {r['grade'] or '-':4s} | {r['store_url'][:50]}")

        # JSON in page 데이터 확인
        print("\n[5] 페이지 내 JSON 데이터...")
        mall_names = re.findall(r'"mallName"\s*:\s*"([^"]+)"', html)
        is_ads = re.findall(r'"isAd"\s*:\s*(true|false)', html)
        print(f"  mallName 수: {len(mall_names)}")
        print(f"  isAd 수: {len(is_ads)} (광고:{is_ads.count('true')}개)")
        if mall_names:
            print(f"  샘플: {mall_names[:5]}")

        with open("debug_final.html","w",encoding="utf-8") as f:
            f.write(html)
        print("  debug_final.html 저장")

    browser.close()

print("\nDONE")
