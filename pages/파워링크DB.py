"""영업툴 — 파워링크 DB 추출 (관리자 전용)"""
import streamlit as st
import os
import sys
import re
import time
import random
import io
from urllib.parse import quote, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from db import sb_load, sb_save

# ── 관리자 전용 ───────────────────────────────────────────────────────────────
if st.session_state.get("auth_type") != "admin":
    st.error("관리자만 접근할 수 있는 페이지입니다.")
    st.stop()

# ── 정규식 ────────────────────────────────────────────────────────────────────
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,6}')
PHONE_RE = re.compile(r'0\d{1,2}[\s\-]?\d{3,4}[\s\-]?\d{4}')

FALLBACK_JSON = os.path.join(ROOT, "sales_leads_powerlink.json")
SESSION_KEY   = "powerlink_results"

# ── Playwright 브라우저 설치 (캐시) ───────────────────────────────────────────
@st.cache_resource
def _install_browser():
    import subprocess
    try:
        subprocess.run(
            ["playwright", "install", "chromium"],
            capture_output=True, timeout=120,
        )
    except Exception:
        pass

_install_browser()

# ── 수집 함수 ─────────────────────────────────────────────────────────────────
def _scrape_powerlink(keywords, region, max_pages, progress_bar, status_text):
    from playwright.sync_api import sync_playwright

    results      = []
    seen_domains = set()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
        )
        page = ctx.new_page()

        total = len(keywords) * max_pages
        done  = 0

        for keyword in keywords:
            query = f"{keyword} {region}".strip() if region else keyword

            for page_num in range(1, max_pages + 1):
                status_text.text(f"수집 중: [{query}] {page_num}페이지...")
                start = (page_num - 1) * 10 + 1
                url = (
                    f"https://search.naver.com/search.naver"
                    f"?query={quote(query)}&start={start}"
                )

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    time.sleep(random.uniform(1.5, 2.5))

                    # 파워링크 광고 영역 탐색
                    ad_section = page.locator(
                        "#ad_area, [class*='ad_area'], [class*='lst_ad'], "
                        "#powerlink_top_bx, .cm_ad_p"
                    ).first

                    if ad_section.count() > 0:
                        ad_links = ad_section.locator("a[href]").all()
                    else:
                        ad_links = page.locator(
                            "[class*='ad'] a[href], .ad_tit a, "
                            "[class*='power_link'] a[href]"
                        ).all()

                    for link in ad_links:
                        href = link.get_attribute("href") or ""
                        if not href or href.startswith("#") or "naver.com" in href:
                            continue

                        try:
                            parsed = urlparse(href)
                            domain = parsed.netloc.replace("www.", "")
                        except Exception:
                            domain = ""

                        if not domain:
                            continue

                        if domain in seen_domains:
                            # 키워드 누적
                            for r in results:
                                if r["domain"] == domain and keyword not in r["found_keywords"]:
                                    r["found_keywords"].append(keyword)
                            continue
                        seen_domains.add(domain)

                        biz_name = link.inner_text().strip() or domain

                        results.append({
                            "keyword":        keyword,
                            "biz_name":       biz_name,
                            "is_ad":          "광고",
                            "page":           f"{page_num}페이지",
                            "landing_url":    href,
                            "domain":         domain,
                            "email":          "미확인",
                            "phone":          "미확인",
                            "memo":           "",
                            "found_keywords": [keyword],
                        })
                except Exception:
                    pass

                done += 1
                progress_bar.progress(done / total)
                time.sleep(random.uniform(0.5, 1.0))

        # ── 연락처 수집 ───────────────────────────────────────────────────────
        for i, row in enumerate(results):
            status_text.text(
                f"연락처 수집 중: {row['domain']} ({i + 1}/{len(results)})"
            )
            try:
                page.goto(row["landing_url"], wait_until="domcontentloaded", timeout=15000)
                time.sleep(1.0)
                html = page.content()

                emails = EMAIL_RE.findall(html)
                phones = PHONE_RE.findall(html)
                emails = [
                    e for e in emails
                    if not any(x in e.lower() for x in ["naver.com", "example", "kakao"])
                ]

                if emails:
                    row["email"] = emails[0]
                if phones:
                    row["phone"] = phones[0]
            except Exception:
                pass

        browser.close()

    return results


# ── 기존 데이터 로드 ──────────────────────────────────────────────────────────
def _load_existing():
    raw = sb_load("sales_leads_powerlink", fallback_path=FALLBACK_JSON)
    if isinstance(raw, list):
        return raw
    return []


# ── 병합 (domain 기준 중복 제거) ─────────────────────────────────────────────
def _merge(existing, new_rows):
    dom_map = {}
    for row in existing:
        key = row.get("domain", "")
        if key:
            dom_map[key] = row

    for row in new_rows:
        key = row.get("domain", "")
        if not key:
            continue
        if key in dom_map:
            prev = dom_map[key]
            prev_kws = prev.get("found_keywords", [])
            for kw in row.get("found_keywords", []):
                if kw not in prev_kws:
                    prev_kws.append(kw)
            prev["found_keywords"] = prev_kws
        else:
            dom_map[key] = row

    return list(dom_map.values())


# ── XLSX 바이트 생성 ──────────────────────────────────────────────────────────
def _to_xlsx(rows):
    import pandas as pd

    df = pd.DataFrame(rows)
    if "found_keywords" in df.columns:
        df["found_keywords"] = df["found_keywords"].apply(
            lambda v: ", ".join(v) if isinstance(v, list) else str(v)
        )
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="파워링크DB")
    return buf.getvalue()


# ── CSV 바이트 생성 ───────────────────────────────────────────────────────────
def _to_csv(rows):
    import pandas as pd

    df = pd.DataFrame(rows)
    if "found_keywords" in df.columns:
        df["found_keywords"] = df["found_keywords"].apply(
            lambda v: ", ".join(v) if isinstance(v, list) else str(v)
        )
    return df.to_csv(index=False).encode("utf-8-sig")


# ══════════════════════════════════════════════════════════════════════════════
# UI
# ══════════════════════════════════════════════════════════════════════════════
st.title("🔗 파워링크 DB 추출")
st.caption("네이버 검색 파워링크 광고주 연락처를 자동 수집합니다.")

# ── 입력 영역 ─────────────────────────────────────────────────────────────────
col_kw, col_cfg = st.columns([3, 2], gap="large")

with col_kw:
    st.markdown("#### 키워드 입력")
    kw_raw = st.text_area(
        "키워드 (줄바꿈으로 구분)",
        placeholder="예:\n이혼변호사\n재산분할\n양육권소송",
        height=150,
        key="pl_kw_raw",
    )

with col_cfg:
    st.markdown("#### 설정")
    region = st.text_input(
        "지역 (선택 — 비워두면 전국)",
        placeholder="예: 강남, 서울, 부산",
        key="pl_region",
    )
    max_pages = st.number_input(
        "수집 페이지 수", min_value=1, max_value=5, value=2, step=1,
        key="pl_max_pages",
    )
    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    run_btn = st.button("🔍 수집 시작", type="primary", use_container_width=True,
                        key="pl_run")

st.divider()

# ── 수집 실행 ─────────────────────────────────────────────────────────────────
if run_btn:
    keywords = [k.strip() for k in kw_raw.splitlines() if k.strip()]
    if not keywords:
        st.warning("키워드를 하나 이상 입력해주세요.")
    else:
        prog = st.progress(0.0)
        stxt = st.empty()
        with st.spinner("Playwright 크롬 실행 중..."):
            try:
                new_rows = _scrape_powerlink(
                    keywords, region.strip(), int(max_pages), prog, stxt
                )
            except Exception as e:
                st.error(f"수집 중 오류: {e}")
                new_rows = []

        stxt.empty()
        prog.empty()

        if new_rows:
            existing = _load_existing()
            merged   = _merge(existing, new_rows)
            st.session_state[SESSION_KEY] = merged
            st.success(f"수집 완료 — 신규 {len(new_rows)}건 / 전체 {len(merged)}건")
        else:
            st.warning("수집된 데이터가 없습니다. 키워드·네트워크 상태를 확인해주세요.")

# ── 기존 데이터 초기 로드 ─────────────────────────────────────────────────────
if SESSION_KEY not in st.session_state:
    loaded = _load_existing()
    if loaded:
        st.session_state[SESSION_KEY] = loaded

# ── 결과 테이블 ───────────────────────────────────────────────────────────────
results = st.session_state.get(SESSION_KEY, [])

if results:
    import pandas as pd

    display_rows = []
    for r in results:
        dr = dict(r)
        dr["found_keywords"] = (
            ", ".join(dr["found_keywords"])
            if isinstance(dr.get("found_keywords"), list)
            else str(dr.get("found_keywords", ""))
        )
        display_rows.append(dr)

    df_all = pd.DataFrame(display_rows)

    col_order = [
        "keyword", "biz_name", "is_ad", "page",
        "landing_url", "domain", "email", "phone", "memo",
    ]
    col_rename = {
        "keyword":     "수집키워드",
        "biz_name":    "업체명",
        "is_ad":       "광고여부",
        "page":        "노출페이지",
        "landing_url": "랜딩URL",
        "domain":      "도메인",
        "email":       "이메일",
        "phone":       "연락처",
        "memo":        "메모",
    }

    for c in col_order:
        if c not in df_all.columns:
            df_all[c] = ""

    df_display = df_all[col_order].rename(columns=col_rename).copy()
    df_display.insert(0, "선택", False)

    st.markdown(f"**총 {len(df_display)}건**")

    edited = st.data_editor(
        df_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "선택":     st.column_config.CheckboxColumn("선택", width="small"),
            "수집키워드": st.column_config.TextColumn("수집키워드", disabled=True),
            "업체명":    st.column_config.TextColumn("업체명",    disabled=True),
            "광고여부":  st.column_config.TextColumn("광고여부",  disabled=True, width="small"),
            "노출페이지": st.column_config.TextColumn("노출페이지", disabled=True, width="small"),
            "랜딩URL":   st.column_config.LinkColumn("랜딩URL",   disabled=True),
            "도메인":    st.column_config.TextColumn("도메인",    disabled=True),
            "이메일":    st.column_config.TextColumn("이메일",    disabled=True),
            "연락처":    st.column_config.TextColumn("연락처",    disabled=True),
            "메모":      st.column_config.TextColumn("메모",      disabled=False),
        },
        key="pl_editor",
    )

    # 메모 역동기화
    if edited is not None:
        for idx, row in edited.iterrows():
            if idx < len(results):
                results[idx]["memo"] = row.get("메모", "")
        st.session_state[SESSION_KEY] = results

    # ── 액션 버튼 ─────────────────────────────────────────────────────────────
    act1, act2, act3, act4 = st.columns(4)

    with act1:
        if st.button("🗑️ 선택 삭제", use_container_width=True, key="pl_del"):
            if edited is not None:
                keep = [
                    results[i]
                    for i, row in edited.iterrows()
                    if not row.get("선택", False) and i < len(results)
                ]
                st.session_state[SESSION_KEY] = keep
                st.rerun()

    with act2:
        if st.button("💾 Supabase 저장", use_container_width=True, key="pl_save"):
            ok = sb_save("sales_leads_powerlink", results, FALLBACK_JSON)
            if ok:
                st.success("Supabase에 저장했습니다.")
            else:
                st.warning(f"Supabase 저장 실패 — 로컬 JSON({FALLBACK_JSON})에 저장했습니다.")

    with act3:
        csv_bytes = _to_csv(results)
        st.download_button(
            "📥 CSV 다운로드",
            data=csv_bytes,
            file_name="파워링크DB.csv",
            mime="text/csv",
            use_container_width=True,
            key="pl_csv",
        )

    with act4:
        xlsx_bytes = _to_xlsx(results)
        st.download_button(
            "📊 XLSX 다운로드",
            data=xlsx_bytes,
            file_name="파워링크DB.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="pl_xlsx",
        )

else:
    st.info("수집된 데이터가 없습니다. 키워드를 입력하고 '수집 시작'을 눌러주세요.")
