"""
마케팁 OS — 로컬 수집기
실행: python collector.py
- Playwright headless=False (실제 크롬처럼 동작)
- 수집 결과 data/sales_leads_shopping.csv/.xlsx 저장
- Supabase에도 저장 (연결된 경우)
"""

import os, sys, re, time, random, json, csv, io
from datetime import datetime
from urllib.parse import quote, urlparse, parse_qs, unquote

# Windows 콘솔 UTF-8 출력
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass  # Python < 3.7

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ── 환경변수 로드 (.env) ──────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass

# ── 정규식 ────────────────────────────────────────────────────────────────────
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,6}')
PHONE_RE = re.compile(r'0\d{1,2}[\s\-]?\d{3,4}[\s\-]?\d{4}')

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# ── Supabase ──────────────────────────────────────────────────────────────────
def _get_supabase():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception:
        return None

def _sb_save(collection, data):
    sb = _get_supabase()
    if not sb:
        print("  [Supabase] 미연결 — 로컬 파일만 저장")
        return False
    try:
        sb.table("app_data").upsert({
            "key":        collection,
            "data":       data,
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }, on_conflict="key").execute()
        print(f"  [Supabase] '{collection}' 저장 완료 ({len(data)}건)")
        return True
    except Exception as e:
        print(f"  [Supabase] 저장 실패: {e}")
        return False

def _sb_load(collection):
    sb = _get_supabase()
    if not sb:
        return []
    try:
        res = sb.table("app_data").select("data").eq("key", collection).execute()
        if res.data:
            return res.data[0]["data"] or []
    except Exception:
        pass
    return []

# ── 헬퍼 ─────────────────────────────────────────────────────────────────────
def _real_url(href):
    if not href:
        return href
    if "outlink" in href or "inflow" in href:
        try:
            qs = parse_qs(urlparse(href).query)
            inner = (qs.get("url") or qs.get("link") or [None])[0]
            if inner:
                return unquote(inner)
        except Exception:
            pass
    return href

def _store_key(href):
    real = _real_url(href or "")
    if not real:
        return None, None
    if "smartstore.naver.com" in real:
        parts = urlparse(real).path.strip("/").split("/")
        if parts and parts[0] not in ["main","inflow","i","m","v","product","products",""]:
            sid = parts[0]
            return f"https://smartstore.naver.com/{sid}", sid
    return real.split("?")[0] or None, None

def _contacts(html):
    emails = [e for e in EMAIL_RE.findall(html)
              if not any(x in e.lower() for x in ["naver.com","example","kakao","google","daum"])]
    phones = PHONE_RE.findall(html)
    return (emails[0] if emails else "미확인"), (phones[0] if phones else "미확인")

def _save_csv(rows, path, cols):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            row = dict(r)
            if "found_keywords" in row and isinstance(row["found_keywords"], list):
                row["found_keywords"] = ", ".join(row["found_keywords"])
            w.writerow({c: row.get(c, "") for c in cols})
    print(f"  CSV 저장: {path}")

def _save_xlsx(rows, path, cols, sheet="Sheet1"):
    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = sheet
        ws.append(cols)
        for r in rows:
            row = dict(r)
            if "found_keywords" in row and isinstance(row["found_keywords"], list):
                row["found_keywords"] = ", ".join(row["found_keywords"])
            ws.append([row.get(c, "") for c in cols])
        wb.save(path)
        print(f"  XLSX 저장: {path}")
    except ImportError:
        print("  openpyxl 없음 — XLSX 저장 건너뜀")

def _merge_rows(existing, new_rows, key_field="store_url"):
    idx = {}
    for r in existing:
        k = r.get("store_id") or r.get(key_field, "")
        if k:
            idx[k] = r
    for r in new_rows:
        k = r.get("store_id") or r.get(key_field, "")
        if not k:
            continue
        if k in idx:
            for kw in r.get("found_keywords", []):
                if kw not in idx[k].get("found_keywords", []):
                    idx[k]["found_keywords"].append(kw)
        else:
            idx[k] = r
    return list(idx.values())

# ══════════════════════════════════════════════════════════════════════════════
# 쇼핑광고 수집
# ══════════════════════════════════════════════════════════════════════════════
SHOP_COLS = [
    "keyword","store_name","store_url","is_ad","page",
    "grade","owner","email","phone","memo","found_keywords",
]

def collect_shopping(keywords, max_pages, dedup=True):
    from playwright.sync_api import sync_playwright

    print(f"\n[쇼핑광고] 키워드: {keywords}  페이지: {max_pages}")
    results  = []
    seen_key = set()

    with sync_playwright() as pw:
        print("  브라우저 시작 (headless=False)...")
        browser = pw.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ]
        )
        ctx = browser.new_context(
            user_agent=UA,
            locale="ko-KR",
            viewport={"width": 1366, "height": 768},
        )
        pg = ctx.new_page()
        pg.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
            "window.chrome={runtime:{}};"
        )

        # naver.com 세션 확보
        print("  naver.com 접속...")
        pg.goto("https://www.naver.com", wait_until="domcontentloaded", timeout=30000)
        time.sleep(random.uniform(2, 3))
        print(f"  naver.com 완료 — closed={pg.is_closed()}")

        for keyword in keywords:
            print(f"\n  [키워드: {keyword}]")
            for page_num in range(1, max_pages + 1):
                start = (page_num - 1) * 10 + 1
                url = (
                    f"https://search.naver.com/search.naver"
                    f"?where=nexearch&query={quote(keyword)}&start={start}"
                )
                print(f"  {page_num}p goto: {url}")
                try:
                    pg.goto(url, wait_until="domcontentloaded", timeout=25000)
                    print(f"  {page_num}p 성공 — URL={pg.url[:60]}  closed={pg.is_closed()}")
                    time.sleep(random.uniform(1.5, 2.5))
                except Exception as e:
                    print(f"  {page_num}p goto 오류: {e}")
                    if pg.is_closed():
                        print("  page 닫힘 — 수집 중단")
                        break
                    continue

                if pg.is_closed():
                    print("  page 닫힘 — 수집 중단")
                    break

                # 스크롤
                for y in [500, 1000, 1500, 2000]:
                    try:
                        pg.evaluate(f"window.scrollTo(0,{y})")
                        time.sleep(0.3)
                    except Exception:
                        break

                # 페이지 상태 확인
                try:
                    title = pg.title()
                    html  = pg.content()
                    print(f"  title: {title[:40]}")
                    body  = pg.evaluate("()=>document.body?.innerText?.slice(0,300)||''")
                    print(f"  body: {body[:200]}")
                except Exception as e:
                    print(f"  content 오류: {e}")
                    continue

                if "접속이 일시적으로 제한" in html:
                    print("  ⛔ 차단 페이지 감지")
                    break

                # 스마트스토어 링크 추출
                try:
                    links = pg.locator('a[href*="smartstore.naver.com/"]').all()
                    print(f"  smartstore links: {len(links)}")
                except Exception:
                    links = []

                count = 0
                for lnk in links:
                    try:
                        href = lnk.get_attribute("href") or ""
                    except Exception:
                        continue
                    store_url, store_id = _store_key(href)
                    if not store_url:
                        continue
                    k = store_id or store_url
                    if dedup and k in seen_key:
                        for r in results:
                            if (r.get("store_id") or r["store_url"]) == k:
                                if keyword not in r["found_keywords"]:
                                    r["found_keywords"].append(keyword)
                        continue
                    seen_key.add(k)
                    try:
                        name = lnk.inner_text().strip().replace("\n", " ")
                    except Exception:
                        name = ""
                    if not name:
                        name = store_id or store_url.split("/")[-1]
                    try:
                        p_html = lnk.evaluate('el => el.closest("li,div,article")?.innerHTML || ""')
                    except Exception:
                        p_html = ""
                    is_ad = any(x in p_html for x in ["광고","adBadge","ad_badge"])
                    grade = next((g for g in ["프리미엄","빅파워","파워"] if g in p_html), "")
                    results.append({
                        "keyword":        keyword,
                        "store_name":     name,
                        "store_url":      store_url,
                        "store_id":       store_id or "",
                        "is_ad":          "광고" if is_ad else "비광고",
                        "page":           f"{page_num}페이지",
                        "grade":          grade,
                        "owner":          "미확인",
                        "email":          "미확인",
                        "phone":          "미확인",
                        "memo":           "",
                        "found_keywords": [keyword],
                    })
                    count += 1
                print(f"  {page_num}p → {count}개 신규")
                time.sleep(random.uniform(1, 2))

        # 연락처 수집
        print(f"\n  연락처 수집 시작 ({len(results)}개)...")
        for i, row in enumerate(results):
            if pg.is_closed():
                print("  page 닫힘 — 연락처 수집 중단")
                break
            if "smartstore.naver.com" not in (row.get("store_url") or ""):
                continue
            print(f"  [{i+1}/{len(results)}] {row['store_name'][:20]}: {row['store_url']}")
            try:
                pg.goto(row["store_url"], wait_until="domcontentloaded", timeout=15000)
                time.sleep(random.uniform(1, 1.5))
                email, phone = _contacts(pg.content())
                row["email"] = email
                row["phone"] = phone
                print(f"    email={email}  phone={phone}")
            except Exception as e:
                print(f"    연락처 오류: {e}")

        browser.close()

    print(f"\n  총 수집: {len(results)}개")
    return results

# ══════════════════════════════════════════════════════════════════════════════
# 파워링크 수집
# ══════════════════════════════════════════════════════════════════════════════
PL_COLS = [
    "keyword","biz_name","is_ad","page",
    "landing_url","domain","email","phone","memo","found_keywords",
]

def collect_powerlink(keywords, region, max_pages, dedup=True):
    from playwright.sync_api import sync_playwright

    print(f"\n[파워링크] 키워드: {keywords}  지역: {region}  페이지: {max_pages}")
    results  = []
    seen_dom = set()

    with sync_playwright() as pw:
        print("  브라우저 시작 (headless=False)...")
        browser = pw.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled","--no-sandbox"]
        )
        ctx = browser.new_context(
            user_agent=UA, locale="ko-KR",
            viewport={"width":1366,"height":768},
        )
        pg = ctx.new_page()
        pg.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )

        print("  naver.com 접속...")
        pg.goto("https://www.naver.com", wait_until="domcontentloaded", timeout=30000)
        time.sleep(random.uniform(2, 3))

        for keyword in keywords:
            query = f"{keyword} {region}".strip() if region else keyword
            print(f"\n  [키워드: {query}]")

            for page_num in range(1, max_pages + 1):
                start = (page_num - 1) * 10 + 1
                url = (
                    f"https://search.naver.com/search.naver"
                    f"?where=nexearch&query={quote(query)}&start={start}"
                )
                print(f"  {page_num}p goto: {url}")
                try:
                    pg.goto(url, wait_until="domcontentloaded", timeout=25000)
                    time.sleep(random.uniform(1.5, 2.5))
                    print(f"  {page_num}p 성공")
                except Exception as e:
                    print(f"  {page_num}p 오류: {e}")
                    if pg.is_closed():
                        break
                    continue

                if pg.is_closed():
                    break

                for y in [300, 700, 1200]:
                    try:
                        pg.evaluate(f"window.scrollTo(0,{y})")
                        time.sleep(0.3)
                    except Exception:
                        break

                # 파워링크 광고 링크 추출
                count = 0
                try:
                    # 외부 도메인 링크 (파워링크 광고)
                    all_links = pg.locator("a[href^='http']").all()
                    for lnk in all_links:
                        try:
                            href = lnk.get_attribute("href") or ""
                        except Exception:
                            continue
                        if not href or "naver" in urlparse(href).netloc:
                            continue
                        try:
                            domain = urlparse(href).netloc.replace("www.", "")
                        except Exception:
                            domain = ""
                        if not domain or domain in seen_dom:
                            continue
                        try:
                            p_html = lnk.evaluate('el => el.closest("li,div,article")?.innerHTML || ""')
                        except Exception:
                            p_html = ""
                        # 파워링크 광고 영역인지 확인
                        is_ad = any(x in p_html for x in ["광고","ad_","파워링크"])
                        if not is_ad:
                            continue
                        seen_dom.add(domain)
                        try:
                            biz_name = lnk.inner_text().strip().replace("\n"," ")
                        except Exception:
                            biz_name = domain
                        results.append({
                            "keyword":        keyword,
                            "biz_name":       biz_name or domain,
                            "is_ad":          "광고",
                            "page":           f"{page_num}페이지",
                            "landing_url":    href.split("?")[0],
                            "domain":         domain,
                            "email":          "미확인",
                            "phone":          "미확인",
                            "memo":           "",
                            "found_keywords": [keyword],
                        })
                        count += 1
                except Exception as e:
                    print(f"  link 오류: {e}")
                print(f"  {page_num}p → {count}개 신규")
                time.sleep(random.uniform(1, 2))

        # 연락처 수집
        print(f"\n  연락처 수집 ({len(results)}개)...")
        for i, row in enumerate(results):
            if pg.is_closed():
                break
            print(f"  [{i+1}/{len(results)}] {row['domain']}")
            try:
                pg.goto(row["landing_url"], wait_until="domcontentloaded", timeout=15000)
                time.sleep(1)
                email, phone = _contacts(pg.content())
                row["email"] = email
                row["phone"] = phone
                print(f"    email={email}  phone={phone}")
            except Exception as e:
                print(f"    오류: {e}")

        browser.close()

    print(f"\n  총 수집: {len(results)}개")
    return results

# ══════════════════════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════════════════════
def main():
    print("=" * 50)
    print("  마케팁 OS — 로컬 수집기")
    print("=" * 50)
    print("1. 쇼핑광고 DB 추출")
    print("2. 파워링크 DB 추출")
    print("0. 종료")
    choice = input("\n선택 (0/1/2): ").strip()

    if choice == "0":
        return

    if choice not in ("1", "2"):
        print("잘못된 선택")
        return

    kw_raw = input("키워드 (쉼표 또는 줄바꿈으로 구분): ").strip()
    keywords = [k.strip() for k in re.split(r"[,\n]", kw_raw) if k.strip()]
    if not keywords:
        print("키워드를 입력해주세요.")
        return

    pages_str = input("수집 페이지 수 (기본 2): ").strip()
    max_pages = int(pages_str) if pages_str.isdigit() else 2

    if choice == "1":
        results = collect_shopping(keywords, max_pages)
        existing = _sb_load("sales_leads_shopping")
        merged   = _merge_rows(existing, results, key_field="store_url")

        csv_path  = os.path.join(DATA_DIR, "sales_leads_shopping.csv")
        xlsx_path = os.path.join(DATA_DIR, "sales_leads_shopping.xlsx")
        _save_csv(merged, csv_path, SHOP_COLS)
        _save_xlsx(merged, xlsx_path, SHOP_COLS, sheet="쇼핑광고DB")
        _sb_save("sales_leads_shopping", merged)

    else:
        region = input("지역 (선택, 예: 서울 / 비워두면 전국): ").strip()
        results = collect_powerlink(keywords, region, max_pages)
        existing = _sb_load("sales_leads_powerlink")
        merged   = _merge_rows(existing, results, key_field="landing_url")

        csv_path  = os.path.join(DATA_DIR, "sales_leads_powerlink.csv")
        xlsx_path = os.path.join(DATA_DIR, "sales_leads_powerlink.xlsx")
        _save_csv(merged, csv_path, PL_COLS)
        _save_xlsx(merged, xlsx_path, PL_COLS, sheet="파워링크DB")
        _sb_save("sales_leads_powerlink", merged)

    print("\n✅ 완료")

if __name__ == "__main__":
    main()
