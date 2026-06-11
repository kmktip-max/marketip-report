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
def check_rank(page, keyword: str, domain: str) -> tuple:
    """
    네이버에서 keyword 검색 후 파워링크 영역에서 domain 광고 순위 반환.
    반환: (rank: int|None, total_slots: int)
    - rank=None: 해당 도메인 광고 없음
    - total_slots: 파워링크 구좌 수 (0이면 파워링크 영역 자체 없음)
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
        return None, 0

    # 파워링크 광고 영역 — 상단 광고 li 항목들
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

    total_slots = len(ad_items)

    if not ad_items:
        print(f"    [{keyword}] 파워링크 영역 없음 (구좌 0)")
        return None, 0

    for rank, item in enumerate(ad_items, start=1):
        links = item.query_selector_all("a[href]")
        for link in links:
            href = link.get_attribute("href") or ""
            if _domain_match(href, target):
                return rank, total_slots
        txt = item.inner_text().lower()
        if target in txt:
            return rank, total_slots

    return None, total_slots

# ── 전체 클라이언트 순위 조회 루프 ───────────────────────────────────────────
def run():
    # client_accounts에서 클라이언트 목록 가져오기
    accounts_raw = sb_load("client_accounts") or []
    client_ids   = ["admin"] + [a.get("username","") for a in accounts_raw if a.get("username")]

    # 순위 체크 대상 수집
    # 자동입찰 ON(bidding_enabled) 그룹을 먼저 체크 → 실제 입찰 그룹의 순위가
    # 큐 뒤로 밀려 stale 되는 문제 방지 (페이백관련 938개에 막혀 1.메인 83개가
    # 2일째 갱신 안 되던 버그 수정)
    raw = []   # (prio, sb_key, data_dict, group_idx, kw_idx, keyword, domain)
    for cid in client_ids:
        sb_key = f"bidding_{cid}"
        bdata  = sb_load(sb_key)
        if not bdata or not isinstance(bdata, dict):
            continue
        for gi, g in enumerate(bdata.get("groups", [])):
            domain = g.get("check_domain", "").strip()
            if not domain:
                continue
            prio = 0 if g.get("bidding_enabled") else 1   # 활성 그룹 우선
            for ki, kw in enumerate(g.get("keywords", [])):
                raw.append((prio, sb_key, bdata, gi, ki, kw["keyword"], domain))

    # 안정 정렬: 활성 그룹(prio=0)을 앞으로, 그룹 내 키워드 순서는 유지
    raw.sort(key=lambda t: t[0])
    targets = [t[1:] for t in raw]

    if not targets:
        print("\n⚠  순위 체크 대상 없음 — 5분 후 재시도")
        print("   [그룹 관리] 탭에서 그룹에 '검색 도메인'을 설정해주세요.")
        time.sleep(300)
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

        # sb_key별로 그룹화: 같은 키에 속하는 타깃을 모아서 그룹 끝날 때마다 즉시 저장
        from itertools import groupby
        from operator import itemgetter

        # targets를 (sb_key, bdata, gi, ...) 로 묶어 sb_key 기준 순서 보장
        # targets는 이미 sb_key 순으로 수집되어 있음
        saved_keys: set[str] = set()
        prev_sb_key = None
        bdata_map: dict[str, dict] = {}

        for i, (sb_key, bdata, gi, ki, keyword, domain) in enumerate(targets, 1):
            bdata_map[sb_key] = bdata  # 같은 객체 참조 — 아래 업데이트가 반영됨
            print(f"  [{i}/{len(targets)}] {keyword!r}  ({domain})")
            rank, total_slots = check_rank(page, keyword, domain)
            if rank is not None:
                print(f"    → {rank}위 (구좌 {total_slots}개)")
            else:
                slot_info = f"구좌 없음" if total_slots == 0 else f"구좌 {total_slots}개 — 내 광고 없음"
                print(f"    → 미노출 ({slot_info})")

            # 키워드별 실제 체크 시각 기록 (패스 시작 시각 아닌 실제 체크 시각)
            now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            bdata["groups"][gi]["keywords"][ki]["current_rank"]    = rank
            bdata["groups"][gi]["keywords"][ki]["total_ad_slots"]  = total_slots
            bdata["groups"][gi]["keywords"][ki]["rank_checked_at"] = now_str
            bdata["groups"][gi]["keywords"][ki]["last_checked"]    = now_str

            # sb_key가 바뀌는 시점(=이전 클라이언트 데이터 완료)에 즉시 저장
            if prev_sb_key and prev_sb_key != sb_key and prev_sb_key not in saved_keys:
                ok = sb_save(prev_sb_key, bdata_map[prev_sb_key])
                print(f"  [저장] {prev_sb_key}: {'완료' if ok else '실패'}")
                saved_keys.add(prev_sb_key)
            prev_sb_key = sb_key

            # 중간 저장: 20개마다 현재 클라이언트 데이터를 즉시 반영
            # (1021개 한 패스가 ~60분이라, 끝까지 기다리지 않고 점진적으로 순위 갱신)
            if i % 20 == 0:
                ok = sb_save(sb_key, bdata)
                print(f"  [중간저장 {i}/{len(targets)}] {sb_key}: {'완료' if ok else '실패'}")

            # 키워드 간 딜레이 (봇 차단 방지)
            if i < len(targets):
                delay = random.uniform(2.5, 4.5)
                time.sleep(delay)

        browser.close()

    # 마지막 클라이언트 저장 (모든 키워드 최신화)
    print("\n결과 저장 중...")
    for sb_key, bdata in bdata_map.items():
        ok = sb_save(sb_key, bdata)
        print(f"  {sb_key}: {'저장 완료' if ok else '저장 실패'}")

    print(f"\n완료! ({len(targets)}개 키워드 조회)")


if __name__ == "__main__":
    print("=" * 60)
    print("  마케팁 OS — 순위 조회기 (연속 실행 모드)")
    print("  종료: Ctrl+C")
    print("=" * 60)
    pass_num = 0
    while True:
        pass_num += 1
        print(f"\n\n{'='*60}")
        print(f"  패스 #{pass_num} 시작  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")
        try:
            run()
        except Exception as e:
            print(f"\n[오류] {e} — 60초 후 재시도")
            time.sleep(60)
        # 다음 패스 바로 시작 (키워드 간 딜레이가 이미 충분한 쿨타임)
