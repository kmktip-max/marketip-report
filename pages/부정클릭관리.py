"""부정클릭 관리 — 관리자 전용"""
import io
import json
import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fraud.db import (
    init_db,
    get_all_clicks,
    get_suspicious_ips,
    get_blocked_ips,
    get_dashboard_stats,
    get_client_settings,
    save_client_settings,
    block_ip,
    unblock_ip,
    clear_suspect,
    get_report_data,
    log_click,
)
from fraud.detector import run_detection

# ── 관리자 전용 ───────────────────────────────────────────────────────────────
if st.session_state.get("auth_type") != "admin":
    st.error("🔒 관리자만 접근 가능합니다.")
    st.stop()

# ── DB 초기화 ─────────────────────────────────────────────────────────────────
init_db()

# ── 광고주 목록 로드 ──────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def _load_clients() -> list[dict]:
    try:
        from report_engine.storage import load_clients
        return load_clients() or []
    except Exception:
        pass
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(root, "clients.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


clients = _load_clients()
client_names = [c.get("name", c.get("id", "")) for c in clients]
client_ids   = [c.get("id", "") for c in clients]

# ── 헤더 ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.fd-kpi {
    background:#fff;border:1px solid #E5E7EB;border-radius:12px;
    padding:20px 22px;text-align:center;
}
.fd-kpi-label {font-size:12px;font-weight:700;color:#6B7280;margin-bottom:6px;}
.fd-kpi-val   {font-size:28px;font-weight:800;color:#111827;line-height:1.1;}
.fd-kpi-sub   {font-size:12px;color:#9CA3AF;margin-top:4px;}

.fd-risk-high   {background:#FEE2E2;color:#991B1B;padding:2px 10px;border-radius:100px;font-size:11px;font-weight:700;}
.fd-risk-med    {background:#FEF3C7;color:#92400E;padding:2px 10px;border-radius:100px;font-size:11px;font-weight:700;}
.fd-risk-low    {background:#D1FAE5;color:#065F46;padding:2px 10px;border-radius:100px;font-size:11px;font-weight:700;}

.fd-section {font-size:15px;font-weight:700;color:#111827;border-left:3px solid #0D47A1;padding-left:10px;margin:20px 0 10px;}
</style>
""", unsafe_allow_html=True)

st.markdown("## 🛡️ 부정클릭 관리")
st.caption("광고 유입 로그 수집 · 의심 IP 탐지 · 차단 관리")

# ── 광고주 선택 ───────────────────────────────────────────────────────────────
col_sel, col_run, col_spacer = st.columns([2, 1.2, 4])

with col_sel:
    if not clients:
        st.warning("등록된 광고주가 없습니다.")
        st.stop()
    sel_idx = st.selectbox(
        "광고주 선택",
        range(len(clients)),
        format_func=lambda i: client_names[i],
        key="fd_client_idx",
        label_visibility="collapsed",
    )
    client = clients[sel_idx]
    cid    = client_ids[sel_idx]

with col_run:
    if st.button("🔍 탐지 실행", type="primary", use_container_width=True):
        with st.spinner("분석 중..."):
            n = run_detection(cid)
        st.success(f"완료 — {n}건 갱신")
        st.rerun()

# ── 탭 ───────────────────────────────────────────────────────────────────────
TAB_DASH, TAB_LOG, TAB_SUS, TAB_BLK, TAB_SET, TAB_SCR = st.tabs([
    "📊 대시보드",
    "📋 클릭 로그",
    "⚠️ 의심 IP",
    "🚫 차단 IP",
    "⚙️ 광고주 설정",
    "🔗 추적 스크립트",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — 대시보드
# ══════════════════════════════════════════════════════════════════════════════
with TAB_DASH:
    stats = get_dashboard_stats(cid)

    c1, c2, c3, c4, c5 = st.columns(5)
    kpi_data = [
        (c1, "오늘 총 유입",     stats["today_total"],          ""),
        (c2, "오늘 의심 클릭",   stats["today_suspect_clicks"], ""),
        (c3, "의심 IP 수",       stats["suspect_count"],        "탐지된 IP"),
        (c4, "차단 IP 수",       stats["blocked_count"],        ""),
        (c5, "의심 클릭 비율",   f"{stats['suspect_ratio']}%",  ""),
    ]
    for col, label, val, sub in kpi_data:
        with col:
            st.markdown(
                f'<div class="fd-kpi">'
                f'<div class="fd-kpi-label">{label}</div>'
                f'<div class="fd-kpi-val">{val}</div>'
                f'<div class="fd-kpi-sub">{sub}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("")

    left, right = st.columns(2)

    with left:
        st.markdown('<div class="fd-section">상위 반복 IP TOP 10 (24h)</div>', unsafe_allow_html=True)
        if stats["top_ips"]:
            df_ip = pd.DataFrame(stats["top_ips"]).rename(columns={"ip_address": "IP", "cnt": "클릭수"})
            st.dataframe(df_ip, use_container_width=True, hide_index=True)
        else:
            st.info("데이터 없음")

    with right:
        st.markdown('<div class="fd-section">의심 키워드 TOP 10 (24h)</div>', unsafe_allow_html=True)
        if stats["top_keywords"]:
            df_kw = pd.DataFrame(stats["top_keywords"]).rename(columns={"keyword": "키워드", "cnt": "유입수"})
            st.dataframe(df_kw, use_container_width=True, hide_index=True)
        else:
            st.info("데이터 없음")

    # 리포트 기간 선택
    st.markdown('<div class="fd-section">기간별 리포트</div>', unsafe_allow_html=True)
    settings = get_client_settings(cid)
    avg_cpc  = settings.get("avg_cpc", 500)

    r1, r2, r3 = st.columns([1.2, 1.2, 3])
    with r1:
        rpt_start = st.date_input("시작일", datetime.now() - timedelta(days=30), key="rpt_s")
    with r2:
        rpt_end   = st.date_input("종료일", datetime.now(), key="rpt_e")

    rdata = get_report_data(cid, str(rpt_start), str(rpt_end))

    m1, m2, m3, m4, m5 = st.columns(5)
    save_est = rdata["suspect_clicks"] * avg_cpc
    for col, label, val in [
        (m1, "총 유입",        rdata["total"]),
        (m2, "의심 유입",      rdata["suspect_clicks"]),
        (m3, "의심 IP 수",     rdata["suspect_ip_count"]),
        (m4, "차단 IP 수",     rdata["blocked_count"]),
        (m5, "추정 절감 광고비", f"~{save_est:,}원"),
    ]:
        col.metric(label, val)

    st.caption(f"추정 절감 = 의심클릭 × 평균CPC {avg_cpc:,}원 (추정값)")

    r_left, r_right = st.columns(2)
    with r_left:
        if rdata["top_keywords"]:
            st.markdown("**의심 키워드 TOP10**")
            st.dataframe(
                pd.DataFrame(rdata["top_keywords"]).rename(columns={"keyword":"키워드","cnt":"의심유입수"}),
                use_container_width=True, hide_index=True,
            )
    with r_right:
        if rdata["top_ips"]:
            st.markdown("**반복 IP TOP10**")
            st.dataframe(
                pd.DataFrame(rdata["top_ips"]).rename(columns={"ip_address":"IP","cnt":"클릭수"}),
                use_container_width=True, hide_index=True,
            )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — 클릭 로그
# ══════════════════════════════════════════════════════════════════════════════
with TAB_LOG:
    st.markdown('<div class="fd-section">클릭 로그</div>', unsafe_allow_html=True)

    fl1, fl2, fl3 = st.columns([1.2, 1.2, 2])
    with fl1:
        log_start = st.date_input("시작일", datetime.now() - timedelta(days=7), key="log_s")
    with fl2:
        log_end   = st.date_input("종료일", datetime.now(), key="log_e")
    with fl3:
        kw_filter = st.text_input("IP / 키워드 검색", placeholder="예: 1.2.3.4 또는 브랜드명", key="log_kw")

    logs = get_all_clicks(cid, start_date=str(log_start), end_date=str(log_end), limit=1000)

    if kw_filter.strip():
        kw = kw_filter.strip().lower()
        logs = [l for l in logs if kw in (l.get("ip_address","")).lower()
                                 or kw in (l.get("keyword","")).lower()]

    if logs:
        df_log = pd.DataFrame(logs)
        show_cols = ["created_at", "ip_address", "keyword", "device", "browser",
                     "os", "source", "medium", "landing_url", "stay_seconds", "is_conversion"]
        show_cols = [c for c in show_cols if c in df_log.columns]
        col_rename = {
            "created_at": "시간", "ip_address": "IP", "keyword": "키워드",
            "device": "기기", "browser": "브라우저", "os": "OS",
            "source": "소스", "medium": "매체", "landing_url": "랜딩URL",
            "stay_seconds": "체류(초)", "is_conversion": "전환",
        }
        df_show = df_log[show_cols].rename(columns=col_rename)
        st.dataframe(df_show, use_container_width=True, hide_index=True, height=420)
        st.caption(f"총 {len(logs):,}건")

        csv_buf = io.StringIO()
        df_show.to_csv(csv_buf, index=False, encoding="utf-8-sig")
        st.download_button("CSV 다운로드", csv_buf.getvalue(), "click_logs.csv", "text/csv")
    else:
        st.info("해당 기간 클릭 로그가 없습니다.")

    # 테스트 클릭 삽입
    with st.expander("테스트 클릭 삽입 (개발/검증용)", expanded=False):
        st.caption("실제 스크립트 없이 샘플 데이터를 넣어 탐지 로직을 테스트합니다.")
        t1, t2, t3 = st.columns(3)
        with t1:
            t_ip  = st.text_input("IP", "1.2.3.4", key="t_ip")
            t_kw  = st.text_input("키워드", "브랜드명", key="t_kw")
        with t2:
            t_cnt = st.number_input("삽입 횟수", 1, 20, 6, key="t_cnt")
            t_stay= st.number_input("체류시간(초)", 0, 300, 5, key="t_stay")
        with t3:
            t_conv= st.checkbox("전환 있음", False, key="t_conv")
            t_ua  = st.text_input("User-Agent", "Mozilla/5.0 (Windows NT 10.0)", key="t_ua")

        if st.button("삽입", key="t_btn"):
            for _ in range(int(t_cnt)):
                log_click({
                    "client_id": cid,
                    "ip_address": t_ip,
                    "user_agent": t_ua,
                    "keyword": t_kw,
                    "device": "desktop", "browser": "Chrome", "os": "Windows",
                    "is_conversion": 1 if t_conv else 0,
                    "stay_seconds": int(t_stay),
                    "source": "naver", "medium": "cpc",
                })
            st.success(f"{t_cnt}건 삽입 완료. 상단 [탐지 실행] 버튼으로 분석하세요.")
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — 의심 IP
# ══════════════════════════════════════════════════════════════════════════════
with TAB_SUS:
    st.markdown('<div class="fd-section">의심 IP 목록</div>', unsafe_allow_html=True)
    st.caption("위험 점수 기준: 80점 이상 강한 의심(빨강) / 50점 이상 의심(주황)")

    suspects = get_suspicious_ips(cid)

    if not suspects:
        st.info("탐지된 의심 IP가 없습니다. 상단 [탐지 실행] 버튼으로 분석하세요.")
    else:
        for sus in suspects:
            ip    = sus["ip_address"]
            score = sus["risk_score"]
            status= sus["status"]

            if status == "strong_suspect":
                badge = '<span class="fd-risk-high">강한 의심</span>'
                border_color = "#FCA5A5"
            else:
                badge = '<span class="fd-risk-med">의심</span>'
                border_color = "#FCD34D"

            with st.container():
                st.markdown(
                    f'<div style="background:#fff;border:1px solid {border_color};border-radius:10px;'
                    f'padding:14px 18px;margin-bottom:10px;">',
                    unsafe_allow_html=True,
                )

                row1, row2 = st.columns([5, 1])
                with row1:
                    st.markdown(
                        f'<b style="font-size:16px;">{ip}</b> &nbsp; {badge} &nbsp;'
                        f'<span style="font-size:13px;color:#6B7280;">위험점수: '
                        f'<b style="color:#DC2626;">{score}점</b></span>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f'<div style="font-size:12px;color:#6B7280;margin-top:4px;">'
                        f'클릭수: <b>{sus["click_count"]}</b> | '
                        f'키워드수: <b>{sus["keyword_count"]}</b> | '
                        f'첫 유입: {sus["first_seen"][:16] if sus["first_seen"] else "-"} | '
                        f'마지막: {sus["last_seen"][:16] if sus["last_seen"] else "-"}</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f'<div style="font-size:12px;color:#92400E;margin-top:4px;">'
                        f'사유: {sus["reason"]}</div>',
                        unsafe_allow_html=True,
                    )

                with row2:
                    st.markdown("")
                    if st.button("🚫 차단", key=f"blk_{ip}", type="primary"):
                        st.session_state[f"confirm_blk_{ip}"] = True

                if st.session_state.get(f"confirm_blk_{ip}"):
                    blk_col1, blk_col2, blk_col3 = st.columns([3, 1, 1])
                    with blk_col1:
                        memo = st.text_input("차단 메모 (선택)", key=f"memo_{ip}", placeholder="예: 경쟁사 추정")
                    with blk_col2:
                        st.markdown("")
                        if st.button("✅ 확인 차단", key=f"do_blk_{ip}", type="primary"):
                            block_ip(cid, ip, sus["reason"],
                                     st.session_state.get("auth_username", "admin"),
                                     st.session_state.get(f"memo_{ip}", ""))
                            st.session_state.pop(f"confirm_blk_{ip}", None)
                            st.success(f"{ip} 차단 완료")
                            st.rerun()
                    with blk_col3:
                        st.markdown("")
                        if st.button("취소", key=f"cancel_blk_{ip}"):
                            st.session_state.pop(f"confirm_blk_{ip}", None)
                            st.rerun()

                clr_col, _ = st.columns([2, 5])
                with clr_col:
                    if st.button("✔️ 정상 처리", key=f"clr_{ip}"):
                        clear_suspect(cid, ip)
                        st.success(f"{ip} 정상 처리됨")
                        st.rerun()

                st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")
    if st.button("🔄 탐지 재실행", key="rerun_det"):
        n = run_detection(cid)
        st.success(f"{n}건 갱신")
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — 차단 IP
# ══════════════════════════════════════════════════════════════════════════════
with TAB_BLK:
    st.markdown('<div class="fd-section">차단 IP 목록</div>', unsafe_allow_html=True)

    blocked = get_blocked_ips(cid)

    if not blocked:
        st.info("차단된 IP가 없습니다.")
    else:
        df_blk = pd.DataFrame(blocked)[["ip_address","reason","blocked_by","created_at"]]
        df_blk.columns = ["IP", "차단 사유", "처리자", "차단 일시"]
        st.dataframe(df_blk, use_container_width=True, hide_index=True)

        # 다운로드
        d1, d2, d3 = st.columns([1, 1, 3])
        ip_list = "\n".join(r["ip_address"] for r in blocked)
        with d1:
            st.download_button(
                "TXT 다운로드",
                ip_list,
                file_name=f"blocked_ips_{cid}.txt",
                mime="text/plain",
            )
        with d2:
            csv_buf = io.StringIO()
            df_blk.to_csv(csv_buf, index=False, encoding="utf-8-sig")
            st.download_button(
                "CSV 다운로드",
                csv_buf.getvalue(),
                file_name=f"blocked_ips_{cid}.csv",
                mime="text/csv",
            )

        st.info(
            "💡 **네이버 광고**: 광고관리시스템 → 캠페인 설정 → IP 차단 → 다운로드한 IP 등록\n\n"
            "💡 **구글 Ads**: 도구 → IP 제외 → IP 목록 붙여넣기"
        )

        # 차단 해제
        with st.expander("차단 해제", expanded=False):
            unblk_ip = st.selectbox("해제할 IP", [r["ip_address"] for r in blocked], key="unblk_sel")
            if st.button("차단 해제", key="do_unblk"):
                unblock_ip(cid, unblk_ip)
                st.success(f"{unblk_ip} 차단 해제됨")
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — 광고주 설정
# ══════════════════════════════════════════════════════════════════════════════
with TAB_SET:
    st.markdown('<div class="fd-section">탐지 기준 설정</div>', unsafe_allow_html=True)
    st.caption(f"광고주: **{client.get('name', cid)}**")

    cfg = get_client_settings(cid)

    with st.form("fraud_settings_form"):
        s1, s2 = st.columns(2)
        with s1:
            st.markdown("**반복 클릭 기준**")
            v_24h = st.number_input(
                "24시간 내 최대 허용 클릭 수",
                1, 100, int(cfg.get("max_clicks_24h", 5)),
                help="이 횟수 이상이면 +30점",
            )
            v_1h  = st.number_input(
                "1시간 내 최대 허용 클릭 수",
                1, 50, int(cfg.get("max_clicks_1h", 3)),
                help="이 횟수 이상이면 +30점",
            )
            v_kw  = st.number_input(
                "동일 키워드 최대 반복 수",
                1, 50, int(cfg.get("max_keyword_repeats", 3)),
                help="이 횟수 이상이면 +20점",
            )

        with s2:
            st.markdown("**체류시간 / 점수 기준**")
            v_stay = st.number_input(
                "최소 체류시간(초) — 이 이하는 의심",
                1, 120, int(cfg.get("min_stay_seconds", 10)),
                help="이 초 이하면 +20점",
            )
            v_score = st.number_input(
                "의심 처리 최소 점수",
                10, 100, int(cfg.get("auto_suspect_score", 50)),
                help="이 점수 이상이면 의심 IP로 분류",
            )
            v_cpc = st.number_input(
                "평균 CPC (원) — 절감액 추정용",
                100, 100000, int(cfg.get("avg_cpc", 500)),
                step=100,
            )

        st.markdown("**안전 IP 목록** (내부 직원 · 사무실 IP)")
        safe_raw = st.text_area(
            "한 줄에 IP 하나씩 입력",
            value="\n".join(cfg.get("safe_ips", [])),
            height=100,
            placeholder="예:\n192.168.1.1\n10.0.0.5",
            label_visibility="collapsed",
        )

        st.markdown("**점수별 기준 안내**")
        st.markdown("""
| 조건 | 점수 |
|------|------|
| 24시간 내 설정 횟수 이상 | +30 |
| 1시간 내 설정 횟수 이상 | +30 |
| 동일 키워드 반복 | +20 |
| 평균 체류시간 기준 이하 | +20 |
| 전환 없이 3회 이상 반복 | +10 |
| 봇 패턴 UA 감지 | +10 |
| 전환 있음 (오탐 방지 감점) | -20 |
| 체류시간 60초 초과 (감점) | -10 |
""")

        submitted = st.form_submit_button("설정 저장", type="primary")

    if submitted:
        safe_ips = [ip.strip() for ip in safe_raw.splitlines() if ip.strip()]
        save_client_settings(cid, {
            "max_clicks_24h":      v_24h,
            "max_clicks_1h":       v_1h,
            "max_keyword_repeats": v_kw,
            "min_stay_seconds":    v_stay,
            "auto_suspect_score":  v_score,
            "avg_cpc":             v_cpc,
            "safe_ips":            safe_ips,
        })
        st.success("설정이 저장되었습니다.")
        st.cache_data.clear()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — 추적 스크립트 발급
# ══════════════════════════════════════════════════════════════════════════════
with TAB_SCR:
    st.markdown('<div class="fd-section">추적 스크립트 발급</div>', unsafe_allow_html=True)

    sc1, sc2 = st.columns([2, 1])
    with sc1:
        server_url = st.text_input(
            "추적 서버 URL",
            value="http://your-server:8502",
            placeholder="예: http://211.x.x.x:8502 또는 https://track.example.com",
            help="FastAPI 추적 서버 주소 (fraud/server.py 실행 필요)",
        )
    with sc2:
        sel_client_idx = st.selectbox(
            "스크립트 발급 광고주",
            range(len(clients)),
            format_func=lambda i: client_names[i],
            key="scr_client_idx",
        )

    target_cid = client_ids[sel_client_idx]
    script_tag = (
        f'<script src="{server_url.rstrip("/")}/track.js'
        f'?client_id={target_cid}"></script>'
    )

    # ── 발급 코드 ──────────────────────────────────────────────────────────────
    st.markdown("#### 📋 발급된 스크립트 코드")
    st.code(script_tag, language="html")

    st.markdown("---")

    # ── 삽입 위치 안내 ──────────────────────────────────────────────────────────
    st.markdown("### 📌 어디에 넣어야 하나요?")
    st.info(
        "광고를 클릭했을 때 사람들이 **처음 도달하는 페이지(랜딩페이지)** 의 HTML 코드 안, "
        "**`</head>` 태그 바로 위**에 붙여넣기 하면 됩니다."
    )

    st.markdown("#### ✅ 올바른 삽입 위치 예시")
    st.code(
        f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>광고 랜딩페이지</title>

  <!-- ▼▼▼ 여기에 붙여넣기 ▼▼▼ -->
  {script_tag}
  <!-- ▲▲▲ 여기까지 ▲▲▲ -->

</head>
<body>
  ... 페이지 내용 ...
</body>
</html>""",
        language="html",
    )

    st.markdown("---")
    st.markdown("### 🏗️ 홈페이지 종류별 삽입 방법")

    tab_cafe24, tab_wordpress, tab_html, tab_naver = st.tabs([
        "카페24 / 메이크샵", "워드프레스", "직접 제작 HTML", "네이버 스마트스토어"
    ])

    with tab_cafe24:
        st.markdown("""
**카페24 관리자 → 디자인 → HTML/CSS 편집**

1. 카페24 관리자 페이지 로그인
2. 상단 메뉴 **디자인** 클릭
3. **디자인 편집** → HTML 편집 버튼
4. `index.html` (또는 메인 레이아웃 파일) 열기
5. `</head>` 를 찾아서 **그 바로 위**에 코드 붙여넣기
6. 저장
""")

    with tab_wordpress:
        st.markdown("""
**워드프레스 → 외모 → 테마 편집기** 또는 **헤더/푸터 플러그인**

**방법 1 — 테마 편집기**
1. 워드프레스 관리자 → **외모** → **테마 편집기**
2. 오른쪽에서 `header.php` 선택
3. `</head>` 바로 위에 코드 붙여넣기
4. **파일 업데이트** 클릭

**방법 2 — 플러그인 (권장)**
1. 플러그인 → **Insert Headers and Footers** 설치
2. 설정 → **Scripts in Header** 칸에 코드 붙여넣기
3. 저장
""")

    with tab_html:
        st.markdown("""
**직접 제작 또는 HTML 파일 수정**

1. 랜딩페이지 `.html` 파일을 텍스트 편집기(메모장, VS Code 등)로 열기
2. `Ctrl+F`로 `</head>` 검색
3. `</head>` 바로 위 줄에 코드 붙여넣기
4. 저장 후 서버에 재업로드 (FTP 등)
""")

    with tab_naver:
        st.markdown("""
**네이버 스마트스토어는 외부 스크립트 삽입이 제한**됩니다.

- 스마트스토어 자체 페이지에는 이 스크립트를 직접 삽입할 수 없습니다.
- 대신 **별도 랜딩페이지**(자체 도메인)를 제작하고, 그 페이지에서 스마트스토어로 연결하는 방식을 사용하세요.
- 광고 도착 URL을 자체 랜딩페이지로 설정 → 추적 후 스마트스토어로 리다이렉트 가능합니다.
""")

    st.markdown("---")

    # ── 전환 이벤트 (선택) ─────────────────────────────────────────────────────
    with st.expander("📞 전환 이벤트 설정 (전화 상담·문의 완료 등)"):
        st.markdown("""
전환이 발생했을 때 아래 코드를 호출하면, 해당 방문자의 위험도 점수가 낮아집니다.
(부정클릭이 아닌 진짜 고객으로 분류)

**예시 — 전화 버튼 클릭 시:**
""")
        st.code(
            """<button onclick="window.mktipConversion({type: 'call'})">
  📞 전화 상담
</button>""",
            language="html",
        )
        st.markdown("**예시 — 문의 폼 제출 완료 시:**")
        st.code(
            """// 폼 submit 성공 후 실행
window.mktipConversion({type: 'inquiry'});""",
            language="javascript",
        )

    st.info(
        "⚠️ **개인정보 처리방침**: 이 스크립트는 방문자 IP를 수집합니다. "
        "사이트 개인정보 처리방침에 **'광고 부정클릭 방지 목적으로 IP 주소를 수집함'** 을 명시하세요."
    )

    with st.expander("API 엔드포인트 참고"):
        st.code(f"""
# 스크립트 파일
GET  {server_url}/track.js?client_id=CLIENT_ID

# 클릭 수집
POST {server_url}/track
     Body: {{client_id, session_id, landing_url, referrer, keyword, ...}}

# 체류시간 전송
POST {server_url}/track/stay
     Body: {{log_id, stay_seconds}}

# 전환 기록
POST {server_url}/track/convert
     Body: {{log_id}}

# IP 차단 확인
GET  {server_url}/check/{{ip}}?client_id=CLIENT_ID

# 헬스체크
GET  {server_url}/health
""", language="text")

# ── 이용안내 ─────────────────────────────────────────────────────────────────
st.divider()
with st.expander("📖 이용안내 — 처음 사용하시는 분께", expanded=False):
    st.markdown("""
**순서대로 따라하면 바로 시작할 수 있어요!**

**① 트래킹 스크립트 설치**
**[트래킹 스크립트]** 탭에서 클라이언트 선택 → 스크립트 코드 복사
→ 광고 랜딩페이지 HTML 소스의 `</head>` 바로 위에 붙여넣기

**② 설치 확인**
스크립트 설치 후 직접 광고를 클릭해 랜딩페이지에 방문 → 잠시 후 **[클릭 현황]** 탭에서 데이터 수신 확인

**③ 클릭 데이터 모니터링**
**[클릭 현황]** 탭에서 방문자별 IP·방문 횟수·체류시간·키워드 확인
→ 체류시간이 극히 짧거나(0~3초) 같은 IP가 반복 방문하면 의심 클릭 가능성

**④ 의심 IP 확인 및 차단**
**[의심 IP]** 탭에서 비정상 패턴 IP 목록 확인 → **[차단]** 버튼 클릭

**⑤ 네이버 광고에 차단 IP 등록**
차단된 IP를 **네이버 검색광고 시스템 → 캠페인 설정 → IP 차단**에도 등록하면 이중 차단 효과

> ⚠️ **개인정보 주의** : IP를 수집하므로 사이트 개인정보 처리방침에 수집 목적을 반드시 명시하세요.
    """)
