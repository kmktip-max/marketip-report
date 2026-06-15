import streamlit as st
import streamlit.components.v1 as components
import json
import os
import re
import sys
import traceback
from datetime import datetime, date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from report_engine.naver_api import NaverAdAPI
from report_engine.emailer import send_report
from report_engine.report_html import generate_html
from report_engine.report_html_v2 import build_monthly_report_v2, fetch_v2_extra
from report_engine.report_data_adapters import normalize_naver_data
from report_engine.storage import load_clients, save_clients


# ── 유틸 ──────────────────────────────────────────────────────────────
def _fmt_phone(raw: str) -> str:
    """숫자만 추출 후 한국 휴대폰 번호 형식(010-XXXX-XXXX)으로 변환."""
    d = re.sub(r"\D", "", (raw or "").strip())
    if len(d) == 11:
        return f"{d[:3]}-{d[3:7]}-{d[7:]}"
    if len(d) == 10:
        return f"{d[:3]}-{d[3:6]}-{d[6:]}"
    return raw.strip()


def get_secret(key, default=""):
    try:
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key, default)


def load_history():
    path = os.path.join(ROOT, "report_history.json")
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def save_history(history):
    path = os.path.join(ROOT, "report_history.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ── 일괄 발송 헬퍼 ────────────────────────────────────────────────────
def _client_sendable(c):
    """필수 필드 검증. (can_send: bool, missing: list[str]) 반환."""
    missing = []
    if not str(c.get("name", "")).strip():         missing.append("광고주명")
    if not str(c.get("customer_id", "")).strip():  missing.append("Customer ID")
    if not str(c.get("api_key", "")).strip():      missing.append("API Key")
    if not str(c.get("secret_key", "")).strip():   missing.append("Secret Key")
    if not str(c.get("email", "")).strip():        missing.append("수신 이메일")
    return len(missing) == 0, missing


def _get_period_range(period_key):
    """(since, until) 문자열 반환."""
    today = date.today()
    if period_key == "weekly":
        until = today - timedelta(days=1)
        since = until - timedelta(days=6)
    else:
        first = today.replace(day=1)
        until = first - timedelta(days=1)
        since = until.replace(day=1)
    return since.strftime("%Y-%m-%d"), until.strftime("%Y-%m-%d")


# ── 예약발송 스케줄 관리 ──────────────────────────────────────────────
SCHEDULE_PATH = os.path.join(ROOT, "data", "report_schedule.json")
_SB_KEY = "report_schedule"


@st.cache_resource
def _get_sb():
    try:
        url = (getattr(st, "secrets", {}).get("SUPABASE_URL", "")
               or os.getenv("SUPABASE_URL", ""))
        key = (getattr(st, "secrets", {}).get("SUPABASE_KEY", "")
               or os.getenv("SUPABASE_KEY", ""))
        if not url or not key:
            return None
        from supabase import create_client
        return create_client(url, key)
    except Exception:
        return None


def load_schedule():
    # Supabase 우선 (Cloud 환경에서도 영구 저장)
    try:
        sb = _get_sb()
        if sb:
            res = sb.table("app_data").select("data").eq("key", _SB_KEY).execute()
            if res.data:
                return res.data[0]["data"]
    except Exception:
        pass
    # 로컬 파일 폴백
    try:
        if os.path.exists(SCHEDULE_PATH):
            with open(SCHEDULE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"scheduled": [], "auto_monthly": {}}


def save_schedule(data):
    # Supabase 저장
    try:
        sb = _get_sb()
        if sb:
            sb.table("app_data").upsert(
                {"key": _SB_KEY, "data": data,
                 "updated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")},
                on_conflict="key",
            ).execute()
    except Exception:
        pass
    # 로컬 파일도 동기화
    os.makedirs(os.path.dirname(SCHEDULE_PATH), exist_ok=True)
    try:
        with open(SCHEDULE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _already_sent(history, client_name, period_key, since, until):
    """동일 광고주·기간으로 이미 성공 발송된 이력이 있는지 확인."""
    for h in history:
        if (h.get("client") == client_name
                and h.get("period") == period_key
                and h.get("since") == since
                and h.get("until") == until
                and "성공" in str(h.get("status", ""))):
            return True
    return False


def _get_last_sent(history, client_name):
    """해당 광고주의 마지막 성공 발송일시 반환."""
    for h in reversed(history):
        if h.get("client") == client_name and "성공" in str(h.get("status", "")):
            return h.get("sent_at", "-")
    return "-"


st.session_state.report_admin_auth = True

# ── 권한 분기 ─────────────────────────────────────────────────────────
_is_admin = st.session_state.get("auth_type", "") == "admin"
_username = st.session_state.get("auth_username", "")

from auth import feature_access_guard
feature_access_guard("monthly_report", "월간보고서")

# ── 헤더 ──────────────────────────────────────────────────────────────
st.title("📊 광고 보고서 관리")
if not _is_admin:
    st.caption(f"👤 {_username} 님 | 본인 데이터만 열람 가능합니다.")

with st.expander("📖 이용안내 — 처음 사용하시는 분께", expanded=False):
    st.markdown("""
**순서대로 따라하면 바로 시작할 수 있어요!**

**① 광고주 등록**
**[광고주 관리]** 탭 → **[+ 광고주 추가]** 클릭 → 이름·이메일·API 키·Customer ID 입력 후 저장
(API 키는 네이버 검색광고 → 내 정보 → API 관리 에서 발급)

**② 보고서 생성**
**[보고서 발송]** 탭 → 광고주 선택 → 조회 기간 선택 → **[보고서 생성]** 클릭

**③ 미리보기 확인**
화면에 표시된 보고서(지표 요약·그래프·키워드 분석 포함)를 먼저 확인하세요

**④ 발송 또는 저장**
**[이메일 발송]** 버튼으로 광고주에게 바로 전송하거나 **[PDF 다운로드]**로 파일 저장

**⑤ 자동 정기발송 설정 (선택)**
**[보고서 자동발송]** 탭 → 광고주별 발송 일자·시간 설정 → 매월 자동 발송
발송 내역은 **[발송 이력]** 탭에서 언제든 확인 가능

> 💡 **팁** : 광고주를 한 번 등록해두면 다음 달부터 클릭 한 번으로 보고서를 발송할 수 있어요.
    """)

tab1, tab2, tab_auto, tab3, tab4, tab5 = st.tabs(["👥 광고주 관리", "📋 보고서 발송", "📅 보고서 자동발송", "📜 발송 이력", "⚙️ 설정", "📅 예약관리"])


# ═══════════════════════════════════════════════════════════════════════
# 탭1: 광고주 관리 (owner 기반 필터링)
# ═══════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("새 광고주 추가")
    with st.form("add_client", clear_on_submit=True):
        fc1, fc2 = st.columns(2)
        with fc1:
            name       = st.text_input("광고주명 *")
            cust_id    = st.text_input("Customer ID *", help="searchad.naver.com → URL 숫자")
            email      = st.text_input("수신 이메일 *")
            phone      = st.text_input("카카오 알림 전화번호", placeholder="010-0000-0000",
                                       help="보고서 발송 시 SMS/카카오 알림 수신 번호")
        with fc2:
            api_key    = st.text_input("API Access License *")
            secret_key = st.text_input("Secret Key *", type="password")
            memo       = st.text_input("메모")

        if st.form_submit_button("➕ 추가", type="primary"):
            if not all([name, cust_id, email, api_key, secret_key]):
                st.error("* 항목을 모두 입력해주세요.")
            else:
                _all_c = load_clients()
                _all_c.append({
                    "id":           datetime.now().strftime("%Y%m%d%H%M%S"),
                    "name":         name.strip(),
                    "customer_id":  cust_id.strip(),
                    "email":        email.strip(),
                    "phone":        _fmt_phone(phone),
                    "api_key":      api_key.strip(),
                    "secret_key":   secret_key.strip(),
                    "memo":         memo,
                    "created_at":   datetime.now().strftime("%Y-%m-%d"),
                    "owner":        _username,
                    "approved":     _is_admin,  # 관리자 추가 시 즉시 승인
                })
                save_clients(_all_c)
                if _is_admin:
                    st.success(f"✅ {name} 추가 완료!")
                else:
                    st.success(f"✅ {name} 등록 요청 완료! 관리자 승인 후 활성화됩니다.")
                st.rerun()

    st.divider()

    # ── 승인 대기 (관리자 전용) ───────────────────────────────────────
    if _is_admin:
        _all_clients_raw = load_clients()
        _pending_list = [c for c in _all_clients_raw if not c.get("approved", True)]
        if _pending_list:
            st.warning(f"⏳ 승인 대기 중인 광고주 {len(_pending_list)}명")
            for _pc in _pending_list:
                _pa, _pb, _pc2 = st.columns([5, 1, 1])
                _pa.write(f"**{_pc['name']}** | {_pc['email']} | 등록자: **{_pc.get('owner','-')}**")
                if _pb.button("✅ 승인", key=f"approve_{_pc['id']}"):
                    for _cc in _all_clients_raw:
                        if _cc["id"] == _pc["id"]:
                            _cc["approved"] = True
                    save_clients(_all_clients_raw)
                    st.rerun()
                if _pc2.button("❌ 거부", key=f"reject_{_pc['id']}"):
                    save_clients([c for c in _all_clients_raw if c["id"] != _pc["id"]])
                    st.rerun()
            st.divider()

    st.subheader("등록된 광고주")
    _all_c2 = load_clients()
    # 관리자: 승인된 것 전체 / 비관리자: 본인 등록 + 승인된 것만
    if _is_admin:
        clients = [c for c in _all_c2 if c.get("approved", True)]
    else:
        clients = [c for c in _all_c2
                   if c.get("owner", "") == _username and c.get("approved", True)]

    if not clients:
        st.info("등록된 광고주가 없습니다.")
    else:
        for i, cl in enumerate(clients):
            _owner_tag = f" | 등록자: {cl.get('owner','-')}" if _is_admin else ""
            with st.expander(f"**{cl['name']}** | {cl['email']} | ID: {cl['customer_id']}{_owner_tag}"):
                ec1, ec2, ec3, ec4 = st.columns([4, 1, 1, 1])
                with ec1:
                    st.caption(
                        f"등록일: {cl.get('created_at','-')} | "
                        f"전화: {cl.get('phone','-') or '-'} | "
                        f"메모: {cl.get('memo','-') or '-'}"
                    )
                    st.caption(f"API Key: {cl['api_key'][:20]}...")
                with ec2:
                    if st.button("🔌 연결 테스트", key=f"test_{i}"):
                        with st.spinner("확인 중..."):
                            try:
                                api = NaverAdAPI(cl["api_key"], cl["secret_key"], cl["customer_id"])
                                ok, msg = api.test_connection()
                                st.success(msg) if ok else st.error(msg)
                            except Exception as e:
                                st.error(str(e))
                with ec3:
                    if st.button("✏️ 편집", key=f"edit_btn_{i}"):
                        st.session_state[f"editing_{i}"] = True
                with ec4:
                    if st.button("🗑️ 삭제", key=f"del_{i}"):
                        save_clients([c for c in _all_c2 if c["id"] != cl["id"]])
                        st.rerun()

                if st.session_state.get(f"editing_{i}"):
                    st.divider()
                    with st.form(key=f"edit_form_{i}"):
                        ef1, ef2 = st.columns(2)
                        with ef1:
                            e_name   = st.text_input("광고주명",   value=cl.get("name", ""),     key=f"e_name_{i}")
                            e_email  = st.text_input("수신 이메일", value=cl.get("email", ""),    key=f"e_email_{i}")
                            e_phone  = st.text_input("카카오 알림 전화번호", value=cl.get("phone", ""),
                                                     placeholder="010-0000-0000", key=f"e_phone_{i}")
                        with ef2:
                            e_apikey = st.text_input("API Access License", value=cl.get("api_key", ""), key=f"e_api_{i}")
                            e_secret = st.text_input("Secret Key", value=cl.get("secret_key", ""),
                                                     type="password", key=f"e_secret_{i}")
                            e_memo   = st.text_input("메모", value=cl.get("memo", ""),            key=f"e_memo_{i}")

                        esub1, esub2 = st.columns(2)
                        _save   = esub1.form_submit_button("💾 저장", type="primary", use_container_width=True)
                        _cancel = esub2.form_submit_button("취소", use_container_width=True)

                        if _save:
                            for _cc2 in _all_c2:
                                if _cc2["id"] == cl["id"]:
                                    _cc2.update({
                                        "name":       e_name.strip(),
                                        "email":      e_email.strip(),
                                        "phone":      _fmt_phone(e_phone),
                                        "api_key":    e_apikey.strip(),
                                        "secret_key": e_secret.strip(),
                                        "memo":       e_memo,
                                    })
                            save_clients(_all_c2)
                            st.session_state.pop(f"editing_{i}", None)
                            st.rerun()
                        if _cancel:
                            st.session_state.pop(f"editing_{i}", None)
                            st.rerun()


# ═══════════════════════════════════════════════════════════════════════
# 탭2: 보고서 발송
# ═══════════════════════════════════════════════════════════════════════
with tab2:
    _all_clients_t2 = load_clients()
    # 비관리자: 본인 등록 + 승인된 광고주만
    if _is_admin:
        clients = [c for c in _all_clients_t2 if c.get("approved", True)]
    else:
        clients = [c for c in _all_clients_t2
                   if c.get("owner", "") == _username and c.get("approved", True)]
    if not clients:
        st.warning("등록된 광고주가 없습니다. 광고주 관리 탭에서 추가하세요.")
        st.stop()

    send_mode = st.radio(
        "발송 방식",
        ["단일 발송", "일괄 발송"],
        horizontal=True,
        key="send_mode_radio",
    )

    # ─────────────────────────────────────────────────────────────────
    # 단일 발송 (기존 로직 유지)
    # ─────────────────────────────────────────────────────────────────
    if send_mode == "단일 발송":
        st.subheader("① 발송 설정")
        sc1, sc2 = st.columns([2, 1])
        with sc1:
            selected_names = st.multiselect(
                "광고주 선택",
                options=[c["name"] for c in clients],
                default=[],
            )
        with sc2:
            period_label = st.radio("기간", ["주간 (지난 7일)", "월간 (지난달)"], horizontal=True)
            period_key = "weekly" if "주간" in period_label else "monthly"

        _fmt_col, _plt_col = st.columns([1, 1])
        with _fmt_col:
            report_fmt_single = st.radio(
                "보고서 형식",
                ["기존 보고서", "월간보고서 V2"],
                index=0,
                horizontal=True,
                key="report_fmt_single",
                help="V2: 일자별/주차별/키워드 TOP10 분석 보고서 (기존 보고서가 기본값)",
            )
        with _plt_col:
            platform_single = st.radio(
                "플랫폼",
                ["네이버", "구글", "카카오", "당근"],
                index=0,
                horizontal=True,
                key="platform_single",
                help="현재 네이버만 지원. 구글/카카오/당근은 준비 중.",
            ) if report_fmt_single == "월간보고서 V2" else "네이버"

        if not selected_names:
            st.info("광고주를 선택하세요.")
        else:
            selected_clients = [c for c in clients if c["name"] in selected_names]

            st.subheader("② 보고서 미리보기")
            if st.button("🔍 보고서 데이터 수집 및 미리보기 생성", type="secondary", use_container_width=True):
                import pandas as pd
                results = []
                for client in selected_clients:
                    with st.status(
                        f"📡 {client['name']} 데이터 수집 중...",
                        expanded=True,
                    ) as _col_status:
                        _step_msg = st.empty()

                        def _on_step(msg, _el=_step_msg):
                            _el.write(msg)

                        try:
                            api  = NaverAdAPI(client["api_key"], client["secret_key"], client["customer_id"])
                            data = api.fetch_report(period_key, on_step=_on_step)
                            _rpt_date = datetime.now().strftime("%Y-%m-%d")
                            if report_fmt_single == "월간보고서 V2":
                                _plt = st.session_state.get("platform_single", "네이버")
                                if _plt != "네이버":
                                    st.warning(f"⚠️ {_plt} 플랫폼은 준비 중입니다. 네이버로 대체합니다.")
                                _on_step("V2: 주차별/전월 데이터 수집 중 (5회 API 호출)...")
                                _v2e = fetch_v2_extra(api, data["since"], data["until"])
                                # debug 출력
                                for _dbg in _v2e.get("debug", []):
                                    _on_step(f"  ↳ {_dbg}")
                                _norm = normalize_naver_data(data, _v2e)
                                html = build_monthly_report_v2(
                                    data, client["name"], _rpt_date, v2_extra=_v2e
                                )
                            else:
                                html = generate_html(data, client["name"], _rpt_date)
                            results.append({"client": client, "data": data, "html": html, "status": "ok"})
                            sm = data.get("summary", {})
                            _col_status.update(
                                label=(
                                    f"✅ {client['name']} 완료 — "
                                    f"캠페인 {data['total_campaigns']}개 | "
                                    f"키워드 {data['total_keywords']}개 | "
                                    f"클릭 {sm.get('clicks', 0):,}회"
                                ),
                                state="complete",
                                expanded=False,
                            )
                        except Exception as e:
                            results.append({"client": client, "error": str(e), "status": "error"})
                            _col_status.update(
                                label=f"❌ {client['name']} 오류",
                                state="error",
                            )
                            st.error(f"❌ {client['name']} 오류: {e}")

                for r in results:
                    if r["status"] != "ok":
                        continue
                    client = r["client"]
                    data   = r["data"]
                    sm     = data.get("summary", {})
                    kwsm   = data.get("kw_summary", {})
                    dbg    = data.get("debug_params", {})
                    kws    = data["keywords"]

                    with st.expander(f"🔎 {client['name']} 데이터 검증", expanded=True):
                        st.markdown("**① API 요청 정보**")
                        dc1, dc2, dc3 = st.columns(3)
                        dc1.text(f"Customer ID : {dbg.get('customer_id','')}")
                        dc2.text(f"조회 시작일  : {dbg.get('since','')}")
                        dc3.text(f"조회 종료일  : {dbg.get('until','')}")
                        st.caption(
                            f"Endpoint: {dbg.get('endpoint','')}  |  "
                            f"Fields: {dbg.get('fields','')}  |  "
                            f"캠페인 통계 row: {dbg.get('camp_stat_rows',0)}  |  "
                            f"키워드 통계 row: {dbg.get('kw_stat_rows',0)}  |  "
                            f"캠페인: {dbg.get('total_campaigns',0)}개  "
                            f"광고그룹: {dbg.get('total_adgroups',0)}개  "
                            f"키워드: {dbg.get('total_keywords',0)}개"
                        )
                        st.divider()
                        st.markdown("**② 캠페인 레벨 집계 (KPI 카드 기준)**")
                        mc1, mc2, mc3, mc4, mc5 = st.columns(5)
                        mc1.metric("클릭수",   f"{sm.get('clicks',0):,}")
                        mc2.metric("노출수",   f"{sm.get('impressions',0):,}")
                        mc3.metric("전환수",   f"{sm.get('conversions',0):,}")
                        mc4.metric("전환매출", f"{sm.get('revenue',0):,}")
                        mc5.metric("추정비용", f"{sm.get('cost',0):,}")
                        st.markdown("**③ 키워드 레벨 합산**")
                        kc1, kc2, kc3, kc4, kc5 = st.columns(5)
                        kc1.metric("클릭수", f"{kwsm.get('clicks',0):,}",
                                   delta=f"{kwsm.get('clicks',0)-sm.get('clicks',0):+,}")
                        kc2.metric("노출수", f"{kwsm.get('impressions',0):,}",
                                   delta=f"{kwsm.get('impressions',0)-sm.get('impressions',0):+,}")
                        kc3.metric("전환수",   f"{kwsm.get('conversions',0):,}")
                        kc4.metric("전환매출", f"{kwsm.get('revenue',0):,}")
                        kc5.metric("추정비용", f"{kwsm.get('cost',0):,}")
                        st.divider()
                        camp_table = data.get("camp_table", [])
                        if camp_table:
                            st.markdown("**④ 캠페인별 성과**")
                            st.dataframe(pd.DataFrame(camp_table), use_container_width=True, hide_index=True)
                        if kws:
                            st.markdown("**⑤ 키워드 성과 상위 10행**")
                            _cols = ["keyword", "clicks", "impressions", "conversions",
                                     "revenue", "cost", "ctr", "cpc", "roas", "avg_rnk"]
                            st.dataframe(
                                pd.DataFrame(kws[:10])[[col for col in _cols if col in kws[0]]],
                                use_container_width=True, hide_index=True,
                            )
                        with st.expander("디버그 로그"):
                            for line in data.get("debug", []):
                                st.caption(line)

                st.session_state.preview_results = results
                st.session_state.preview_period  = period_key

            if "preview_results" in st.session_state:
                results    = st.session_state.preview_results
                ok_results = [r for r in results if r["status"] == "ok"]

                if ok_results:
                    st.divider()
                    preview_idx = st.selectbox(
                        "미리볼 광고주 선택",
                        options=range(len(ok_results)),
                        format_func=lambda i: ok_results[i]["client"]["name"],
                    )
                    r = ok_results[preview_idx]
                    d = r["data"]
                    with st.expander(f"📊 {r['client']['name']} 보고서 미리보기", expanded=True):
                        st.caption(
                            f"기간: {d['since']} ~ {d['until']} | "
                            f"키워드: {d['total_keywords']}개 | "
                            f"클릭: {sum(k['clicks'] for k in d['keywords']):,}회"
                        )
                        components.html(r["html"], height=1200, scrolling=True)

                    st.divider()
                    st.subheader("③ 이메일 발송")
                    smtp_user = get_secret("SMTP_USER", "")
                    if not smtp_user:
                        st.error("⚙️ 이메일 설정 탭에서 SMTP 설정을 먼저 해주세요.")
                    else:
                        period_k = st.session_state.get("preview_period", "monthly")
                        period_str = "주간" if period_k == "weekly" else "월간"
                        for r in ok_results:
                            st.info(
                                f"**{r['client']['name']}** → `{r['client']['email']}`  \n"
                                f"제목: [광고 성과 보고서] {r['client']['name']} | {period_str} "
                                f"({r['data']['since']} ~ {r['data']['until']})"
                            )
                        st.warning("⚠️ 위 내용을 확인하셨나요? 아래 버튼을 누르면 실제 이메일이 발송됩니다.")

                        _has_phone = all(r["client"].get("phone") for r in ok_results)
                        _any_phone = any(r["client"].get("phone") for r in ok_results)

                        _btn_col1, _btn_col2 = st.columns(2)
                        _send_email_only  = _btn_col1.button(
                            "✉️ 이메일만 발송", type="secondary", use_container_width=True,
                            key="btn_send_email_only",
                        )
                        _send_email_kakao = _btn_col2.button(
                            "✉️📱 이메일 + 카톡 발송", type="primary", use_container_width=True,
                            key="btn_send_email_kakao",
                            help="전화번호 미등록 광고주는 이메일만 발송됩니다",
                        )

                        _do_send  = _send_email_only or _send_email_kakao
                        _do_kakao = _send_email_kakao

                        # ── 예약 발송 ─────────────────────────────────
                        with st.expander("📅 나중에 발송하기 (예약 등록)"):
                            _sc1, _sc2, _sc3 = st.columns([2, 1, 1])
                            _sch_date = _sc1.date_input(
                                "발송 날짜",
                                min_value=date.today() + timedelta(days=1),
                                key="sch_date_single",
                            )
                            _sch_hour = _sc2.number_input("발송 시각(시)", 0, 23, 9, key="sch_hour_s")
                            _sc3.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                            if _sc3.button("📅 예약 등록", key="sch_btn_s", use_container_width=True):
                                import uuid as _uuid
                                _sch_dt = datetime.combine(_sch_date, datetime.min.time()).replace(hour=int(_sch_hour))
                                _sched = load_schedule()
                                _sched["scheduled"].append({
                                    "id":           datetime.now().strftime("%Y%m%d%H%M%S") + "_" + str(_uuid.uuid4())[:6],
                                    "client_ids":   [r["client"]["id"] for r in ok_results],
                                    "client_names": [r["client"]["name"] for r in ok_results],
                                    "period_key":   st.session_state.get("preview_period", "monthly"),
                                    "since":        str(ok_results[0]["data"]["since"]),
                                    "until":        str(ok_results[0]["data"]["until"]),
                                    "scheduled_at": _sch_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                                    "status":       "pending",
                                    "created_at":   datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                                    "error":        "",
                                    "send_mode":    "single",
                                })
                                save_schedule(_sched)
                                st.success(f"✅ {_sch_date.strftime('%Y-%m-%d')} {int(_sch_hour):02d}:00 발송 예약됐습니다!")
                                st.session_state.pop("preview_results", None)
                                st.rerun()

                        if _do_send:
                            smtp_cfg = {
                                "smtp_user":     smtp_user,
                                "smtp_password": get_secret("SMTP_PASSWORD", ""),
                                "smtp_host":     get_secret("SMTP_HOST", "smtp.naver.com"),
                                "smtp_port":     int(get_secret("SMTP_PORT", "465")),
                            }
                            history  = load_history()
                            period_k = st.session_state.get("preview_period", "monthly")

                            for r in ok_results:
                                client = r["client"]
                                _since = r["data"]["since"]
                                _until = r["data"]["until"]

                                # ── 이메일 발송 ────────────────────────────────
                                _email_ok   = False
                                _hist_entry = {
                                    "client":    client["name"],
                                    "email":     client["email"],
                                    "period":    period_k,
                                    "since":     _since,
                                    "until":     _until,
                                    "keywords":  r["data"]["total_keywords"],
                                    "sent_at":   datetime.now().strftime("%Y-%m-%d %H:%M"),
                                    "send_mode": "single",
                                }
                                try:
                                    send_report(
                                        to_email=client["email"],
                                        client_name=client["name"],
                                        period=period_k,
                                        since=_since,
                                        until=_until,
                                        html_body=r["html"],
                                        **smtp_cfg,
                                    )
                                    st.success(f"✅ **{client['name']}** → {client['email']} 이메일 발송 완료!")
                                    _hist_entry["status"] = "성공"
                                    _email_ok = True
                                except Exception as e:
                                    st.error(f"❌ **{client['name']}** 이메일 발송 실패: {e}")
                                    with st.expander("오류 상세 (디버그)"):
                                        st.code(traceback.format_exc())
                                    _hist_entry["status"] = f"실패: {str(e)[:100]}"

                                # ── 알림톡 발송 (이메일 성공 + 이메일+카톡 버튼 클릭 시) ─
                                _alimtalk_r = {"status": "skipped", "reason": "이메일 실패 또는 미요청"}
                                if _do_kakao and _email_ok:
                                    try:
                                        _at_phone = str(
                                            client.get("alert_phone", "")
                                            or client.get("phone", "") or ""
                                        ).strip()
                                        _since_dt     = datetime.strptime(_since, "%Y-%m-%d")
                                        _report_month = f"{_since_dt.year}년 {_since_dt.month}월"
                                        from notifications import send_monthly_report_alimtalk
                                        _alimtalk_r = send_monthly_report_alimtalk(
                                            phone=_at_phone,
                                            advertiser_name=client["name"],
                                            recipient_email=client["email"],
                                            report_month=_report_month,
                                        )
                                        _at_s = _alimtalk_r.get("status", "")
                                        if _at_s == "success":
                                            _ch = "알림톡" if _alimtalk_r.get("type") == "alimtalk" else "SMS"
                                            st.info(f"📱 **{client['name']}** → {_at_phone} {_ch} 발송 완료!")
                                        elif _at_s == "skipped":
                                            st.caption(f"📱 {client['name']} — {_alimtalk_r.get('reason','건너뜀')}")
                                        else:
                                            st.warning(
                                                f"📱 알림톡 발송 실패: "
                                                f"{_alimtalk_r.get('reason') or _alimtalk_r.get('error','')}"
                                            )
                                    except Exception as _at_e:
                                        _alimtalk_r = {"status": "failed", "error": str(_at_e)[:100]}
                                        st.warning(f"📱 알림톡 오류: {_at_e}")
                                _hist_entry["alimtalk_status"] = _alimtalk_r.get("status", "")
                                _hist_entry["alimtalk_error"]  = (
                                    _alimtalk_r.get("error") or _alimtalk_r.get("reason", "")
                                )
                                history.append(_hist_entry)

                            save_history(history)
                            st.session_state.pop("preview_results", None)

    # ─────────────────────────────────────────────────────────────────
    # 일괄 발송
    # ─────────────────────────────────────────────────────────────────
    else:
        st.subheader("① 발송 설정")

        bc1, bc2 = st.columns([2, 1])
        with bc1:
            period_label = st.radio(
                "발송 기간", ["주간 (지난 7일)", "월간 (지난달)"],
                horizontal=True, key="bulk_period",
            )
            period_key = "weekly" if "주간" in period_label else "monthly"
            since, until = _get_period_range(period_key)
            st.caption(f"분석 기간: **{since} ~ {until}**")
            report_fmt_bulk = st.radio(
                "보고서 형식",
                ["기존 보고서", "월간보고서 V2"],
                index=0,
                horizontal=True,
                key="report_fmt_bulk",
                help="V2: 일자별/주차별/키워드 TOP10 분석 보고서 (기존 보고서가 기본값)",
            )
            if report_fmt_bulk == "월간보고서 V2":
                platform_bulk = st.radio(
                    "플랫폼",
                    ["네이버", "구글", "카카오", "당근"],
                    index=0, horizontal=True, key="platform_bulk",
                    help="현재 네이버만 지원",
                )
        with bc2:
            dedup_on = st.checkbox(
                "중복 발송 방지",
                value=True,
                help="동일 광고주·기간 이미 성공 발송 시 스킵",
            )

        test_mode  = st.checkbox("🧪 테스트 모드 (실제 발송 없이 검증 / 관리자 이메일로 샘플 발송)")
        test_email = ""
        if test_mode:
            test_email = st.text_input(
                "테스트 수신 이메일",
                value=get_secret("SMTP_USER", ""),
                key="bulk_test_email",
            )

        st.divider()

        # 전체 선택/해제
        history_cur   = load_history()
        sendable_ids  = {c["id"] for c in clients if _client_sendable(c)[0]}

        sel_c1, sel_c2, _ = st.columns([1, 1, 4])
        if sel_c1.button("✅ 전체 선택"):
            for c in clients:
                can, _ = _client_sendable(c)
                already = _already_sent(history_cur, c["name"], period_key, since, until) if dedup_on else False
                st.session_state[f"bck_{c['id']}"] = can and not already
            st.rerun()
        if sel_c2.button("⬜ 전체 해제"):
            for c in clients:
                st.session_state[f"bck_{c['id']}"] = False
            st.rerun()

        # 광고주 테이블 헤더
        st.subheader("② 광고주 목록")
        th = st.columns([0.5, 2, 1.5, 2.2, 0.8, 1.5, 2])
        for col, hdr in zip(th, ["선택", "광고주명", "Customer ID", "수신 이메일", "API", "최근 발송", "비고"]):
            col.markdown(f"**{hdr}**")
        st.markdown("---")

        selected_bulk = []
        for c in clients:
            can_send, missing = _client_sendable(c)
            already   = _already_sent(history_cur, c["name"], period_key, since, until) if dedup_on else False
            last_sent = _get_last_sent(history_cur, c["name"])
            has_api   = bool(str(c.get("api_key", "")).strip() and str(c.get("secret_key", "")).strip())

            default_val = st.session_state.get(f"bck_{c['id']}", can_send and not already)

            row = st.columns([0.5, 2, 1.5, 2.2, 0.8, 1.5, 2])
            checked = row[0].checkbox("", key=f"bck_{c['id']}", value=default_val, disabled=not can_send)
            row[1].write(c.get("name", "-"))
            row[2].caption(c.get("customer_id", "") or "❌")
            row[3].caption(c.get("email", "") or "❌ 없음")
            row[4].markdown("✅" if has_api else "❌")
            row[5].caption(last_sent)

            if not can_send:
                row[6].caption(f"🚫 누락: {', '.join(missing)}")
            elif already and dedup_on:
                row[6].caption("⚠️ 이미 발송됨")
            else:
                row[6].caption("✅ 발송 대상")

            if checked and can_send:
                selected_bulk.append(c)

        st.divider()

        # 요약 지표
        st.subheader("③ 선택 현황")
        total_n    = len(clients)
        sendable_n = len([c for c in clients if _client_sendable(c)[0]])
        selected_n = len(selected_bulk)
        already_n  = sum(
            1 for c in clients
            if _client_sendable(c)[0] and _already_sent(history_cur, c["name"], period_key, since, until)
        ) if dedup_on else 0

        sm1, sm2, sm3, sm4 = st.columns(4)
        sm1.metric("전체 광고주",    total_n)
        sm2.metric("발송 가능",      sendable_n)
        sm3.metric("선택됨",         selected_n)
        sm4.metric("중복(기발송)",   already_n if dedup_on else "-")

        # 발송 실행
        st.divider()
        smtp_user = get_secret("SMTP_USER", "")
        if not smtp_user and not test_mode:
            st.warning("⚙️ 설정 탭에서 SMTP 설정을 먼저 해주세요.")
        elif selected_n == 0:
            st.info("발송할 광고주를 선택하세요.")
        else:
            btn_label = (
                f"🧪 테스트 검증 실행 ({selected_n}명)"
                if test_mode
                else f"✉️ 선택 광고주 월간보고서 일괄 발송 ({selected_n}명)"
            )
            if st.button(btn_label, type="primary", use_container_width=True):
                smtp_cfg = {
                    "smtp_user":     smtp_user,
                    "smtp_password": get_secret("SMTP_PASSWORD", ""),
                    "smtp_host":     get_secret("SMTP_HOST", "smtp.naver.com"),
                    "smtp_port":     int(get_secret("SMTP_PORT", "465")),
                }
                history = load_history()

                progress_bar = st.progress(0, text="일괄 발송 준비 중...")
                status_box   = st.empty()

                success_list, fail_list, skip_list, log_list = [], [], [], []
                total_sel = len(selected_bulk)

                for idx, client in enumerate(selected_bulk):
                    progress_bar.progress(idx / total_sel, text=f"{idx+1}/{total_sel} {client['name']} 처리 중...")
                    status_box.info(f"⏳ {idx+1}/{total_sel} — **{client['name']}** 보고서 생성 중...")

                    # 실행 시점 중복 재확인
                    if dedup_on and _already_sent(history, client["name"], period_key, since, until):
                        skip_list.append(client["name"])
                        log_list.append(f"⏭️ {client['name']}: 이미 발송됨 (스킵)")
                        history.append({
                            "client":    client["name"],
                            "email":     client.get("email", ""),
                            "period":    period_key,
                            "since":     since,
                            "until":     until,
                            "sent_at":   datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "status":    "스킵: 중복",
                            "send_mode": "bulk",
                        })
                        continue

                    try:
                        api  = NaverAdAPI(client["api_key"], client["secret_key"], client["customer_id"])
                        data = api.fetch_report(period_key)
                        _rpt_date_b = datetime.now().strftime("%Y-%m-%d")
                        if report_fmt_bulk == "월간보고서 V2":
                            _v2e_b = fetch_v2_extra(api, data["since"], data["until"])
                            for _dbg_b in _v2e_b.get("debug", []):
                                log_list.append(f"  V2 {client['name']}: {_dbg_b}")
                            _norm_b = normalize_naver_data(data, _v2e_b)
                            html = build_monthly_report_v2(data, client["name"], _rpt_date_b, v2_extra=_v2e_b)
                        else:
                            html = generate_html(data, client["name"], _rpt_date_b)

                        to_addr = test_email if test_mode else client["email"]
                        status_box.info(f"📧 {idx+1}/{total_sel} — **{client['name']}** → {to_addr} 발송 중...")

                        if not test_mode or to_addr:
                            send_report(
                                to_email=to_addr,
                                client_name=f"[테스트] {client['name']}" if test_mode else client["name"],
                                period=period_key,
                                since=data["since"],
                                until=data["until"],
                                html_body=html,
                                **smtp_cfg,
                            )

                        label = f"{client['name']} (테스트→{to_addr})" if test_mode else f"{client['name']} / {client['email']}"
                        success_list.append(label)
                        log_list.append(f"✅ {client['name']}: {'테스트 완료' if test_mode else '발송 완료'} → {to_addr}")

                        # ── 알림톡 (실제 발송 + 설정 활성화 시) ─────────────
                        _bulk_at_r = {"status": "skipped", "reason": "테스트 모드"}
                        if not test_mode:
                            from notifications import get_notify_config as _gcfg_b, send_monthly_report_alimtalk as _sat_b
                            if _gcfg_b().get("monthly_report_alimtalk_enabled", False):
                                try:
                                    _bphone = str(
                                        client.get("alert_phone", "")
                                        or client.get("phone", "") or ""
                                    ).strip()
                                    _bd      = datetime.strptime(data["since"], "%Y-%m-%d")
                                    _bulk_at_r = _sat_b(
                                        phone=_bphone,
                                        advertiser_name=client["name"],
                                        recipient_email=client["email"],
                                        report_month=f"{_bd.year}년 {_bd.month}월",
                                    )
                                    _bst = _bulk_at_r.get("status", "")
                                    log_list.append(
                                        f"📱 {client['name']}: 알림톡 {_bst}"
                                        + (f" — {_bulk_at_r.get('reason') or _bulk_at_r.get('error','')}"
                                           if _bst != "success" else "")
                                    )
                                except Exception as _be:
                                    _bulk_at_r = {"status": "failed", "error": str(_be)[:100]}
                                    log_list.append(f"📱 {client['name']}: 알림톡 오류 — {_be}")
                            else:
                                _bulk_at_r = {"status": "skipped", "reason": "알림톡 미사용 설정"}

                        history.append({
                            "client":          client["name"],
                            "email":           to_addr,
                            "period":          period_key,
                            "since":           data["since"],
                            "until":           data["until"],
                            "keywords":        data.get("total_keywords", 0),
                            "sent_at":         datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "status":          "테스트" if test_mode else "성공",
                            "send_mode":       "bulk_test" if test_mode else "bulk",
                            "alimtalk_status": _bulk_at_r.get("status", ""),
                            "alimtalk_error":  _bulk_at_r.get("error") or _bulk_at_r.get("reason", ""),
                        })

                    except Exception as e:
                        err = str(e)[:120]
                        fail_list.append(f"{client['name']} — {err}")
                        log_list.append(f"❌ {client['name']}: 실패 — {err}")
                        history.append({
                            "client":    client["name"],
                            "email":     client.get("email", ""),
                            "period":    period_key,
                            "since":     since,
                            "until":     until,
                            "sent_at":   datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "status":    f"실패: {err}",
                            "send_mode": "bulk",
                        })

                progress_bar.progress(1.0, text="완료!")
                status_box.empty()
                save_history(history)

                # 결과 요약
                st.divider()
                st.subheader("📋 발송 결과 요약")
                rs1, rs2, rs3, rs4 = st.columns(4)
                rs1.metric("총 선택",  total_sel)
                rs2.metric("✅ 성공",  len(success_list))
                rs3.metric("❌ 실패",  len(fail_list))
                rs4.metric("⏭️ 스킵",  len(skip_list))

                if success_list:
                    st.success("**발송 성공:**\n" + "\n".join(f"• {s}" for s in success_list))
                if fail_list:
                    st.error("**발송 실패:**\n" + "\n".join(f"• {f}" for f in fail_list))
                if skip_list:
                    st.info("**스킵 (중복):**\n" + "\n".join(f"• {s}" for s in skip_list))
                with st.expander("📄 상세 로그"):
                    for log in log_list:
                        st.caption(log)


# ═══════════════════════════════════════════════════════════════════════
# 탭3: 발송 이력
# ═══════════════════════════════════════════════════════════════════════
with tab3:
    history = load_history()
    # 비관리자: 본인 광고주 이력만
    if not _is_admin:
        _my_clients = {c["name"] for c in load_clients()
                       if c.get("owner","") == _username and c.get("approved", True)}
        history = [h for h in history if h.get("client","") in _my_clients]
    if not history:
        st.info("발송 이력이 없습니다.")
    else:
        import pandas as pd
        df = pd.DataFrame(list(reversed(history)))
        st.dataframe(df, use_container_width=True, hide_index=True)
        if _is_admin and st.button("🗑️ 이력 초기화"):
            save_history([])
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════
# 탭4: 설정
# ═══════════════════════════════════════════════════════════════════════
with tab4:
    if not _is_admin:
        st.info("🔒 설정은 관리자만 접근할 수 있습니다.")

if _is_admin:
 with tab4:
    st.success("✅ 월간보고서 알림톡 설정 UI v1 적용됨")
    st.subheader("이메일 발송 설정")
    smtp_user = get_secret("SMTP_USER", "")
    if smtp_user:
        st.success(f"✅ 발송 계정: {smtp_user}")
    else:
        st.error("❌ 이메일 설정 없음")

    st.info("Streamlit Cloud → 앱 Settings → Secrets 에 아래 내용 입력")
    st.code("""SMTP_USER = "발송계정@naver.com"
SMTP_PASSWORD = "네이버앱비밀번호12자리"
SMTP_HOST = "smtp.naver.com"
SMTP_PORT = "465"
ADMIN_PASSWORD = "관리자비밀번호"
""", language="toml")

    st.divider()
    st.subheader("카카오 알림톡 설정")
    from notifications import get_notify_config, save_notify_config
    _ncfg = get_notify_config()

    # SOLAPI 설정 상태 표시 (실제 값은 숨김)
    _api_key_ok = bool(get_secret("SOLAPI_API_KEY", ""))
    _api_sec_ok = bool(get_secret("SOLAPI_API_SECRET", ""))
    _sender_ok  = bool(get_secret("SOLAPI_SENDER_ID", ""))
    _sc1, _sc2, _sc3 = st.columns(3)
    _sc1.metric("SOLAPI_API_KEY",    "✅ 설정됨" if _api_key_ok else "❌ 없음")
    _sc2.metric("SOLAPI_API_SECRET", "✅ 설정됨" if _api_sec_ok else "❌ 없음")
    _sc3.metric("SOLAPI_SENDER_ID",  "✅ 설정됨" if _sender_ok  else "❌ 없음")
    if not (_api_key_ok and _api_sec_ok and _sender_ok):
        st.error("❌ SOLAPI 미설정 — secrets.toml에 SOLAPI_API_KEY / SOLAPI_API_SECRET / SOLAPI_SENDER_ID 추가 필요")

    with st.form("monthly_alimtalk_cfg_form"):
        _at_enabled = st.checkbox(
            "알림톡 사용 (일괄 발송 시 이메일 성공 후 자동 발송)",
            value=bool(_ncfg.get("monthly_report_alimtalk_enabled", False)),
        )
        _at_tmpl = st.text_input(
            "월간보고서 알림톡 템플릿 ID",
            value=(
                _ncfg.get("monthly_report_template_id", "")
                or get_secret("MONTHLY_REPORT_ALIMTALK_TEMPLATE_ID", "")
            ),
            placeholder="KA01TP...",
            help="Solapi 대시보드 → 알림톡 → 템플릿 관리에서 승인된 템플릿 ID (미입력 시 SMS 폴백)",
        )
        _at_pf = st.text_input(
            "카카오 채널 ID (pfId)",
            value=(
                _ncfg.get("monthly_report_pf_id", "")
                or get_secret("SOLAPI_KAKAO_PF_ID", "")
            ),
            placeholder="KA01PF...",
        )
        if st.form_submit_button("💾 저장", type="primary"):
            _ncfg["monthly_report_alimtalk_enabled"] = _at_enabled
            _ncfg["monthly_report_template_id"]      = _at_tmpl.strip()
            _ncfg["monthly_report_pf_id"]            = _at_pf.strip()
            save_notify_config(_ncfg)
            st.success("저장됐습니다.")
            st.rerun()

    _at_cur_tmpl = _ncfg.get("monthly_report_template_id", "")
    if _at_cur_tmpl:
        st.success(f"✅ 템플릿 ID 설정됨: `{_at_cur_tmpl}`")
    else:
        st.info("📱 템플릿 ID 미설정 → 이메일+카톡 버튼 클릭 시 SMS로 폴백 발송")

    with st.expander("📋 Solapi 등록할 템플릿 내용 (복사용)"):
        st.code(
            "[마케팁 월간보고서 안내]\n\n"
            "#{광고주명}님의 #{보고서월} 월간 광고 보고서가\n"
            "등록된 이메일로 발송되었습니다.\n\n"
            "수신 이메일:\n#{발송이메일}\n\n"
            "메일함에서 보고서를 확인해 주세요.\n감사합니다.",
            language="text",
        )
        st.caption("템플릿 변수: #{광고주명}  #{보고서월}  #{발송이메일}")

    st.divider()
    st.subheader("알림톡 테스트 발송")
    _at_test_phone = st.text_input(
        "테스트 수신번호",
        value=_ncfg.get("monthly_report_test_phone", ""),
        placeholder="010-0000-0000",
        key="at_test_phone_input",
    )
    if st.button("📱 알림톡 테스트 발송"):
        _t_ph = _at_test_phone.strip()
        if not _t_ph:
            st.warning("테스트 수신번호를 입력하세요.")
        elif not (_api_key_ok and _api_sec_ok and _sender_ok):
            st.error("SOLAPI 설정이 필요합니다.")
        else:
            _ncfg["monthly_report_test_phone"] = _t_ph
            save_notify_config(_ncfg)
            try:
                from notifications import send_monthly_report_alimtalk
                _tr = send_monthly_report_alimtalk(
                    phone=_t_ph,
                    advertiser_name="테스트 광고주",
                    recipient_email="test@example.com",
                    report_month="2026년 5월",
                )
                _tst = _tr.get("status", "")
                if _tst == "success":
                    _tch = "알림톡" if _tr.get("type") == "alimtalk" else "SMS"
                    st.success(f"✅ {_tch} 테스트 발송 완료! ({_t_ph})")
                elif _tst == "skipped":
                    st.info(f"건너뜀: {_tr.get('reason', '')}")
                else:
                    st.error(f"❌ 실패: {_tr.get('error') or _tr.get('reason', '')}")
            except Exception as _te:
                st.error(f"오류: {_te}")

    st.divider()
    st.subheader("테스트 이메일 발송")
    test_to = st.text_input("수신 이메일", value=smtp_user)
    if st.button("📧 테스트 발송"):
        if not smtp_user:
            st.error("SMTP 설정을 먼저 해주세요.")
        else:
            try:
                send_report(
                    to_email=test_to,
                    client_name="테스트",
                    period="weekly",
                    since="2026-01-01",
                    until="2026-01-07",
                    html_body="<html><body><h2>✅ 테스트 이메일 - 발송 시스템 정상 작동</h2></body></html>",
                    smtp_user=smtp_user,
                    smtp_password=get_secret("SMTP_PASSWORD", ""),
                    smtp_host=get_secret("SMTP_HOST", "smtp.naver.com"),
                    smtp_port=int(get_secret("SMTP_PORT", "465")),
                )
                st.success(f"✅ {test_to} 발송 성공!")
            except Exception as e:
                st.error(f"❌ 실패: {e}")



# ═══════════════════════════════════════════════════════════════════════
# 탭 자동발송: 자동 정기발송 설정
# ═══════════════════════════════════════════════════════════════════════
with tab_auto:
    if not _is_admin:
        st.info("🔒 자동발송 설정은 관리자만 접근할 수 있습니다.")

if _is_admin:
 with tab_auto:
    st.subheader("🔄 자동 정기발송")
    st.caption("업체별로 **매월**(지난달 보고서) 또는 **격주(2주마다)**(최근 2주 보고서) 자동발송을 선택할 수 있습니다. (scheduler.py 실행 중일 때 동작)")
    _auto_clients = load_clients()
    _auto_sched   = load_schedule()
    _auto_cfg     = _auto_sched.get("auto_monthly", {})

    if not _auto_clients:
        st.info("광고주를 먼저 등록해주세요.")
    else:
        with st.form("auto_monthly_cfg"):
            _gcol1, _gcol2 = st.columns(2)
            _g_day  = _gcol1.number_input("매월 발송일 (월간 발송용)", 1, 28, int(_auto_cfg.get("_global_day",  5)))
            _g_hour = _gcol2.number_input("발송 시각(시)",            0, 23, int(_auto_cfg.get("_global_hour", 9)))
            st.caption("격주 발송은 직전 발송일로부터 14일 경과 시 위 '발송 시각'에 자동 발송됩니다.")
            st.markdown("**광고주별 자동발송 설정:**")
            _hc1, _hc2 = st.columns([2, 2])
            _hc1.markdown("<span style='font-size:12px;color:#6B7280;'>광고주 (체크 시 활성)</span>", unsafe_allow_html=True)
            _hc2.markdown("<span style='font-size:12px;color:#6B7280;'>발송 주기</span>", unsafe_allow_html=True)
            _settings = {}
            for _ac in _auto_clients:
                _acid  = _ac.get("id") or _ac.get("name", "")
                _cname = _ac.get("name", "")
                _prev  = _auto_cfg.get(_cname, {})
                _cc1, _cc2 = st.columns([2, 2])
                _en = _cc1.checkbox(_cname, value=bool(_prev.get("enabled", False)), key=f"auto_tog_{_acid}")
                _opts5 = ["매월", "격주(2주)", "매월 + 격주(2주)"]
                _fidx  = {"monthly": 0, "biweekly": 1, "both": 2}.get(_prev.get("freq", "monthly"), 0)
                _fr = _cc2.selectbox(
                    "주기", _opts5, index=_fidx,
                    key=f"auto_freq_{_acid}", label_visibility="collapsed",
                )
                _freq5 = {"매월": "monthly", "격주(2주)": "biweekly", "매월 + 격주(2주)": "both"}[_fr]
                _settings[_cname] = (_en, _freq5)
            if st.form_submit_button("💾 저장", type="primary"):
                _migrated = {}
                for _k, _v in _auto_cfg.items():
                    if _k.startswith("_"):
                        _migrated[_k] = _v
                        continue
                    _cn = _v.get("client_name") or _k
                    _migrated[_cn] = _v
                _auto_cfg = _migrated
                for _cname, (_en, _freq) in _settings.items():
                    _prev = _auto_cfg.get(_cname, {})
                    _auto_cfg[_cname] = {
                        "enabled":         _en,
                        "freq":            _freq,
                        "send_day":        int(_g_day),
                        "send_hour":       int(_g_hour),
                        "last_sent_month": _prev.get("last_sent_month", ""),
                        "last_sent_date":  _prev.get("last_sent_date", ""),
                    }
                _auto_cfg["_global_day"]  = int(_g_day)
                _auto_cfg["_global_hour"] = int(_g_hour)
                _auto_sched["auto_monthly"] = _auto_cfg
                save_schedule(_auto_sched)
                st.success(f"✅ 저장됨 — 발송 시각 {int(_g_hour):02d}:00 (매월 {int(_g_day)}일 / 격주 14일 주기)")
                st.rerun()

        _on_list = []
        for _ac in _auto_clients:
            _c = _auto_cfg.get(_ac.get("name", ""), {})
            if _c.get("enabled"):
                _on_list.append(f"{_ac['name']}({'격주' if _c.get('freq')=='biweekly' else '매월'})")
        if _on_list:
            st.info(f"🔄 자동발송 대상: {', '.join(_on_list)}")


# ═══════════════════════════════════════════════════════════════════════
# 탭5: 예약관리
# ═══════════════════════════════════════════════════════════════════════
with tab5:
    if not _is_admin:
        st.info("🔒 예약관리는 관리자만 접근할 수 있습니다.")

if _is_admin:
 with tab5:
    st.subheader("📅 예약발송 관리")
    _t5_sched   = load_schedule()
    _t5_items   = _t5_sched.get("scheduled", [])
    _t5_now     = datetime.now()
    _t5_pending = [i for i in _t5_items if i.get("status") == "pending"]
    _t5_overdue = [i for i in _t5_pending
                   if i.get("scheduled_at", "") <= _t5_now.strftime("%Y-%m-%dT%H:%M:%S")]
    _t5_done    = [i for i in _t5_items if i.get("status") != "pending"]

    if _t5_pending:
        st.markdown("**⏳ 대기 중인 예약**")
        if _t5_overdue:
            st.warning(f"⚠️ {len(_t5_overdue)}건의 예약 발송 시간이 지났습니다. "
                       f"Streamlit Cloud는 백그라운드 자동 실행을 지원하지 않아 수동 발송이 필요합니다.")
            if st.button(f"▶️ 기한 지난 예약 지금 발송 ({len(_t5_overdue)}건)",
                         type="primary", key="t5_run_overdue"):
                _smtp_cfg5 = {
                    "smtp_user":     get_secret("SMTP_USER", ""),
                    "smtp_password": get_secret("SMTP_PASSWORD", ""),
                    "smtp_host":     get_secret("SMTP_HOST", "smtp.naver.com"),
                    "smtp_port":     int(get_secret("SMTP_PORT", "465")),
                }
                _clients5   = load_clients()
                _history5   = load_history()
                _report_fmt5 = st.session_state.get("report_fmt_single", "기존 보고서")

                for _ov in _t5_overdue:
                    _names5 = _ov.get("client_names", [])
                    _since5 = _ov.get("since", "")
                    _until5 = _ov.get("until", "")
                    _pkey5  = _ov.get("period_key", "monthly")
                    for _cn5 in _names5:
                        _cl5 = next((c for c in _clients5 if c["name"] == _cn5), None)
                        if not _cl5:
                            st.error(f"❌ {_cn5}: 광고주 정보 없음")
                            continue
                        try:
                            with st.status(f"📡 {_cn5} 발송 중...", expanded=False):
                                _api5  = NaverAdAPI(_cl5["api_key"], _cl5["secret_key"], _cl5["customer_id"])
                                _data5 = _api5.fetch_report(_pkey5)
                                _rdate5 = datetime.now().strftime("%Y-%m-%d")
                                if _report_fmt5 == "월간보고서 V2":
                                    _v2e5 = fetch_v2_extra(_api5, _data5["since"], _data5["until"])
                                    _html5 = build_monthly_report_v2(_data5, _cn5, _rdate5, v2_extra=_v2e5)
                                else:
                                    _html5 = generate_html(_data5, _cn5, _rdate5)
                                send_report(
                                    to_email=_cl5["email"], client_name=_cn5,
                                    period=_pkey5, since=_since5, until=_until5,
                                    html_body=_html5, **_smtp_cfg5,
                                )
                            st.success(f"✅ {_cn5} → {_cl5['email']} 발송 완료")
                            _history5.append({
                                "client": _cn5, "email": _cl5["email"], "period": _pkey5,
                                "since": _since5, "until": _until5,
                                "keywords": _data5.get("total_keywords", 0),
                                "sent_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "status": "성공", "send_mode": "scheduled",
                            })
                        except Exception as _e5:
                            st.error(f"❌ {_cn5} 발송 실패: {_e5}")
                            _ov["error"] = str(_e5)[:200]

                    _ov["status"] = "completed"
                    _ov["sent_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

                save_schedule(_t5_sched)
                save_history(_history5)
                st.rerun()

        for _ti in sorted(_t5_pending, key=lambda x: x.get("scheduled_at", "")):
            _tia, _tib, _tic, _tid = st.columns([2.5, 2.5, 2, 1])
            _tia.write(", ".join(_ti.get("client_names", _ti.get("client_ids", []))))
            _tib.caption(f"{_ti.get('since','')} ~ {_ti.get('until','')}")
            _overdue_mark = " ⚠️ 기한초과" if _ti.get("scheduled_at","") <= _t5_now.strftime("%Y-%m-%dT%H:%M:%S") else ""
            _tic.caption(f"📅 {_ti.get('scheduled_at','')[:16]}{_overdue_mark}")
            if _tid.button("취소", key=f"cancel_{_ti['id']}"):
                _ti["status"] = "cancelled"
                save_schedule(_t5_sched)
                st.rerun()
    else:
        st.info("대기 중인 예약이 없습니다.")

    if _t5_done:
        st.divider()
        st.markdown("**📋 완료된 예약 이력**")
        import pandas as _pd5
        _t5_df = _pd5.DataFrame([{
            "광고주":   ", ".join(i.get("client_names", i.get("client_ids", []))),
            "기간":     f"{i.get('since','')} ~ {i.get('until','')}",
            "예약시각": i.get("scheduled_at", "")[:16],
            "상태":     i.get("status", ""),
            "오류":     i.get("error", ""),
        } for i in reversed(_t5_done)])
        st.dataframe(_t5_df, use_container_width=True, hide_index=True)
        if st.button("🗑️ 완료 이력 초기화", key="t5_clear"):
            _t5_sched["scheduled"] = _t5_pending
            save_schedule(_t5_sched)
            st.rerun()

    # 자동 정기발송 현황
    st.divider()
    st.subheader("🔄 자동 정기발송 현황")
    _t5_auto   = _t5_sched.get("auto_monthly", {})
    _t5_clients = load_clients()
    import calendar as _cal5
    from utils.sched_dates import shift_to_weekday
    _now5 = datetime.now()

    def _bi_next_date(cfg):
        _last = cfg.get("last_sent_date", "")
        if not _last:
            return None   # 첫 발송 대기
        try:
            return shift_to_weekday((datetime.strptime(_last, "%Y-%m-%d") + timedelta(days=14)).date())
        except Exception:
            return None

    def _mon_next_date(cfg):
        day = int(cfg.get("send_day", 5))
        def _mk(y, m):
            return datetime(y, m, min(day, _cal5.monthrange(y, m)[1])).date()
        if cfg.get("last_sent_month") == _now5.strftime("%Y-%m"):
            ny, nm = (_now5.year + 1, 1) if _now5.month == 12 else (_now5.year, _now5.month + 1)
            return shift_to_weekday(_mk(ny, nm))
        this = shift_to_weekday(_mk(_now5.year, _now5.month))
        return this if this >= _now5.date() else shift_to_weekday(_now5.date())

    def _next_send(cfg):
        hour = int(cfg.get("send_hour", 9))
        freq = cfg.get("freq", "monthly")
        cands = []
        if freq in ("biweekly", "both"):
            d = _bi_next_date(cfg)
            if d:
                cands.append(d)
        if freq in ("monthly", "both"):
            cands.append(_mon_next_date(cfg))
        if not cands:
            return "발송 시각 도달 시 (첫 발송 대기)"
        return min(cands).strftime("%Y-%m-%d") + f" {hour:02d}:00"

    _FREQ_LBL = {"monthly": "매월", "biweekly": "격주(2주)", "both": "매월+격주"}

    _t5_on = []
    for _tc in _t5_clients:
        _tcid = _tc.get("id") or _tc.get("name", "")
        _tcc  = (_t5_auto.get(_tcid) or _t5_auto.get(_tc.get("name", ""), {}))
        if _tcc.get("enabled"):
            _freq = _tcc.get("freq", "monthly")
            _hh   = _tcc.get("send_hour", 9)
            _sd   = _tcc.get("send_day", 5)
            if _freq == "both":
                _sched_txt = f"매월 {_sd}일 + 14일마다 {_hh:02d}:00"
                _last_txt  = f"월 {_tcc.get('last_sent_month','-') or '-'} / 격주 {_tcc.get('last_sent_date','-') or '-'}"
            elif _freq == "biweekly":
                _sched_txt = f"14일마다 {_hh:02d}:00"
                _last_txt  = _tcc.get("last_sent_date", "-") or "-"
            else:
                _sched_txt = f"매월 {_sd}일 {_hh:02d}:00"
                _last_txt  = _tcc.get("last_sent_month", "-") or "-"
            _t5_on.append({
                "광고주":       _tc["name"],
                "주기":         _FREQ_LBL.get(_freq, "매월"),
                "발송 스케줄":   _sched_txt,
                "다음 발송 예정": _next_send(_tcc),
                "마지막 발송":   _last_txt,
            })
    if _t5_on:
        import pandas as _pd5b
        st.dataframe(_pd5b.DataFrame(_t5_on), use_container_width=True, hide_index=True)
    else:
        st.info("자동 정기발송 설정된 광고주가 없습니다. 🔄 자동발송 탭에서 활성화하세요.")
