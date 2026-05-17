"""영업툴 — 쇼핑광고 DB 추출 (관리자 전용)"""
import streamlit as st
import os, sys, re, time, random, io, asyncio
from urllib.parse import quote, urlparse, parse_qs, unquote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from db import sb_load, sb_save

if st.session_state.get("auth_type") != "admin":
    st.error("🔒 관리자만 접근 가능합니다.")
    st.stop()

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,6}')
PHONE_RE = re.compile(r'0\d{1,2}[\s\-]?\d{3,4}[\s\-]?\d{4}')
FALLBACK_JSON = os.path.join(ROOT, "sales_leads_shopping.json")
SESSION_KEY   = "shopping_results"

BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-setuid-sandbox",
    "--disable-blink-features=AutomationControlled",
    "--no-zygote",
    "--disable-extensions",
    "--window-size=1366,768",
]

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins',   {get: () => [1,2,3,4,5]});
Object.defineProperty(navigator, 'languages', {get: () => ['ko-KR','ko','en']});
window.chrome = {runtime: {}};
"""

# ── Playwright Chromium 설치 (최초 1회) ──────────────────────────────────────
@st.cache_resource
def _install_browser():
    import subprocess
    for cmd in [
        ["playwright", "install", "chromium", "--with-deps"],
        ["playwright", "install", "chromium"],
    ]:
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=300)
            if r.returncode == 0:
                break
        except Exception:
            pass

_install_browser()

# ── 헬퍼 ─────────────────────────────────────────────────────────────────────
def _real_url(href: str) -> str:
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

def _store_key(href: str):
    """(store_url, store_id) 반환. 파싱 실패 시 (None, None)"""
    real = _real_url(href or "")
    if not real:
        return None, None
    if "smartstore.naver.com" in real:
        parts = urlparse(real).path.strip("/").split("/")
        if parts and parts[0] not in ["main","inflow","i","m","v","product","products",""]:
            sid = parts[0]
            return f"https://smartstore.naver.com/{sid}", sid
    url = real.split("?")[0]
    return (url or None), None

def _contacts(html: str):
    emails = [e for e in EMAIL_RE.findall(html)
              if not any(x in e.lower() for x in ["naver.com","example","kakao","google","daum"])]
    phones = PHONE_RE.findall(html)
    return (emails[0] if emails else "미확인"), (phones[0] if phones else "미확인")

# ── 비동기 수집 코어 ──────────────────────────────────────────────────────────
async def _scrape_async(keywords, max_pages, dedup, log_cb, status_cb, progress_cb):
    from playwright.async_api import async_playwright

    results  = []
    seen_key = set()

    playwright = None
    browser    = None
    context    = None
    page       = None

    try:
        log_cb("🚀 Playwright 시작")
        playwright = await async_playwright().start()

        log_cb("🖥️ 브라우저 생성 중...")
        browser = await playwright.chromium.launch(
            headless=True,
            args=BROWSER_ARGS,
        )
        log_cb("✅ 브라우저 생성 완료")

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
            viewport={"width": 1366, "height": 768},
        )
        log_cb("✅ Context 생성 완료")

        page = await context.new_page()
        await page.add_init_script(STEALTH_JS)
        log_cb("✅ Page 생성 완료")

        # ── 네이버 세션 확보 ────────────────────────────────────────────────────
        status_cb("🌐 네이버 세션 초기화 중...")
        log_cb("→ goto: https://www.naver.com")
        await page.goto("https://www.naver.com", wait_until="domcontentloaded", timeout=30000)
        log_cb("✅ naver.com 접속 성공")
        await asyncio.sleep(random.uniform(1.5, 2.5))

        total = len(keywords) * max_pages
        done  = 0

        for keyword in keywords:
            # ── 검색창 입력 ──────────────────────────────────────────────────
            status_cb(f"🔍 [{keyword}] 검색 중...")
            log_cb(f"── 키워드: {keyword}")
            try:
                sb = page.locator('input[name="query"]').first
                await sb.click()
                await asyncio.sleep(0.3)
                await sb.fill("")
                await asyncio.sleep(0.2)
                for ch in keyword:
                    await sb.type(ch, delay=random.randint(50, 130))
                await asyncio.sleep(0.5)
                await sb.press("Enter")
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                await asyncio.sleep(2)
                log_cb(f"✅ 검색 완료: {page.url[:60]}")
            except Exception as e:
                log_cb(f"⚠ 검색창 실패, 직접 이동: {e}")
                await page.goto(
                    f"https://search.naver.com/search.naver?query={quote(keyword)}",
                    wait_until="domcontentloaded", timeout=20000,
                )
                await asyncio.sleep(2)

            # 쇼핑 탭 이동 시도
            try:
                shop_tab = page.locator('a[href*="where=shopping"]').first
                if await shop_tab.count() > 0:
                    await shop_tab.click()
                    await page.wait_for_load_state("domcontentloaded", timeout=15000)
                    await asyncio.sleep(2)
            except Exception:
                pass

            for page_num in range(1, max_pages + 1):
                status_cb(f"📄 [{keyword}] {page_num}페이지 수집 중...")
                try:
                    if page_num > 1:
                        start = (page_num - 1) * 40 + 1
                        nav_url = (
                            f"https://search.naver.com/search.naver"
                            f"?where=shopping&query={quote(keyword)}&start={start}"
                        )
                        log_cb(f"→ goto: {nav_url[:70]}")
                        await page.goto(nav_url, wait_until="domcontentloaded", timeout=20000)
                        await asyncio.sleep(random.uniform(1.5, 2.5))

                    for y in [500, 1000, 1500, 2000]:
                        await page.evaluate(f"window.scrollTo(0,{y})")
                        await asyncio.sleep(0.5)

                    html = await page.content()
                    if "접속이 일시적으로 제한" in html:
                        log_cb(f"⛔ [{keyword}] {page_num}p 차단 — 건너뜀")
                        done += 1
                        progress_cb(done / total)
                        break

                    links = await page.locator('a[href*="smartstore.naver.com/"]').all()
                    page_count = 0
                    for link in links:
                        href = await link.get_attribute("href") or ""
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
                            name = (await link.inner_text()).strip().replace("\n", " ")
                        except Exception:
                            name = ""
                        if not name:
                            name = store_id or store_url.split("/")[-1]

                        try:
                            parent_html = await link.evaluate(
                                'el => el.closest("li,div,article")?.innerHTML || ""'
                            )
                        except Exception:
                            parent_html = ""
                        is_ad = any(x in parent_html for x in ["광고","adBadge","ad_badge","AdLabel"])
                        grade = next((g for g in ["프리미엄","빅파워","파워"] if g in parent_html), "")

                        results.append({
                            "keyword":        keyword,
                            "store_name":     name,
                            "store_url":      store_url,
                            "store_id":       store_id or "",
                            "is_ad":          "광고" if is_ad else "비광고",
                            "page":           f"{page_num}페이지",
                            "grade":          grade,
                            "email":          "미확인",
                            "phone":          "미확인",
                            "memo":           "",
                            "found_keywords": [keyword],
                        })
                        page_count += 1

                    log_cb(f"✅ [{keyword}] {page_num}p → {page_count}개 수집")

                except Exception as e:
                    log_cb(f"⚠ [{keyword}] {page_num}p 오류: {str(e)[:80]}")

                done += 1
                progress_cb(done / total)
                await asyncio.sleep(random.uniform(1, 2))

        # ── 연락처 수집 ─────────────────────────────────────────────────────────
        log_cb(f"📞 연락처 수집 시작 (총 {len(results)}개)...")
        for i, row in enumerate(results):
            if "smartstore.naver.com" not in (row.get("store_url") or ""):
                continue
            status_cb(f"📞 연락처 {i+1}/{len(results)}: {row['store_name'][:15]}")
            try:
                await page.goto(row["store_url"], wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(random.uniform(1, 1.5))
                email, phone = _contacts(await page.content())
                row["email"] = email
                row["phone"] = phone
            except Exception:
                pass

    except Exception as e:
        log_cb(f"❌ 치명적 오류: {str(e)[:120]}")
        raise

    finally:
        log_cb("🔚 브라우저 종료 중...")
        if page and not page.is_closed():
            try:
                await page.close()
            except Exception:
                pass
        if context:
            try:
                await context.close()
            except Exception:
                pass
        if browser:
            try:
                await browser.close()
                log_cb("✅ 브라우저 종료 완료")
            except Exception:
                pass
        if playwright:
            try:
                await playwright.stop()
            except Exception:
                pass

    return results


# ── 동기 래퍼 (Streamlit → asyncio) ──────────────────────────────────────────
def _scrape(keywords, max_pages, dedup, prog_bar, status_el, log_el):
    logs = []

    def log_cb(msg):
        logs.append(msg)
        log_el.text("\n".join(logs[-8:]))

    def status_cb(msg):
        status_el.text(msg)

    def progress_cb(val):
        prog_bar.progress(min(val, 1.0))

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(
            _scrape_async(keywords, max_pages, dedup, log_cb, status_cb, progress_cb)
        )
        return result
    finally:
        try:
            loop.close()
        except Exception:
            pass


# ── 기존 데이터 로드 / 병합 ───────────────────────────────────────────────────
def _load_existing():
    raw = sb_load("sales_leads_shopping", fallback_path=FALLBACK_JSON)
    return raw if isinstance(raw, list) else []

def _merge(existing, new_rows):
    idx = {}
    for r in existing:
        k = r.get("store_id") or r.get("store_url", "")
        if k:
            idx[k] = r
    for r in new_rows:
        k = r.get("store_id") or r.get("store_url", "")
        if not k:
            continue
        if k in idx:
            for kw in r.get("found_keywords", []):
                if kw not in idx[k].get("found_keywords", []):
                    idx[k]["found_keywords"].append(kw)
        else:
            idx[k] = r
    return list(idx.values())

def _to_csv(rows):
    import pandas as pd
    df = pd.DataFrame(rows)
    if "found_keywords" in df.columns:
        df["found_keywords"] = df["found_keywords"].apply(
            lambda v: ", ".join(v) if isinstance(v, list) else str(v)
        )
    cols = ["keyword","store_name","is_ad","page","store_url","grade","email","phone","memo","found_keywords"]
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df[cols].to_csv(index=False).encode("utf-8-sig")

def _to_xlsx(rows):
    import pandas as pd
    df = pd.DataFrame(rows)
    if "found_keywords" in df.columns:
        df["found_keywords"] = df["found_keywords"].apply(
            lambda v: ", ".join(v) if isinstance(v, list) else str(v)
        )
    cols = ["keyword","store_name","is_ad","page","store_url","grade","email","phone","memo","found_keywords"]
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df[cols].to_excel(w, index=False, sheet_name="쇼핑광고DB")
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
# UI
# ══════════════════════════════════════════════════════════════════════════════
st.title("🛍️ 쇼핑광고 DB 추출")
st.caption("네이버 쇼핑 검색 결과에서 광고 집행 중인 스마트스토어 DB를 수집합니다.")

col_kw, col_cfg, col_info = st.columns([3, 2, 2], gap="large")

with col_kw:
    st.markdown("#### 키워드")
    kw_raw = st.text_area(
        "키워드 (줄바꿈으로 구분)", height=160,
        placeholder="예:\n강아지사료\n고양이간식\n반려동물용품",
        key="shop_kw_raw",
    )

with col_cfg:
    st.markdown("#### 설정")
    max_pages = st.number_input("수집 페이지 수", min_value=1, max_value=10,
                                value=2, step=1, key="shop_pages")
    dedup = st.checkbox("중복 제거 (스토어 기준)", value=True, key="shop_dedup")
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
    run_btn = st.button("🔍 수집 시작", type="primary",
                        use_container_width=True, key="shop_run")

with col_info:
    st.markdown("#### 수집 항목")
    st.markdown(
        "- 수집 키워드\n- 스토어명\n- 광고여부\n"
        "- 노출 페이지\n- 스토어 URL\n- 판매자 등급\n"
        "- 이메일 / 연락처\n- 메모"
    )

st.divider()

if run_btn:
    keywords = [k.strip() for k in kw_raw.splitlines() if k.strip()]
    if not keywords:
        st.warning("키워드를 입력해주세요.")
    else:
        prog   = st.progress(0.0)
        status = st.empty()
        logbox = st.empty()
        new_rows = []
        try:
            new_rows = _scrape(keywords, int(max_pages), dedup, prog, status, logbox)
        except Exception as e:
            st.error(f"수집 오류: {e}")

        prog.empty()
        status.empty()
        logbox.empty()

        if new_rows:
            merged = _merge(_load_existing(), new_rows)
            st.session_state[SESSION_KEY] = merged
            st.success(f"✅ 수집 완료 — 신규 {len(new_rows)}건 / 전체 {len(merged)}건")
        else:
            st.warning("수집된 데이터가 없습니다. 로그를 확인해주세요.")

if SESSION_KEY not in st.session_state:
    loaded = _load_existing()
    if loaded:
        st.session_state[SESSION_KEY] = loaded

results = st.session_state.get(SESSION_KEY, [])

if results:
    import pandas as pd

    display_rows = []
    for r in results:
        dr = dict(r)
        dr["found_keywords"] = ", ".join(dr.get("found_keywords", []) or [])
        display_rows.append(dr)

    df = pd.DataFrame(display_rows)
    col_order = ["keyword","store_name","is_ad","page","store_url","grade","email","phone","memo"]
    col_rename = {
        "keyword": "수집키워드", "store_name": "스토어명", "is_ad": "광고여부",
        "page": "노출페이지", "store_url": "스토어URL", "grade": "등급",
        "email": "이메일", "phone": "연락처", "memo": "메모",
    }
    for c in col_order:
        if c not in df.columns:
            df[c] = ""
    df_disp = df[col_order].rename(columns=col_rename).copy()
    df_disp.insert(0, "선택", False)

    st.markdown(f"**총 {len(df_disp)}건**")
    edited = st.data_editor(
        df_disp, use_container_width=True, hide_index=True,
        column_config={
            "선택":     st.column_config.CheckboxColumn("선택", width="small"),
            "수집키워드": st.column_config.TextColumn(disabled=True),
            "스토어명":  st.column_config.TextColumn(disabled=True),
            "광고여부":  st.column_config.TextColumn(disabled=True, width="small"),
            "노출페이지": st.column_config.TextColumn(disabled=True, width="small"),
            "스토어URL": st.column_config.LinkColumn(disabled=True),
            "등급":     st.column_config.TextColumn(disabled=True, width="small"),
            "이메일":   st.column_config.TextColumn(disabled=True),
            "연락처":   st.column_config.TextColumn(disabled=True),
            "메모":    st.column_config.TextColumn(disabled=False),
        },
        key="shop_editor",
    )

    if edited is not None:
        for idx, row in edited.iterrows():
            if idx < len(results):
                results[idx]["memo"] = row.get("메모", "")
        st.session_state[SESSION_KEY] = results

    a1, a2, a3, a4 = st.columns(4)
    with a1:
        if st.button("🗑️ 선택 삭제", use_container_width=True, key="shop_del"):
            if edited is not None:
                keep = [
                    results[i] for i, r in edited.iterrows()
                    if not r.get("선택", False) and i < len(results)
                ]
                st.session_state[SESSION_KEY] = keep
                st.rerun()
    with a2:
        if st.button("💾 Supabase 저장", use_container_width=True, key="shop_save"):
            sb_save("sales_leads_shopping", results, FALLBACK_JSON)
            st.success("저장 완료")
    with a3:
        st.download_button("📥 CSV", _to_csv(results), "쇼핑광고DB.csv",
                           "text/csv", use_container_width=True, key="shop_csv")
    with a4:
        st.download_button(
            "📊 XLSX", _to_xlsx(results), "쇼핑광고DB.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True, key="shop_xlsx",
        )
else:
    st.info("키워드를 입력하고 '수집 시작'을 눌러주세요.")
