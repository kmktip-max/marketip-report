"""
마케팁 OS — 네이버 파워링크 순위 자동 조회기
실행: python rank_checker.py  또는  run_rank_checker.bat 더블클릭

동작:
  1. Supabase에서 모든 클라이언트의 자동입찰 그룹 로드
  2. 그룹에 check_domain이 설정된 경우, 각 키워드를 네이버에서 검색
  3. 파워링크 광고 중 check_domain이 포함된 광고 순위 확인
  4. current_rank 업데이트 후 Supabase에 저장
"""

import os, sys, time, random, json, re
from datetime import datetime
from urllib.parse import urlparse, parse_qs, unquote, quote

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

ROOT = os.path.dirname(os.path.abspath(__file__))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass

# ── Supabase ──────────────────────────────────────────────────────────────────
def _get_sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception as e:
        print(f"[Supabase] 연결 실패: {e}")
        return None

def sb_load(key):
    sb = _get_sb()
    if not sb:
        return None
    try:
        res = sb.table("app_data").select("data").eq("key", key).execute()
        if res.data:
            return res.data[0]["data"]
    except Exception as e:
        print(f"[Supabase] 로드 실패 ({key}): {e}")
    return None

def sb_save(key, data):
    sb = _get_sb()
    if not sb:
        print(f"[Supabase] 미연결 — {key} 저장 건너뜀")
        return False
    try:
        sb.table("app_data").upsert({
            "key":        key,
            "data":       data,
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }, on_conflict="key").execute()
        return True
    except Exception as e:
        print(f"[Supabase] 저장 실패 ({key}): {e}")
        return False

# ── 도메인 정규화 ──────────────────────────────────────────────────────────────
def _normalize_domain(domain: str) -> str:
    """www.example.com → example.com (www 제거, 소문자, 경로 제거)"""
    d = domain.lower().strip().rstrip("/")
    d = re.sub(r"^https?://", "", d)
    d = re.sub(r"^www\.", "", d)
    return d.split("/")[0]

def _extract_dest(href: str) -> str:
    """네이버 광고 추적 URL에서 실제 목적지 URL 추출"""
    if not href:
        return ""
    try:
        qs = parse_qs(urlparse(href).query)
        for key in ("url", "link", "dest"):
            if key in qs:
                return unquote(qs[key][0])
    except Exception:
        pass
    return href

def _domain_match(href: str, target_domain: str) -> bool:
    """광고 링크가 target_domain과 일치하는지 확인"""
    dest = _extract_dest(href)
    dest_domain = _normalize_domain(re.sub(r"^https?://", "", dest))
    return target_domain in dest_domain or dest_domain in target_domain

# ── 네이버 파워링크 순위 조회 ─────────────────────────────────────────────────
def check_rank(page, keyword: str, domain: str) -> int | None:
    """
    네이버에서 keyword 검색 후 파워링크 영역에서 domain 광고 순위 반환.
    못 찾으면 None.
    """
    target = _normalize_domain(domain)
    url = (
        "https://search.naver.com/search.naver"
        f"?where=nexearch&sm=top_hty&fbm=0&ie=utf8&query={quote(keyword)}"
    )
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(random.randint(1500, 2500))
    except Exception as e:
        print(f"    [페이지 로드 오류] {keyword}: {e}")
        return None

    # 파워링크 광고 영역 — 상단 광고 li 항목들
    # Naver 구조: #ad_area_top > ul > li  또는 .ad_area > ul.lst_ad > li
    ad_selectors = [
        "#ad_area_top ul li",
        ".lst_ad_top li",
        "ul.lst_ad li",
        "[class*='ad_area'] ul li",
    ]

    ad_items = []
    for sel in ad_selectors:
        items = page.query_selector_all(sel)
        if items:
            ad_items = items
            break

    if not ad_items:
        print(f"    [{keyword}] 파워링크 영역 없음")
        return None

    for rank, item in enumerate(ad_items, start=1):
        # 항목 내 모든 a 태그 href 확인
        links = item.query_selector_all("a[href]")
        for link in links:
            href = link.get_attribute("href") or ""
            if _domain_match(href, target):
                return rank
        # 항목 텍스트에서 도메인 확인 (일부 광고는 표시 URL이 있음)
        txt = item.inner_text().lower()
        if target in txt:
            return rank

    return None

# ── 전체 클라이언트 순위 조회 루프 ───────────────────────────────────────────
def run():
    print("=" * 60)
    print("  마케팁 OS — 네이버 파워링크 순위 조회기")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # client_accounts에서 클라이언트 목록 가져오기
    accounts_raw = sb_load("client_accounts") or []
    client_ids   = ["admin"] + [a.get("username","") for a in accounts_raw if a.get("username")]

    # 순위 체크 대상 수집
    targets = []   # (sb_key, data_dict, group_idx, kw_idx, keyword, domain)
    for cid in client_ids:
        sb_key = f"bidding_{cid}"
        bdata  = sb_load(sb_key)
        if not bdata or not isinstance(bdata, dict):
            continue
        for gi, g in enumerate(bdata.get("groups", [])):
            domain = g.get("check_domain", "").strip()
            if not domain:
                continue
            for ki, kw in enumerate(g.get("keywords", [])):
                targets.append((sb_key, bdata, gi, ki, kw["keyword"], domain))

    if not targets:
        print("\n⚠  순위 체크 대상 없음.")
        print("   [그룹 관리] 탭에서 그룹에 '검색 도메인'을 설정해주세요.")
        input("\n아무 키나 누르면 종료...")
        return

    print(f"\n총 {len(targets)}개 키워드 순위 조회 시작\n")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="ko-KR",
        )
        page = ctx.new_page()

        # 처음 네이버 접속으로 쿠키 워밍업
        print("  네이버 접속 중...")
        page.goto("https://www.naver.com", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(random.randint(2000, 3000))

        # 변경된 데이터 추적 (sb_key 기준)
        changed: dict[str, dict] = {}
        now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        for i, (sb_key, bdata, gi, ki, keyword, domain) in enumerate(targets, 1):
            print(f"  [{i}/{len(targets)}] {keyword!r}  ({domain})")
            rank = check_rank(page, keyword, domain)
            if rank is not None:
                print(f"    → {rank}위")
            else:
                print(f"    → 광고 없음 (미노출 또는 도메인 불일치)")

            # 데이터 업데이트
            bdata["groups"][gi]["keywords"][ki]["current_rank"]  = rank
            bdata["groups"][gi]["keywords"][ki]["last_checked"]  = now_str
            changed[sb_key] = bdata

            # 키워드 간 딜레이 (봇 차단 방지)
            if i < len(targets):
                delay = random.uniform(2.5, 4.5)
                time.sleep(delay)

        browser.close()

    # Supabase 저장
    print("\n결과 저장 중...")
    for sb_key, bdata in changed.items():
        ok = sb_save(sb_key, bdata)
        print(f"  {sb_key}: {'저장 완료' if ok else '저장 실패'}")

    print(f"\n완료! ({len(targets)}개 키워드 조회)")
    input("\n아무 키나 누르면 종료...")

if __name__ == "__main__":
    run()
