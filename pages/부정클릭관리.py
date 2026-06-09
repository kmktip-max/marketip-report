"""부정클릭 관리 — 스마트로그 UI 스타일 (관리자 전용)"""
import json
import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import requests
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fraud.db import (
    init_db,
    log_click,
    get_clicks_for_ip,
    get_ip_summary,
    get_mobile_sessions,
    get_suspect_ip_set,
    get_blocked_ip_set,
    get_naver_excluded_ips,
    get_naver_excluded_ip_set,
    add_naver_excluded_ip,
    remove_naver_excluded_ip,
    check_auto_block_candidates,
    get_client_settings,
    save_client_settings,
    block_ip,
    unblock_ip,
    clear_suspect,
    _use_sb,
    _sb_url,
)
from fraud.detector import run_detection

if st.session_state.get("auth_type") != "admin":
    st.error("🔒 관리자만 접근 가능합니다.")
    st.stop()

init_db()

# ── CSS (스마트로그 스타일) ─────────────────────────────────────────────────
st.markdown("""
<style>
/* 전체 배경 */
section.main > div { background: #f5f6fa; }

/* 테이블 공통 */
.sl-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
    background: #fff;
    border: 1px solid #e8eaed;
    border-radius: 6px;
    overflow: hidden;
}
.sl-table th {
    background: #f8f9fb;
    padding: 9px 12px;
    text-align: left;
    border-bottom: 1px solid #e0e3e8;
    color: #555;
    font-weight: 600;
    white-space: nowrap;
}
.sl-table th.center { text-align: center; }
.sl-table td {
    padding: 9px 12px;
    border-bottom: 1px solid #f2f3f5;
    vertical-align: middle;
    color: #333;
    white-space: nowrap;
}
.sl-table tr:last-child td { border-bottom: none; }
.sl-table tr:hover td { background: #f0f7ff; }
.sl-row-suspect td { background: #f0fdf4 !important; }
.sl-row-strong td { background: #dcfce7 !important; }
.sl-row-blocked td { background: #fef9c3 !important; }
.sl-divider { border-left: 1px solid #e8eaed; }

/* 네이버 N 뱃지 */
.n-badge {
    display: inline-block;
    background: #03C75A;
    color: white;
    font-size: 10px;
    font-weight: 900;
    width: 15px; height: 15px;
    line-height: 15px;
    text-align: center;
    border-radius: 2px;
    margin-right: 3px;
    vertical-align: middle;
}
/* IP 링크 */
.ip-text { color: #1a73e8; font-weight: 600; }
.plus-btn {
    display: inline-block;
    color: #888;
    border: 1px solid #ccc;
    border-radius: 3px;
    width: 16px; height: 16px;
    line-height: 14px;
    text-align: center;
    font-size: 12px;
    margin-right: 4px;
}

/* 설정 row 레이블 */
.cfg-label {
    font-weight: 700;
    font-size: 14px;
    color: #222;
    padding-top: 6px;
}
.cfg-sub {
    font-size: 12px;
    color: #888;
    margin-top: 2px;
}
.cfg-divider { border-top: 1px solid #f0f0f0; margin: 8px 0; }

/* 페이지 제목 */
.sl-page-title { font-size: 20px; font-weight: 700; color: #222; margin-bottom: 4px; }

/* 섹션 제목 (설정 페이지 내) */
.sl-section-title { font-size: 16px; font-weight: 700; color: #222; margin: 24px 0 4px; }
.sl-section-sub   { font-size: 13px; color: #888; margin-bottom: 16px; }

/* 녹색 안내 배너 */
.sl-green-box {
    background: #f0fdf4;
    border: 1px solid #bbf7d0;
    border-radius: 6px;
    padding: 14px 18px;
    font-size: 13px;
    color: #166534;
    margin-bottom: 16px;
    line-height: 1.7;
}

/* 조회하기 버튼 영역 */
.filter-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;
}

/* 인라인 액션 버튼 */
.btn-sm-red {
    display: inline-block;
    background: #ef4444;
    color: white;
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 4px;
    font-weight: 600;
}
.btn-sm-blue {
    display: inline-block;
    background: #3b82f6;
    color: white;
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 4px;
    font-weight: 600;
}
</style>
""", unsafe_allow_html=True)

# ── 광고주 로딩 ───────────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def _load_clients():
    try:
        from report_engine.storage import load_clients
        return load_clients() or []
    except Exception:
        pass
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        p = os.path.join(root, "clients.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []

clients      = _load_clients()
client_names = [c.get("name", c.get("id", "")) for c in clients]
client_ids   = [c.get("id", "") for c in clients]

if not clients:
    st.warning("등록된 광고주가 없습니다.")
    st.stop()

# ── 헬퍼 ──────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def _carrier_lookup(ip: str) -> str:
    try:
        r = requests.get(
            f"http://ip-api.com/json/{ip}?fields=isp,org",
            timeout=2,
        )
        if r.ok:
            d = r.json()
            isp = d.get("isp") or d.get("org") or ""
            for short, kws in [
                ("주식회사 케이티", ["KT", "Olleh", "Korea Telecom"]),
                ("에스케이텔레콤(주)", ["SKT", "SK Telecom"]),
                ("LG U+", ["LG U+", "LGU+", "LG Uplus"]),
                ("에스케이브로드밴드주식회사", ["SK Broadband"]),
            ]:
                if any(k in isp for k in kws):
                    return short
            return isp[:20] if isp else "-"
    except Exception:
        pass
    return "-"


def _carrier(row):
    stored = (row.get("carrier") or "").strip()
    if stored:
        return stored
    return _carrier_lookup(row.get("ip_address", ""))


def fmt_stay(s) -> str:
    s = int(s or 0)
    if s >= 3600:
        return "1시간 이상"
    if s >= 60:
        return f"{s // 60}분 {s % 60}초"
    return f"{s}초"


@st.cache_data(ttl=30, show_spinner=False)
def _cfg(cid):
    return get_client_settings(cid)


# ── 필터 바 헬퍼 ─────────────────────────────────────────────────────────────
def filter_bar(key: str):
    """스마트로그 스타일 상단 필터 바. (start_date, end_date, min_clicks) 반환."""
    fc1, fc2, fc3, fc4 = st.columns([2, 2, 2, 1])
    with fc1:
        period = st.selectbox(
            "기간",
            ["오늘", "7일", "30일", "직접 입력"],
            key=f"{key}_period",
            label_visibility="collapsed",
        )
    now = datetime.now()
    if period == "오늘":
        default_s = now.date()
        default_e = now.date()
    elif period == "30일":
        default_s = (now - timedelta(days=29)).date()
        default_e = now.date()
    elif period == "직접 입력":
        default_s = (now - timedelta(days=6)).date()
        default_e = now.date()
    else:  # 7일
        default_s = (now - timedelta(days=6)).date()
        default_e = now.date()

    with fc2:
        if period == "직접 입력":
            dr = st.date_input(
                "기간",
                value=(default_s, default_e),
                key=f"{key}_daterange",
                label_visibility="collapsed",
            )
            start_s = str(dr[0]) if isinstance(dr, (list, tuple)) and len(dr) >= 1 else str(default_s)
            end_s   = str(dr[1]) if isinstance(dr, (list, tuple)) and len(dr) == 2 else str(default_e)
        else:
            st.markdown(
                f'<div style="padding:6px 0;font-size:13px;color:#555;">'
                f'{default_s.strftime("%Y.%m.%d")} - {default_e.strftime("%Y.%m.%d")}</div>',
                unsafe_allow_html=True,
            )
            start_s = str(default_s)
            end_s   = str(default_e)

    with fc3:
        min_clicks = st.number_input(
            "광고 클릭 횟수(유효)",
            min_value=1, max_value=100, value=3,
            key=f"{key}_min",
            label_visibility="collapsed",
        )
        st.caption(f"+ 광고 클릭 횟수(유효): {min_clicks} 회 이상")

    with fc4:
        query = st.button("조회하기", key=f"{key}_query", type="primary", use_container_width=True)
        if query:
            st.cache_data.clear()

    return start_s, end_s, min_clicks


# ── HTML 테이블: 광고 클릭 IP ──────────────────────────────────────────────────
def render_ip_table(rows, suspect_map, excluded_set, blocked_set, selected_ip=None) -> str:
    html = """
    <table class="sl-table">
      <thead>
        <tr>
          <th rowspan="2">IP</th>
          <th rowspan="2">통신사</th>
          <th rowspan="2" class="center">기간내<br>클릭수</th>
          <th colspan="4" class="center sl-divider">전환</th>
          <th rowspan="2">누적<br>체류시간</th>
          <th colspan="3" class="center sl-divider">최근 광고클릭 내역(유효)</th>
        </tr>
        <tr style="font-size:11px;color:#888;">
          <th class="center sl-divider">회원</th>
          <th class="center">주문</th>
          <th class="center">문의</th>
          <th class="center">매출</th>
          <th class="sl-divider">광고종류</th>
          <th>키워드(순위)</th>
          <th>클릭시간</th>
        </tr>
      </thead>
      <tbody>
    """
    for row in rows:
        ip     = row["ip_address"]
        car    = _carrier(row)
        clicks = row["total_clicks"]
        conv   = int(row.get("conversions") or 0)
        stay   = fmt_stay(row.get("total_stay") or 0)
        ad_t   = row.get("ad_type") or "파워링크"
        kw     = row.get("last_keyword") or "-"
        last   = (row.get("last_click") or "")[:19]

        score = suspect_map.get(ip, {}).get("risk_score", 0)
        if ip in blocked_set or score >= 80:
            row_cls = "sl-row-strong"
        elif score >= 50 or ip in excluded_set:
            row_cls = "sl-row-suspect"
        else:
            row_cls = ""

        sel_style = "outline:2px solid #3b82f6;" if ip == selected_ip else ""

        html += f"""
        <tr class="{row_cls}" style="{sel_style}">
          <td><span class="plus-btn">+</span>🇰🇷 <span class="ip-text">{ip}</span></td>
          <td>{car}</td>
          <td class="center">{clicks}</td>
          <td class="center sl-divider">{conv}</td>
          <td class="center">0</td>
          <td class="center">0</td>
          <td class="center">W0</td>
          <td>{stay}</td>
          <td class="sl-divider"><span class="n-badge">N</span>{ad_t}<br>
              <span style="color:#aaa;font-size:11px;">네이버 통합검색</span></td>
          <td>{kw}</td>
          <td style="color:#666;">{last}</td>
        </tr>
        """
    html += "</tbody></table>"
    return html


# ── HTML 테이블: 스마트폰 추적 ────────────────────────────────────────────────
def render_mobile_table(rows) -> str:
    html = """
    <table class="sl-table">
      <thead>
        <tr>
          <th>핸드폰</th>
          <th>단말기 세션</th>
          <th class="center">기간내<br>클릭수</th>
          <th>휴대폰 종류</th>
          <th>휴대폰 모델</th>
          <th>누적 체류시간</th>
          <th>통신사</th>
          <th colspan="3" class="center sl-divider">최근 광고클릭 내역(유효)</th>
        </tr>
        <tr style="font-size:11px;color:#888;">
          <th></th><th></th><th></th><th></th><th></th><th></th><th></th>
          <th class="sl-divider">광고종류</th>
          <th>키워드(순위)</th>
          <th>클릭시간</th>
        </tr>
      </thead>
      <tbody>
    """
    for row in rows:
        sess  = row.get("session_key", "")[:8]
        os_   = row.get("os") or row.get("phone_type") or ""
        model = row.get("phone_model") or ""
        car   = _carrier(row)
        clicks = row["total_clicks"]
        stay  = fmt_stay(0)  # sessions don't aggregate stay
        ad_t  = row.get("ad_type") or "파워링크"
        kw    = row.get("last_keyword") or "-"
        last  = (row.get("last_click") or "")[:19]

        # 폰 아이콘
        if "iphone" in (os_ + model).lower() or "ios" in os_.lower():
            icon = "📱"
            phone_type = "iPhone"
        elif "android" in os_.lower() or "galaxy" in model.lower() or "SM-" in model:
            icon = "📱"
            phone_type = "갤럭시" if "galaxy" in model.lower() or "SM-" in model else "Android"
        else:
            icon = "📱"
            phone_type = os_ or "-"

        html += f"""
        <tr>
          <td>{icon}</td>
          <td><span class="plus-btn">+</span><span class="ip-text">{sess}</span></td>
          <td class="center">{clicks}</td>
          <td>{phone_type}</td>
          <td>{model or "-"}</td>
          <td>{stay}</td>
          <td>{car}</td>
          <td class="sl-divider"><span class="n-badge">N</span>{ad_t}<br>
              <span style="color:#aaa;font-size:11px;">네이버 통합검색 - 모바일</span></td>
          <td>{kw}</td>
          <td style="color:#666;">{last}</td>
        </tr>
        """
    html += "</tbody></table>"
    return html


# ── HTML 테이블: 네이버 노출제한 IP ───────────────────────────────────────────
def render_naver_table(rows) -> str:
    html = """
    <table class="sl-table">
      <thead>
        <tr>
          <th>IP</th>
          <th>메모</th>
          <th>등록일</th>
          <th class="center">광고클릭수<br>(유효/전체)</th>
          <th class="center">IP변경</th>
          <th class="center">일순방문수</th>
          <th class="center">전환수<br>(회원/주문/주문금액)</th>
          <th>상태변경</th>
        </tr>
      </thead>
      <tbody>
    """
    for row in rows:
        ip     = row["ip_address"]
        memo   = row.get("memo") or ""
        reg_dt = (row.get("registered_at") or "")[:10]
        valid  = row.get("ad_clicks_valid", 0)
        total  = row.get("ad_clicks_total", 0)
        visits = row.get("daily_visits", 0)
        sync   = "✅" if row.get("naver_synced") else ""

        html += f"""
        <tr>
          <td><span class="plus-btn">+</span>🇰🇷 <span class="ip-text">{ip}</span> {sync}</td>
          <td style="color:#555;">{memo}</td>
          <td style="color:#666;">{reg_dt}</td>
          <td class="center">{valid}/{total}</td>
          <td class="center">0</td>
          <td class="center">{visits}</td>
          <td class="center">0/0/0</td>
          <td><span style="color:#ef4444;border:1px solid #fca5a5;border-radius:999px;padding:2px 10px;font-size:12px;cursor:pointer;">⊗ 삭제</span></td>
        </tr>
        """
    html += "</tbody></table>"
    return html


# ── 설정 행 레이아웃 헬퍼 ─────────────────────────────────────────────────────
def _cfg_row(label, sub=""):
    lc, rc = st.columns([3, 5])
    with lc:
        st.markdown(
            f'<div class="cfg-label">{label}</div>'
            + (f'<div class="cfg-sub">{sub}</div>' if sub else ""),
            unsafe_allow_html=True,
        )
    return rc


# ══════════════════════════════════════════════════════════════════════════════
# 페이지 헤더
# ══════════════════════════════════════════════════════════════════════════════
h1, h2 = st.columns([3, 1])
with h1:
    st.markdown('<div class="sl-page-title">🛡️ 부정클릭 관리</div>', unsafe_allow_html=True)
with h2:
    sel_idx = st.selectbox(
        "광고주",
        range(len(clients)),
        format_func=lambda i: client_names[i],
        key="fd_client_idx",
        label_visibility="collapsed",
    )

client = clients[sel_idx]
cid    = client_ids[sel_idx]
cfg    = _cfg(cid)

# ══════════════════════════════════════════════════════════════════════════════
# 메인 탭
# ══════════════════════════════════════════════════════════════════════════════
TAB_IP, TAB_MOB, TAB_NAVER, TAB_CFG = st.tabs([
    "광고 클릭 IP",
    "스마트폰 추적",
    "네이버 노출제한 IP",
    "부정클릭 설정",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — 광고 클릭 IP
# ══════════════════════════════════════════════════════════════════════════════
with TAB_IP:
    start_s, end_s, min_clicks = filter_bar("ip")

    # 위치정보 보기 (시각적 토글, 현재는 미구현)
    st.checkbox("□ 위치정보 보기", key="ip_loc", value=False, label_visibility="visible")

    # 데이터 로드
    ip_rows     = get_ip_summary(cid, start_s, end_s)
    suspect_map = get_suspect_ip_set(cid)
    excluded_set = get_naver_excluded_ip_set(cid)
    blocked_set  = get_blocked_ip_set(cid)

    ip_rows = [r for r in ip_rows if r["total_clicks"] >= min_clicks]

    # 선택된 IP (상세)
    sel_ip = st.session_state.get("ip_sel_ip")

    # 테이블 렌더링
    if not ip_rows:
        st.info("해당 기간 조건에 맞는 IP가 없습니다.")
    else:
        st.markdown(render_ip_table(ip_rows, suspect_map, excluded_set, blocked_set, sel_ip),
                    unsafe_allow_html=True)
        st.caption(f"총 {len(ip_rows)}개 IP")

        # IP 선택 → 상세 + 액션
        st.markdown("---")
        ip_options = [r["ip_address"] for r in ip_rows]
        ac1, ac2, ac3, ac4 = st.columns([3, 1, 1, 1])
        with ac1:
            chosen = st.selectbox("IP 선택 (상세 조회 · 차단)", ["— 선택 —"] + ip_options,
                                  key="ip_sel_ip", label_visibility="collapsed")

        if chosen and chosen != "— 선택 —":
            with ac2:
                if chosen not in blocked_set:
                    if st.button("차단", key="ip_blk", type="primary"):
                        block_ip(cid, chosen, f"수동차단", "admin")
                        st.success(f"{chosen} 차단 완료")
                        st.cache_data.clear(); st.rerun()
                else:
                    if st.button("차단해제", key="ip_ublk"):
                        unblock_ip(cid, chosen)
                        st.cache_data.clear(); st.rerun()
            with ac3:
                if chosen not in excluded_set:
                    if st.button("노출제한", key="ip_nex"):
                        cnt = next((r["total_clicks"] for r in ip_rows if r["ip_address"] == chosen), 0)
                        add_naver_excluded_ip(cid, chosen, f"smart-{cnt}", cnt, cnt)
                        st.success(f"{chosen} 노출제한 추가")
                        st.cache_data.clear(); st.rerun()
            with ac4:
                if chosen in suspect_map:
                    if st.button("정상처리", key="ip_clr"):
                        clear_suspect(cid, chosen)
                        st.cache_data.clear(); st.rerun()

            # 클릭 상세 로그
            detail = get_clicks_for_ip(cid, chosen, start_s, end_s, limit=50)
            if detail:
                df_d = pd.DataFrame(detail)
                show = ["created_at", "keyword", "device", "os", "stay_seconds", "is_conversion"]
                show = [c for c in show if c in df_d.columns]
                df_d = df_d[show].rename(columns={
                    "created_at": "클릭시간", "keyword": "키워드",
                    "device": "기기", "os": "OS",
                    "stay_seconds": "체류(초)", "is_conversion": "전환",
                })
                st.dataframe(df_d, use_container_width=True, hide_index=True, height=220)

    # 탐지 실행 + 테스트 클릭 버튼
    run_c1, run_c2, run_c3 = st.columns([4, 1, 1])
    with run_c2:
        if st.button("탐지 실행", key="ip_detect"):
            with st.spinner("분석 중..."):
                run_detection(cid)
            st.cache_data.clear(); st.rerun()
    with run_c3:
        if st.button("테스트 클릭", key="ip_test_click", help="클릭 로그 DB에 테스트 데이터를 추가합니다"):
            import random as _rnd
            _ips = ["1.234.56.78", "210.90.141.33", "125.178.90.12"]
            _kws = ["검색광고리베이트", "네이버광고대행사", "구글광고대행사"]
            for _i in range(5):
                log_click({
                    "client_id": cid,
                    "ip_address": _rnd.choice(_ips),
                    "keyword": _rnd.choice(_kws),
                    "device": _rnd.choice(["desktop", "mobile"]),
                    "landing_url": "https://www.admarketip.com/",
                    "referrer": "https://search.naver.com/",
                    "session_id": f"test_{_i}",
                    "ad_type": "naver",
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })
            st.success("테스트 클릭 5개 추가됨 — 새로고침하면 반영됩니다")
            st.cache_data.clear(); st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — 스마트폰 추적
# ══════════════════════════════════════════════════════════════════════════════
with TAB_MOB:
    mob_s, mob_e, mob_min = filter_bar("mob")

    sessions = get_mobile_sessions(cid, mob_s, mob_e)
    sessions = [s for s in sessions if s["total_clicks"] >= mob_min]

    if not sessions:
        st.info("해당 기간 조건에 맞는 모바일 세션이 없습니다.")
    else:
        st.markdown(render_mobile_table(sessions), unsafe_allow_html=True)
        st.caption(f"총 {len(sessions)}개 세션")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — 네이버 노출제한 IP
# ══════════════════════════════════════════════════════════════════════════════
with TAB_NAVER:
    st.markdown('<div class="sl-page-title" style="font-size:17px;">네이버 광고노출제한 IP</div>',
                unsafe_allow_html=True)

    # 서브탭: 전체 | 자동 노출제한 내역
    nv_sub = st.radio("", ["전체", "자동 노출제한 내역"],
                      horizontal=True, key="nv_sub", label_visibility="collapsed")

    excluded_list = get_naver_excluded_ips(cid)
    active_list   = [r for r in excluded_list if r["status"] == "active"]
    auto_list     = [r for r in active_list if (r.get("memo") or "").startswith("smart-")]

    display_list  = auto_list if nv_sub == "자동 노출제한 내역" else active_list

    # API 연동 상태 배너
    api_key    = cfg.get("naver_api_key", "")
    api_secret = cfg.get("naver_api_secret", "")
    cust_id    = cfg.get("naver_customer_id", "")
    has_api    = bool(api_key and api_secret and cust_id)
    synced_cnt = sum(1 for r in active_list if r.get("naver_synced"))

    if has_api:
        st.markdown(
            f'<div class="sl-green-box">'
            f'<b>네이버 API와 동기화 중 ({len(active_list)}개의 IP)</b><br><br>'
            f'* 네이버 광고 시스템과 연동되어 있습니다. 이곳에 등록된 IP는 네이버 광고 열람이 불가능합니다.<br>'
            f'* 여기서 삭제하거나 수정하시면 실제 네이버 노출제한 IP 데이터가 변경 됩니다.<br>'
            f'* IP 옆에 [+] 버튼(아래 추가)을 눌러서 노출제한을 거실 수 있습니다. '
            f'추가한 IP는 메모에 <i>smart-[광고클릭횟수]</i>로 기록됩니다.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="sl-green-box" style="background:#fefce8;border-color:#fde68a;color:#92400e;">'
            f'<b>⚠️ Naver API 미연동 ({len(active_list)}개 로컬 등록)</b><br><br>'
            f'* [부정클릭 설정 → 기본 설정]에서 Naver API 키를 입력하면 자동 동기화됩니다.<br>'
            f'* 아래 TXT 다운로드 후 네이버 광고관리시스템 → 캠페인 설정 → IP 차단에 수동 등록하세요.</div>',
            unsafe_allow_html=True,
        )

    # 자동차단 후보
    candidates = check_auto_block_candidates(cid)
    if candidates:
        ab_days   = cfg.get("auto_block_days", 7)
        ab_clicks = cfg.get("auto_block_clicks", 5)
        with st.expander(f"⚠️ 자동차단 후보 {len(candidates)}개 — {ab_days}일 내 {ab_clicks}회 이상 클릭"):
            for c in candidates[:15]:
                cc1, cc2, cc3 = st.columns([4, 1, 1])
                with cc1:
                    _ccnt = c.get("total_clicks", c.get("cnt", 0))
                    st.markdown(f"`{c['ip_address']}`  **{_ccnt}회 클릭**")
                with cc2:
                    if st.button("노출제한 추가", key=f"cand_{c['ip_address']}", type="primary"):
                        cnt = c.get("total_clicks", c.get("cnt", 0))
                        add_naver_excluded_ip(cid, c["ip_address"], f"smart-{cnt}", cnt, cnt)
                        st.success(f"{c['ip_address']} 추가"); st.cache_data.clear(); st.rerun()
                with cc3:
                    if st.button("무시", key=f"ign_{c['ip_address']}"):
                        safe = list(cfg.get("safe_ips", []))
                        if c["ip_address"] not in safe:
                            safe.append(c["ip_address"])
                            save_client_settings(cid, {**cfg, "safe_ips": safe})
                            st.cache_data.clear()
                        st.rerun()

    # 테이블
    if not display_list:
        st.info("등록된 노출제한 IP가 없습니다.")
    else:
        st.markdown(render_naver_table(display_list), unsafe_allow_html=True)
        st.caption(f"총 {len(display_list)}개")

        # 삭제 / 다운로드 액션
        st.markdown("---")
        del_col, dl_col = st.columns([3, 2])
        with del_col:
            del_ip = st.selectbox("삭제할 IP 선택", [r["ip_address"] for r in display_list],
                                  key="nv_del_sel")
            if st.button("⊗ 삭제", key="nv_del_btn"):
                remove_naver_excluded_ip(cid, del_ip)
                st.success(f"{del_ip} 삭제 완료"); st.cache_data.clear(); st.rerun()
        with dl_col:
            ip_txt = "\n".join(r["ip_address"] for r in active_list)
            st.download_button("TXT 다운로드", ip_txt, "naver_excluded_ips.txt", "text/plain",
                               use_container_width=True)

    # IP 직접 추가
    st.markdown("---")
    with st.expander("IP 직접 추가"):
        na1, na2, na3 = st.columns([3, 3, 1])
        with na1:
            new_ip = st.text_input("IP 주소", placeholder="예: 1.2.3.4", key="nv_add_ip")
        with na2:
            new_memo = st.text_input("메모", placeholder="예: smart-3 또는 경쟁사", key="nv_add_memo")
        with na3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("추가", key="nv_add_btn", type="primary"):
                if new_ip.strip():
                    add_naver_excluded_ip(cid, new_ip.strip(), new_memo.strip())
                    st.success(f"{new_ip.strip()} 추가 완료"); st.cache_data.clear(); st.rerun()
                else:
                    st.error("IP를 입력하세요.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — 부정클릭 설정
# ══════════════════════════════════════════════════════════════════════════════
with TAB_CFG:
    st.markdown('<div class="sl-page-title" style="font-size:17px;">부정클릭 설정</div>',
                unsafe_allow_html=True)

    # 5개 서브탭
    S1, S2, S3, S4, S5 = st.tabs([
        "부정클릭 차단 설정",
        "알림 설정",
        "네이버 자동차단",
        "기본 설정",
        "추적 스크립트",
    ])

    # ── S1: 부정클릭 차단 설정 ────────────────────────────────────────────────
    with S1:
        st.markdown('<div class="sl-section-title">부정클릭 차단 설정</div>', unsafe_allow_html=True)

        with st.form("s1_form"):
            # 경고 팝업 기능 사용
            with _cfg_row("경고 팝업 기능 사용"):
                popup_use = st.radio("", ["사용", "사용하지 않음"],
                                     index=0 if cfg.get("popup_enabled", 0) else 1,
                                     horizontal=True, key="s1_popup", label_visibility="collapsed")
            st.markdown('<div class="cfg-divider"></div>', unsafe_allow_html=True)

            # 경고 팝업 인식 방법
            with _cfg_row("경고 팝업 인식 방법"):
                popup_mode = st.radio("", ["유효클릭일때만 팝업", "무효+유효클릭 모두 팝업"],
                                      index=0,
                                      horizontal=True, key="s1_popup_mode", label_visibility="collapsed")
            st.markdown('<div class="cfg-divider"></div>', unsafe_allow_html=True)

            # 스마트폰 위치 추적
            with _cfg_row("스마트폰 위치 추적 기능",
                          sub="N회 이상 클릭시 스마트폰 위치 추적"):
                track_enabled = st.radio("", ["사용", "사용하지 않음"],
                                         index=0 if cfg.get("mobile_track_enabled", 1) else 1,
                                         horizontal=True, key="s1_track", label_visibility="collapsed")
                if track_enabled == "사용":
                    track_n = st.number_input("CPC광고를 N회 이상 클릭시 위치 추적",
                                              1, 100, int(cfg.get("mobile_track_clicks", 5)),
                                              key="s1_track_n", label_visibility="visible")
            st.markdown('<div class="cfg-divider"></div>', unsafe_allow_html=True)

            # 스마트폰 전용 경고 팝업
            with _cfg_row("스마트폰 전용 경고 팝업",
                          sub="N회 이상 클릭시 휴대폰/통신사 정보 표시"):
                mobile_popup = st.radio("", ["사용", "사용하지 않음"],
                                        index=0 if cfg.get("mobile_popup_enabled", 1) else 1,
                                        horizontal=True, key="s1_mpopup", label_visibility="collapsed")
                if mobile_popup == "사용":
                    mobile_popup_n = st.number_input("CPC광고를 N회 이상 클릭시 팝업",
                                                     1, 100, int(cfg.get("mobile_popup_clicks", 4)),
                                                     key="s1_mpopup_n", label_visibility="visible")
            st.markdown('<div class="cfg-divider"></div>', unsafe_allow_html=True)

            # 탐지 기준
            st.markdown('<div class="sl-section-title" style="font-size:14px;margin-top:16px;">탐지 기준</div>',
                        unsafe_allow_html=True)
            dc1, dc2 = st.columns(2)
            with dc1:
                v_24h = st.number_input("24시간 내 최대 허용 클릭", 1, 100, int(cfg.get("max_clicks_24h", 5)))
                v_1h  = st.number_input("1시간 내 최대 허용 클릭",  1,  50, int(cfg.get("max_clicks_1h", 3)))
            with dc2:
                v_kw   = st.number_input("동일 키워드 최대 반복",  1, 50, int(cfg.get("max_keyword_repeats", 3)))
                v_stay = st.number_input("최소 체류시간(초)",       1, 120, int(cfg.get("min_stay_seconds", 10)))

            v_score = st.number_input("의심 분류 최소 점수", 10, 100, int(cfg.get("auto_suspect_score", 50)))
            v_cpc   = st.number_input("평균 CPC (원)", 100, 100000, int(cfg.get("avg_cpc", 500)), step=100)

            # 안전 IP
            st.markdown("**안전 IP (내부 직원 · 사무실)**")
            safe_raw = st.text_area("", value="\n".join(cfg.get("safe_ips", [])),
                                    height=70, label_visibility="collapsed",
                                    placeholder="192.168.1.1\n10.0.0.1")

            _, save_col = st.columns([5, 1])
            with save_col:
                s1_saved = st.form_submit_button("저장", type="primary", use_container_width=True)

        if s1_saved:
            save_client_settings(cid, {
                **cfg,
                "popup_enabled":        popup_use == "사용",
                "mobile_track_enabled": track_enabled == "사용",
                "mobile_track_clicks":  track_n if track_enabled == "사용" else 5,
                "mobile_popup_enabled": mobile_popup == "사용",
                "mobile_popup_clicks":  mobile_popup_n if mobile_popup == "사용" else 4,
                "max_clicks_24h":       v_24h,
                "max_clicks_1h":        v_1h,
                "max_keyword_repeats":  v_kw,
                "min_stay_seconds":     v_stay,
                "auto_suspect_score":   v_score,
                "avg_cpc":              v_cpc,
                "safe_ips":             [ip.strip() for ip in safe_raw.splitlines() if ip.strip()],
            })
            st.success("저장되었습니다.")
            st.cache_data.clear()

    # ── S2: 알림 설정 ─────────────────────────────────────────────────────────
    with S2:
        st.markdown('<div class="sl-section-title">알림톡 알림 설정</div>', unsafe_allow_html=True)
        st.markdown('<div class="sl-section-sub">알림톡 알림을 설정합니다.</div>', unsafe_allow_html=True)

        with st.form("s2_form"):
            # 알림톡 사용
            with _cfg_row("알림톡 사용"):
                alert_use = st.radio("", ["사용함", "사용하지 않음"],
                                     index=0 if cfg.get("alert_enabled", 0) else 1,
                                     horizontal=True, key="s2_alert_use", label_visibility="collapsed")
            st.markdown('<div class="cfg-divider"></div>', unsafe_allow_html=True)

            # 알림 횟수
            with _cfg_row("알림 횟수 설정"):
                c_l, c_r = st.columns([2, 3])
                with c_l:
                    alert_n = st.number_input("", 1, 100, int(cfg.get("alert_clicks", 3)),
                                              key="s2_alert_n", label_visibility="collapsed")
                with c_r:
                    st.markdown(
                        f'<div style="padding-top:8px;font-size:13px;color:#555;">'
                        f'회 이상 클릭시 알림을 받습니다. <span style="color:#aaa;">(최근 24시간 이내)</span></div>',
                        unsafe_allow_html=True)
            st.markdown('<div class="cfg-divider"></div>', unsafe_allow_html=True)

            # 알림 수신번호
            with _cfg_row("알림 수신번호"):
                alert_phone = st.text_input("", value=cfg.get("alert_phone", ""),
                                            placeholder="010-0000-0000",
                                            key="s2_phone", label_visibility="collapsed")

            _, sv2 = st.columns([5, 1])
            with sv2:
                s2_saved = st.form_submit_button("저장", type="primary", use_container_width=True)

        if s2_saved:
            save_client_settings(cid, {
                **cfg,
                "alert_enabled": alert_use == "사용함",
                "alert_clicks":  alert_n,
                "alert_phone":   alert_phone,
            })
            st.success("저장되었습니다.")
            st.cache_data.clear()

        # 테스트 발송
        st.markdown("---")
        t1, t2 = st.columns([3, 1])
        with t1:
            test_ip = st.text_input("테스트 IP", "1.2.3.4", key="s2_test_ip")
        with t2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("테스트 발송", key="s2_test_btn"):
                phone = cfg.get("alert_phone", "")
                if not phone:
                    st.error("수신번호를 먼저 저장하세요.")
                else:
                    from bizmoney_alert import send_sms_notification
                    res = send_sms_notification(
                        phone,
                        f"[마케팁] 부정클릭 알림 테스트\nIP: {test_ip}\n클릭수: 99회\n즉시 확인하세요.",
                    )
                    if res.get("status") == "success":
                        st.success("테스트 발송 완료")
                    else:
                        st.error(f"발송 실패: {res.get('error', res)}")

    # ── S3: 네이버 자동차단 ───────────────────────────────────────────────────
    with S3:
        st.markdown('<div class="sl-section-title">네이버 광고 API 자동 차단 사용</div>',
                    unsafe_allow_html=True)
        st.markdown(
            '<div class="sl-section-sub">'
            '이 기능은 네이버 광고 API를 이용하여, 설정된 (유효)클릭 횟수에 도달할 경우,<br>'
            '자동으로 네이버 광고 노출제한 IP에 등록하는 기능입니다.</div>',
            unsafe_allow_html=True)

        with st.form("s3_form"):
            # 자동차단 사용 여부
            with _cfg_row("네이버 광고 API 자동 차단 사용"):
                auto_use = st.radio("", ["사용함", "사용하지 않음"],
                                    index=0 if cfg.get("auto_block_naver", 0) else 1,
                                    horizontal=True, key="s3_auto_use", label_visibility="collapsed")
            st.markdown('<div class="cfg-divider"></div>', unsafe_allow_html=True)

            # LTE 자동차단
            with _cfg_row("LTE 자동 차단 허용"):
                lte_use = st.radio("", ["사용함", "사용하지 않음"],
                                   index=0 if cfg.get("lte_auto_block", 0) else 1,
                                   horizontal=True, key="s3_lte", label_visibility="collapsed")
            st.markdown('<div class="cfg-divider"></div>', unsafe_allow_html=True)

            # 차단 설정
            with _cfg_row("차단 설정"):
                cc1, cc2, cc3, cc4 = st.columns([2, 1, 2, 2])
                with cc1:
                    st.markdown('<div style="padding-top:8px;font-size:13px;">네이버 광고를 최근</div>',
                                unsafe_allow_html=True)
                with cc2:
                    ab_days = st.number_input("", 1, 30, int(cfg.get("auto_block_days", 1)),
                                              key="s3_days", label_visibility="collapsed")
                with cc3:
                    st.markdown('<div style="padding-top:8px;font-size:13px;">일 이내</div>',
                                unsafe_allow_html=True)
                ab2_c1, ab2_c2, ab2_c3 = st.columns([1, 2, 3])
                with ab2_c1:
                    ab_clicks = st.number_input("", 1, 100, int(cfg.get("auto_block_clicks", 5)),
                                                key="s3_clicks", label_visibility="collapsed")
                with ab2_c2:
                    st.markdown('<div style="padding-top:8px;font-size:13px;">회 이상 클릭시 노출제한 IP에 등록</div>',
                                unsafe_allow_html=True)

            _, sv3 = st.columns([5, 1])
            with sv3:
                s3_saved = st.form_submit_button("저장", type="primary", use_container_width=True)

        if s3_saved:
            save_client_settings(cid, {
                **cfg,
                "auto_block_naver":  auto_use == "사용함",
                "lte_auto_block":    lte_use == "사용함",
                "auto_block_days":   ab_days,
                "auto_block_clicks": ab_clicks,
            })
            st.success("저장되었습니다.")
            st.cache_data.clear()

    # ── S4: 기본 설정 ─────────────────────────────────────────────────────────
    with S4:
        # 서브탭: 네이버 광고 API | 담당자 정보
        b1, b2 = st.tabs(["네이버 광고 API", "담당자 정보"])

        with b1:
            st.markdown('<div class="sl-section-title">네이버 광고 API 설정</div>', unsafe_allow_html=True)

            # 연동 상태 배너
            if has_api:
                st.markdown(
                    '<div class="sl-green-box"><b>● 네이버 API와 동기화 중</b></div>',
                    unsafe_allow_html=True)
            else:
                st.markdown(
                    '<div class="sl-green-box" style="background:#fff7ed;border-color:#fed7aa;color:#c2410c;">'
                    '네이버 광고 API 연동 안내<br><br>'
                    '1. API를 연동하면 마케팁에서 원클릭으로 특정 IP의 광고노출을 제한할 수 있습니다.<br>'
                    '2. 연동 완료 후 [네이버 노출제한 IP] 탭에서 네이버와 연동된 노출제한 IP를 확인할 수 있습니다.'
                    '</div>',
                    unsafe_allow_html=True)

            with st.form("b1_form"):
                with _cfg_row("현재상태"):
                    if has_api:
                        st.markdown("🟢 **네이버 API와 동기화 중**")
                    else:
                        st.markdown("⚫ 미연동")
                st.markdown('<div class="cfg-divider"></div>', unsafe_allow_html=True)

                with _cfg_row("CUSTOMER_ID"):
                    nv_cust = st.text_input("", value=cfg.get("naver_customer_id", ""),
                                            key="b1_cust", label_visibility="collapsed")
                st.markdown('<div class="cfg-divider"></div>', unsafe_allow_html=True)

                with _cfg_row("엑세스라이선스"):
                    nv_key = st.text_input("", value=cfg.get("naver_api_key", ""),
                                           type="password", key="b1_key", label_visibility="collapsed")
                st.markdown('<div class="cfg-divider"></div>', unsafe_allow_html=True)

                with _cfg_row("비밀키"):
                    nv_secret = st.text_input("", value=cfg.get("naver_api_secret", ""),
                                              type="password", key="b1_secret", label_visibility="collapsed")

                del_col2, sv_col2 = st.columns([1, 1])
                with del_col2:
                    del_api = st.form_submit_button("삭제")
                with sv_col2:
                    sv_api  = st.form_submit_button("저장", type="primary")

            if del_api:
                save_client_settings(cid, {
                    **cfg,
                    "naver_customer_id": "",
                    "naver_api_key":     "",
                    "naver_api_secret":  "",
                })
                st.success("API 정보가 삭제되었습니다.")
                st.cache_data.clear(); st.rerun()

            if sv_api:
                save_client_settings(cid, {
                    **cfg,
                    "naver_customer_id": nv_cust,
                    "naver_api_key":     nv_key,
                    "naver_api_secret":  nv_secret,
                })
                st.success("저장되었습니다.")
                st.cache_data.clear()

        with b2:
            st.markdown('<div class="sl-section-title">담당자 정보</div>', unsafe_allow_html=True)
            st.markdown('<div class="sl-section-sub">부정클릭 알림 등이 해당 번호로 발송됩니다.</div>',
                        unsafe_allow_html=True)

            with st.form("b2_form"):
                with _cfg_row("담당자 이름 *"):
                    mgr_name = st.text_input("", value=cfg.get("manager_name", ""),
                                             key="b2_name", label_visibility="collapsed")
                st.markdown('<div class="cfg-divider"></div>', unsafe_allow_html=True)

                with _cfg_row("담당자 이메일 *"):
                    mgr_email = st.text_input("", value=cfg.get("manager_email", ""),
                                              key="b2_email", label_visibility="collapsed")
                st.markdown('<div class="cfg-divider"></div>', unsafe_allow_html=True)

                with _cfg_row("담당자 휴대폰번호 *"):
                    mgr_phone = st.text_input("", value=cfg.get("alert_phone", ""),
                                              placeholder="010-0000-0000",
                                              key="b2_phone", label_visibility="collapsed")
                    st.caption("*부정클릭 알림 사용 시 해당 번호로 발송됩니다.")

                _, sv_b2 = st.columns([5, 1])
                with sv_b2:
                    b2_saved = st.form_submit_button("저장", type="primary", use_container_width=True)

            if b2_saved:
                save_client_settings(cid, {
                    **cfg,
                    "manager_name":  mgr_name,
                    "manager_email": mgr_email,
                    "alert_phone":   mgr_phone,
                })
                st.success("저장되었습니다.")
                st.cache_data.clear()

    # ── S5: 추적 스크립트 ─────────────────────────────────────────────────────
    with S5:
        st.markdown('<div class="sl-section-title">클릭 추적 서버 설정</div>', unsafe_allow_html=True)

        # 서버 URL 설정
        with st.form("s5_server_form"):
            with _cfg_row("추적 서버 URL", sub="랜딩페이지에서 클릭 데이터를 전송할 서버 주소"):
                srv_url = st.text_input(
                    "", value=cfg.get("track_server_url", ""),
                    placeholder="예: https://your-server.onrender.com  또는  http://localhost:8502",
                    key="s5_srv_url", label_visibility="collapsed",
                )
            _, sv5 = st.columns([5, 1])
            with sv5:
                s5_saved = st.form_submit_button("저장", type="primary", use_container_width=True)

        if s5_saved:
            save_client_settings(cid, {**cfg, "track_server_url": srv_url.strip()})
            st.success("저장되었습니다.")
            st.cache_data.clear()
            cfg = get_client_settings(cid)

        srv = cfg.get("track_server_url", "").rstrip("/")

        # 서버 상태 확인
        st.markdown("---")
        col_s, col_b = st.columns([4, 1])
        with col_b:
            check_srv = st.button("서버 상태 확인", key="s5_check")
        with col_s:
            if check_srv and srv:
                try:
                    import requests as _req
                    r = _req.get(srv + "/health", timeout=3)
                    if r.ok:
                        st.success(f"✅ 서버 정상 응답 ({srv})")
                    else:
                        st.error(f"⚠️ 서버 오류 ({r.status_code})")
                except Exception as _e:
                    st.error(f"❌ 서버 연결 실패: {_e}")
            elif check_srv and not srv:
                st.warning("서버 URL을 먼저 입력·저장하세요.")

        # Supabase 상태
        if _use_sb():
            st.success("✅ Supabase 연결됨 — 클릭 데이터가 Supabase에 저장됩니다.")
        else:
            st.warning("⚠️ Supabase 미연결 — 클릭 데이터가 로컬 SQLite에 저장됩니다.")

        # 추적 스크립트 임베드 코드
        st.markdown("---")
        st.markdown("### 랜딩페이지 삽입 코드")

        if not srv:
            st.info("추적 서버 URL을 설정하면 삽입 코드가 표시됩니다.")
        else:
            embed_code = f'<script src="{srv}/track.js?client_id={cid}"></script>'
            st.markdown(
                '<div class="sl-green-box">'
                '<b>✅ 아래 스크립트를 랜딩페이지의 &lt;/body&gt; 직전에 삽입하세요</b><br>'
                '광고 클릭으로 방문한 사용자의 IP, 기기, 키워드, 체류시간을 자동 수집합니다.'
                '</div>',
                unsafe_allow_html=True,
            )
            st.code(embed_code, language="html")

            st.markdown("**전환 발생 시 추가 코드 (주문/문의 완료 페이지):**")
            st.code("window.mktipConversion({type: 'inquiry'});  // 또는 'order', 'signup'",
                    language="javascript")

        # 서버 실행 안내
        st.markdown("---")
        st.markdown("### 추적 서버 실행 방법")

        tab_local, tab_cloud = st.tabs(["로컬 실행 (테스트용)", "클라우드 배포 (운영용)"])

        with tab_local:
            st.markdown("**1단계 — 터미널에서 서버 시작:**")
            st.code("python -m uvicorn fraud.server:app --host 0.0.0.0 --port 8502", language="bash")
            st.markdown("**2단계 — ngrok으로 외부 접근 가능하게 (선택):**")
            st.code("ngrok http 8502", language="bash")
            st.caption("ngrok 설치: https://ngrok.com/download — 무료 계정으로 공개 URL 생성")
            st.markdown("**3단계 — 서버 URL 설정:**")
            st.markdown("- 로컬만 테스트: `http://localhost:8502`")
            st.markdown("- ngrok 사용 시: ngrok이 출력한 `https://xxxx.ngrok.io` URL")

        with tab_cloud:
            st.markdown(
                "**Render 무료 배포 (권장):**\n\n"
                "1. [render.com](https://render.com) 무료 계정 생성\n"
                "2. New → Web Service → GitHub 저장소 연결\n"
                "3. Build Command: `pip install -r requirements.txt`\n"
                "4. Start Command: `uvicorn fraud.server:app --host 0.0.0.0 --port $PORT`\n"
                "5. 환경변수 추가: `SUPABASE_URL`, `SUPABASE_KEY`\n"
                "6. 생성된 URL을 위 '추적 서버 URL'에 입력"
            )
            st.markdown(
                '<div class="sl-green-box" style="margin-top:12px;">'
                '<b>💡 Supabase 연결 시 클릭 데이터 자동 공유</b><br>'
                '서버(Render)와 Streamlit(Cloud) 모두 동일한 Supabase에 연결하면 '
                '데이터가 실시간 동기화됩니다.'
                '</div>',
                unsafe_allow_html=True,
            )
