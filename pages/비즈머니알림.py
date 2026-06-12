"""
비즈머니 잔액 감시 & 알림톡 관리 (관리자 전용)

광고주 정보(API 키 등)는 월간보고서 광고주 등록 데이터를 재사용합니다.
이 페이지에서는 알림 설정(기준금액·연락처·발송 플래그)만 관리합니다.
"""

import os
import sys
from datetime import timezone, timedelta

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bizmoney_alert import (
    NAVER_BASE,
    get_merged_settings, save_from_merged, save_one_alert,
    load_history, save_history,
    get_bizmoney_balance,
    get_solapi_config_status,
    send_kakao_alerttalk,
    check_template_vars,
    TEMPLATE_CODE_FIRST, TEMPLATE_CODE_DEPLETED,
    TEMPLATE_FIRST, TEMPLATE_DEPLETED,
    _build_vars, run_check,
)

KST = timezone(timedelta(hours=9))

_is_admin = st.session_state.get("auth_type") == "admin"
_username = st.session_state.get("auth_username", "")

from auth import feature_access_guard
feature_access_guard("bizmoney_alert", "비즈머니 알림")

st.title("비즈머니 잔액 알림 관리")
st.caption("광고주 정보(API 키·Customer ID)는 월간보고서 광고주 등록 데이터를 사용합니다.")

with st.expander("📖 이용안내 — 처음 사용하시는 분께", expanded=False):
    st.markdown("""
**순서대로 따라하면 바로 시작할 수 있어요!**

**① 광고주 등록 (사전 준비)**
먼저 **월간보고서** 페이지에서 광고주를 등록해야 합니다 (API 키·Customer ID 포함)
→ 비즈머니 잔액 조회는 광고주 API 키로 이루어집니다

**② 알림 기준금액 설정**
이 페이지에서 광고주 선택 → **잔액 알림 기준금액** 입력 (예: 100,000원)
→ 잔액이 이 금액 이하로 떨어지면 알림이 발송됩니다

**③ 알림 연락처 등록**
알림을 받을 **카카오톡 연결 전화번호** 입력
(솔라피 카카오 알림톡 서비스 연동 필요 — 관리자에게 문의)

**④ 알림 활성화**
**[알림 활성화]** 토글을 ON으로 설정 → 저장

**⑤ 자동 모니터링 시작**
스케줄러가 주기적으로 잔액을 확인하고, 기준 이하 시 카카오 알림톡을 자동 발송합니다
발송 내역은 **[알림 이력]** 탭에서 확인 가능

> 💡 **팁** : 광고비 소진을 놓쳐 광고가 중단되는 상황을 예방할 수 있어요.
    """)

# ── 광고주 목록 로드 ───────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def _load_merged():
    return get_merged_settings()


def _reload():
    _load_merged.clear()
    st.rerun()


_all_settings = _load_merged()
# 관리자는 전체, 그 외 계정은 본인 소유 광고주만 표시
settings = _all_settings if _is_admin else [
    s for s in _all_settings if s.get("owner", "") == _username
]

if not settings:
    st.warning(
        "등록된 광고주가 없습니다. "
        "먼저 **월간보고서** 페이지에서 광고주를 등록해주세요."
    )
    st.stop()

# ── 탭 구성 ────────────────────────────────────────────────────────────────────
t_status, t_alert_cfg, t_history, t_test = st.tabs([
    "📊 잔액 현황",
    "⚙️ 알림 설정",
    "📋 발송 이력",
    "🧪 테스트 도구",
])


# ─── [탭1] 잔액 현황 ─────────────────────────────────────────────────────────
with t_status:
    col_btn, col_btn2, col_info = st.columns([2, 2, 3])
    with col_btn2:
        if st.button("📣 수동 알림 체크 실행", use_container_width=True,
                     help="잔액 조회 + 기준 미달 시 알림톡 실제 발송"):
            with st.spinner("잔액 확인 및 알림 발송 중..."):
                results = run_check(dry_run=False)
            for r in results:
                cid  = r.get("customer_id", "")
                bal  = r.get("balance", 0)
                acts = r.get("actions", [])
                # balance_check 제외 — 실제 알림 발송 액션만 필터
                alert_acts = [a for a in acts if a.get("type") not in ("balance_check", "reset")]
                sent    = [a for a in alert_acts if a.get("status") == "success"]
                skipped = [a for a in alert_acts if a.get("status") == "skipped"]
                errs    = [a for a in alert_acts if a.get("status") == "failed"]
                if sent:
                    detail = sent[0].get("detail", "")
                    st.success(f"✅ {cid}: 알림톡 발송 완료 (잔액 {bal:,}원) — {detail}")
                elif errs:
                    st.error(f"❌ {cid}: 발송 실패 — {errs[0].get('detail','')}")
                elif skipped:
                    st.warning(f"⏭️ {cid}: 오늘 이미 발송됨 (잔액 {bal:,}원)")
                else:
                    # 알림 조건 미충족 (잔액이 기준치 이상 또는 플래그 설정됨)
                    reset_act = [a for a in acts if a.get("type") == "reset"]
                    reset_msg = " (충전 감지 → 플래그 리셋)" if reset_act else ""
                    st.info(f"ℹ️ {cid}: 잔액 {bal:,}원 — 기준치 이상 또는 이미 발송된 상태{reset_msg}")
    with col_btn:
        if st.button("🔄 전체 잔액 즉시 조회", type="primary", use_container_width=True):
            with st.spinner("잔액 조회 중..."):
                fresh = get_merged_settings()
                for s in fresh:
                    if not s.get("api_access_license") or not s.get("secret_key"):
                        continue
                    res = get_bizmoney_balance(
                        s["customer_id"],
                        s["api_access_license"],
                        s["secret_key"],
                    )
                    if res["status"] == "success":
                        s["last_bizmoney_balance"] = res["balance"]
                        s["last_checked_at"]       = res["checked_at"]
                save_from_merged(fresh)
            st.success("조회 완료")
            _reload()

    # 요약 메트릭
    total   = len(settings)
    has_bal = [s for s in settings if s.get("last_bizmoney_balance") is not None]
    normal  = sum(1 for s in has_bal
                  if s["last_bizmoney_balance"] > int(s.get("first_alert_amount", 50000)))
    warn    = sum(1 for s in has_bal
                  if 0 < s["last_bizmoney_balance"] <= int(s.get("first_alert_amount", 50000)))
    empty   = sum(1 for s in has_bal
                  if s["last_bizmoney_balance"] <= int(s.get("second_alert_amount", 0)))

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("전체 광고주",  f"{total}개")
    m2.metric("🟢 정상",      f"{normal}개")
    m3.metric("🟠 1차 경고",  f"{warn}개")
    m4.metric("🔴 소진",      f"{empty}개")
    m5.metric("미조회",       f"{total - len(has_bal)}개")

    st.divider()

    # 현황 테이블
    rows = []
    for s in settings:
        bal       = s.get("last_bizmoney_balance")
        first_amt = int(s.get("first_alert_amount",  50000))
        sec_amt   = int(s.get("second_alert_amount", 0))

        if bal is None:
            icon = "⬜"
        elif bal <= sec_amt:
            icon = "🔴"
        elif bal <= first_amt:
            icon = "🟠"
        else:
            icon = "🟢"

        checked = (s.get("last_checked_at") or "—")[:16].replace("T", " ")
        rows.append({
            "":            icon,
            "광고주명":    s.get("advertiser_name", ""),
            "Customer ID": s.get("customer_id", ""),
            "현재 잔액":   f"{bal:,}원" if bal is not None else "미조회",
            "1차 기준":    f"{first_amt:,}원",
            "알림":        "ON" if s.get("alert_enabled") else "OFF",
            "1차 발송":    "✅" if s.get("first_alert_sent")  else "—",
            "2차 발송":    "✅" if s.get("second_alert_sent") else "—",
            "최종 조회":   checked,
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # 개별 즉시 조회
    st.divider()
    st.markdown("**개별 즉시 조회**")
    api_ok_tab1 = [s for s in settings if s.get("api_access_license") and s.get("secret_key")]
    if api_ok_tab1:
        sel = st.selectbox(
            "광고주 선택",
            [s["advertiser_name"] for s in api_ok_tab1],
            key="indiv_sel",
        )
        if st.button("조회", key="btn_indiv"):
            s = next(x for x in api_ok_tab1 if x["advertiser_name"] == sel)
            with st.spinner(f"{sel} 잔액 조회 중..."):
                res = get_bizmoney_balance(
                    s["customer_id"], s["api_access_license"], s["secret_key"]
                )
            if res["status"] == "success":
                st.success(f"비즈머니 잔액: **{res['balance']:,}원**")
                s["last_bizmoney_balance"] = res["balance"]
                s["last_checked_at"]       = res["checked_at"]
                save_one_alert(s)
                _reload()
            else:
                sc  = res.get("status_code", "")
                ep  = res.get("endpoint", "")
                err = res.get("error", "")
                st.error(f"조회 실패 (HTTP {sc})")
                st.code(err, language=None)
                if ep:
                    st.caption(f"호출: `GET {NAVER_BASE}{ep}`")
    else:
        st.info("API 키가 설정된 광고주가 없습니다. 월간보고서에서 광고주를 등록해주세요.")


# ─── [탭2] 알림 설정 ─────────────────────────────────────────────────────────
with t_alert_cfg:
    st.caption(
        "광고주명·Customer ID·API 키는 월간보고서 광고주 등록 정보를 사용합니다.  \n"
        "이 화면에서는 **알림 기준금액·연락처·활성 여부**만 설정합니다."
    )

    editable = [dict(s) for s in settings]

    for idx, s in enumerate(editable):
        name    = s.get("advertiser_name") or f"(광고주 #{idx+1})"
        cid     = s.get("customer_id", "—")
        has_api = bool(s.get("api_access_license") and s.get("secret_key"))
        api_icon = "🔑" if has_api else "⚠️"

        with st.expander(
            f"{api_icon} **{name}**  |  CID: {cid}",
            expanded=False,
        ):
            st.markdown(
                f"**광고주명:** {name}  \n"
                f"**Customer ID:** `{cid}`  \n"
                f"**API 키 상태:** {'설정됨 ✅' if has_api else '미설정 ⚠️ (월간보고서에서 등록 필요)'}"
            )
            st.divider()

            c1, c2 = st.columns(2)
            with c1:
                s["alert_enabled"] = st.checkbox(
                    "알림 활성",
                    value=bool(s.get("alert_enabled", True)),
                    key=f"bm_en_{idx}",
                )
                s["first_alert_amount"] = st.number_input(
                    "1차 알림 기준금액(원)",
                    min_value=0, step=10000,
                    value=int(s.get("first_alert_amount", 50000)),
                    key=f"bm_fa_{idx}",
                )
                s["second_alert_amount"] = st.number_input(
                    "2차 알림 기준금액(원) — 보통 0원(소진)",
                    min_value=0, step=1000,
                    value=int(s.get("second_alert_amount", 0)),
                    key=f"bm_sa_{idx}",
                )

            with c2:
                s["advertiser_phone"] = st.text_input(
                    "광고주 연락처",
                    value=s.get("advertiser_phone", ""),
                    placeholder="010-0000-0000",
                    key=f"bm_aph_{idx}",
                )
                s["manager_name"] = st.text_input(
                    "담당자명",
                    value=s.get("manager_name", ""),
                    key=f"bm_mnm_{idx}",
                )
                s["manager_phone"] = st.text_input(
                    "담당자 연락처",
                    value=s.get("manager_phone", ""),
                    placeholder="010-0000-0000",
                    key=f"bm_mph_{idx}",
                )
                s["memo"] = st.text_input(
                    "메모",
                    value=s.get("memo", ""),
                    key=f"bm_memo_{idx}",
                )

            fa = s.get("first_alert_sent",  False)
            sa = s.get("second_alert_sent", False)
            if fa or sa:
                st.caption(
                    f"발송 플래그 — 1차: {'✅ 발송됨' if fa else '미발송'} | "
                    f"2차: {'✅ 발송됨' if sa else '미발송'}"
                )
                if st.button("🔄 플래그 초기화 (재발송 허용)", key=f"bm_rst_{idx}"):
                    s["first_alert_sent"]  = False
                    s["second_alert_sent"] = False
                    save_one_alert(s)
                    st.success("초기화 완료")
                    _reload()

            if st.button("💾 저장", key=f"bm_sv_{idx}", type="primary"):
                save_one_alert(s)
                st.success(f"✅ {name} 저장 완료")
                _reload()

    st.divider()
    if st.button("💾 전체 저장", use_container_width=True, key="bm_save_all"):
        save_from_merged(editable)
        st.success("전체 저장 완료")
        _reload()

    st.divider()
    st.markdown("#### 알림톡 템플릿 ID 설정")
    st.caption("Solapi 콘솔 → 카카오 알림톡 → 템플릿 관리에서 확인한 ID를 입력하세요.")
    try:
        from notifications import get_notify_config as _gnc, save_notify_config as _snc
        _nc = _gnc()
        _tc1 = st.text_input(
            "1차 알림 (잔액 부족) 템플릿 ID",
            value=_nc.get("bm_template_first", TEMPLATE_CODE_FIRST),
            key="cfg_tc1",
        )
        _tc2 = st.text_input(
            "2차 알림 (소진) 템플릿 ID",
            value=_nc.get("bm_template_depleted", TEMPLATE_CODE_DEPLETED),
            key="cfg_tc2",
        )
        if st.button("💾 템플릿 ID 저장", key="btn_tc_save"):
            _nc["bm_template_first"]    = _tc1.strip()
            _nc["bm_template_depleted"] = _tc2.strip()
            _snc(_nc)
            st.success("✅ 저장 완료")
    except Exception as _e:
        st.warning(f"notifications 모듈 로드 실패: {_e}")


# ─── [탭3] 발송 이력 ─────────────────────────────────────────────────────────
with t_history:
    history = load_history()

    if not history:
        st.info("발송 이력이 없습니다.")
    else:
        rows = []
        for h in reversed(history[:200]):
            rows.append({
                "발송 시각":    h.get("sent_at", "")[:16].replace("T", " "),
                "광고주":       h.get("advertiser_name", ""),
                "알림 단계":    "1차 경고" if h.get("alert_type") == "first" else "소진",
                "잔액(원)":     f"{h.get('balance', 0):,}",
                "기준금액(원)": f"{h.get('threshold_amount', 0):,}",
                "연락처":       h.get("phone", ""),
                "상태":         h.get("status", ""),
                "오류":         h.get("error_message", ""),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption(f"최근 {len(rows)}건 표시 (전체 {len(history)}건)")

        if st.button("🗑️ 이력 전체 삭제", type="secondary"):
            save_history([])
            st.success("이력 삭제 완료")
            st.rerun()


# ─── [탭4] 테스트 도구 ───────────────────────────────────────────────────────
with t_test:
    st.markdown("### 🧪 테스트 도구")

    # ── B. SOLAPI 설정 상태 ──────────────────────────────────────────────────
    st.markdown("#### B. 알림톡 설정 상태 (SOLAPI)")
    solapi_status = get_solapi_config_status()
    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric("SOLAPI_API_KEY",    "✅ 설정됨" if solapi_status["SOLAPI_API_KEY"]    else "❌ 없음")
    sc2.metric("SOLAPI_API_SECRET", "✅ 설정됨" if solapi_status["SOLAPI_API_SECRET"] else "❌ 없음")
    sc3.metric("SOLAPI_SENDER_ID",  "✅ 설정됨" if solapi_status["SOLAPI_SENDER_ID"]  else "❌ 없음")
    sc4.metric("SOLAPI_KAKAO_PF_ID","✅ 설정됨" if solapi_status["SOLAPI_KAKAO_PF_ID"] else "⚠️ 미설정(SMS 발송)")

    # 알림톡은 KEY+SECRET+SENDER 3개 필수 / PF_ID 없으면 SMS fallback
    solapi_ready = (solapi_status["SOLAPI_API_KEY"]
                    and solapi_status["SOLAPI_API_SECRET"]
                    and solapi_status["SOLAPI_SENDER_ID"])
    kakao_ready  = solapi_ready and solapi_status["SOLAPI_KAKAO_PF_ID"]

    if not solapi_ready:
        st.warning("SOLAPI 키가 미설정 상태입니다. 알림톡 실제 발송은 skipped 처리됩니다.")
        with st.expander("⚙️ secrets.toml 설정 방법"):
            st.code(
                'SOLAPI_API_KEY    = "솔라피_API_KEY"\n'
                'SOLAPI_API_SECRET = "솔라피_API_SECRET"\n'
                'SOLAPI_SENDER_ID  = "010-XXXX-XXXX"   # 솔라피 인증 발신번호\n'
                'SOLAPI_KAKAO_PF_ID = "_카카오채널ID"   # 알림톡용 (선택)',
                language="toml",
            )
    elif kakao_ready:
        st.success("✅ SOLAPI + 카카오채널 설정 완료 — 알림톡 발송 가능")
    else:
        st.info("ℹ️ SOLAPI 설정됨 / 카카오채널(SOLAPI_KAKAO_PF_ID) 미설정 → SMS로 발송됩니다.")

    st.divider()

    # ── A. 잔액 조회 테스트 ──────────────────────────────────────────────────
    st.markdown("#### A. 잔액 조회 테스트")

    api_ok  = [s for s in settings if s.get("api_access_license") and s.get("secret_key")]
    all_names = [s["advertiser_name"] for s in settings]

    bal_mode = st.radio(
        "잔액 입력 방식",
        ["실제 API 조회", "테스트 잔액 직접 입력 (mock)"],
        horizontal=True,
        key="bal_mode",
    )

    # 세션 상태로 잔액 값을 유지 (API fetch → 하단 발송 섹션에서 재사용)
    if "bm_test_bal" not in st.session_state:
        st.session_state["bm_test_bal"] = 30000

    if bal_mode == "실제 API 조회":
        if api_ok:
            sel_bal = st.selectbox(
                "광고주 선택",
                [s["advertiser_name"] for s in api_ok],
                key="test_bal_sel",
            )
            if st.button("잔액 조회", key="btn_bal_test"):
                s_bal = next(x for x in api_ok if x["advertiser_name"] == sel_bal)
                with st.spinner("조회 중..."):
                    res = get_bizmoney_balance(
                        s_bal["customer_id"],
                        s_bal["api_access_license"],
                        s_bal["secret_key"],
                    )
                if res["status"] == "success":
                    st.session_state["bm_test_bal"] = res["balance"]
                    st.success(f"비즈머니 잔액: **{res['balance']:,}원** (하단 발송 테스트에 자동 반영)")
                else:
                    sc  = res.get("status_code", "")
                    ep  = res.get("endpoint", "")
                    err = res.get("error", "알 수 없는 오류")
                    st.error(f"조회 실패 — HTTP {sc}")
                    st.code(err, language=None)
                    if ep:
                        st.caption(f"호출 경로: `GET {NAVER_BASE}{ep}`")
                    st.info(
                        "API 잔액 조회 실패 시 아래 '테스트 잔액 직접 입력' 방식으로 "
                        "알림 조건 판단 및 Dry-run 테스트가 가능합니다."
                    )
        else:
            st.info("API 키가 설정된 광고주가 없습니다. 월간보고서에서 광고주를 등록해주세요.")

    else:  # mock
        mock_val = st.number_input(
            "테스트 잔액 입력(원)",
            min_value=0, step=1000,
            value=st.session_state["bm_test_bal"],
            key="mock_bal_input",
        )
        st.session_state["bm_test_bal"] = int(mock_val)
        st.info(f"Mock 잔액 **{int(mock_val):,}원** — 실제 API 호출 없이 알림 조건 테스트합니다.")

    st.divider()

    # ── C. 알림톡 테스트 발송 ────────────────────────────────────────────────
    st.markdown("#### C. 알림톡 테스트 발송")

    if not all_names:
        st.info("월간보고서에서 광고주를 먼저 등록해주세요.")
    else:
        sel_name = st.selectbox("광고주 선택", all_names, key="test_adv")
        s_test   = next((x for x in settings if x["advertiser_name"] == sel_name), {})

        test_phone = st.text_input(
            "테스트 발송 번호",
            value=s_test.get("manager_phone", ""),
            placeholder="010-0000-0000",
            key="test_phone",
        )
        alert_type = st.radio(
            "알림 단계", ["1차 경고", "2차 소진"], horizontal=True, key="test_type"
        )

        # 현재 테스트 잔액 표시
        test_bal  = st.session_state["bm_test_bal"]
        st.caption(f"사용할 테스트 잔액: **{test_bal:,}원** (A 섹션에서 변경)")

        # 알림 조건 판단 표시
        first_amt  = int(s_test.get("first_alert_amount",  50000))
        second_amt = int(s_test.get("second_alert_amount", 0))
        if test_bal <= second_amt:
            st.warning(f"🔴 잔액 {test_bal:,}원 ≤ 소진 기준 {second_amt:,}원 → **2차 알림 대상**")
        elif test_bal <= first_amt:
            st.warning(f"🟠 잔액 {test_bal:,}원 ≤ 1차 기준 {first_amt:,}원 → **1차 알림 대상**")
        else:
            st.success(f"🟢 잔액 {test_bal:,}원 > 1차 기준 {first_amt:,}원 → 정상 (알림 불필요)")

        # 템플릿 ID 입력 (카카오채널 설정된 경우만 의미 있음)
        is_first  = alert_type == "1차 경고"
        if kakao_ready:
            try:
                from notifications import get_notify_config as _gnc_t
                _nc_t = _gnc_t()
                default_tcode = (
                    _nc_t.get("bm_template_first", TEMPLATE_CODE_FIRST) if is_first
                    else _nc_t.get("bm_template_depleted", TEMPLATE_CODE_DEPLETED)
                )
            except Exception:
                default_tcode = TEMPLATE_CODE_FIRST if is_first else TEMPLATE_CODE_DEPLETED
            tcode = st.text_input(
                "Solapi 템플릿 ID",
                value=default_tcode,
                placeholder="Solapi에 등록된 실제 템플릿 ID 입력",
                key="test_tcode",
                help="Solapi 콘솔 → 카카오 알림톡 → 템플릿 관리에서 확인 / ⚙️ 알림 설정 탭에서 저장 가능",
            )
        else:
            tcode = TEMPLATE_FIRST if is_first else TEMPLATE_DEPLETED  # SMS용 본문
            st.caption("카카오채널 미설정 → SMS 본문으로 발송됩니다.")

        # dry-run 옵션 (SOLAPI 미설정 시 강제 dry-run)
        dry_run_on = st.checkbox(
            "Dry-run (실제 발송 안 함)",
            value=(not solapi_ready),
            key="test_dry",
            disabled=(not solapi_ready),
        )
        if not solapi_ready:
            st.caption("SOLAPI 미설정 → 자동으로 Dry-run 처리됩니다.")

        # 메시지 미리보기
        threshold = first_amt if is_first else second_amt
        vars_     = _build_vars(s_test, test_bal, threshold)
        tmpl      = TEMPLATE_FIRST if is_first else TEMPLATE_DEPLETED
        preview   = tmpl
        for k, v in vars_.items():
            preview = preview.replace(f"#{{{k}}}", str(v))

        st.markdown("**메시지 미리보기**")
        st.code(preview, language=None)

        # 변수 누락 확인
        missing_vars = check_template_vars(tmpl, vars_)
        if missing_vars:
            st.error(
                "⚠️ 누락된 변수 — 발송 불가: "
                + ", ".join(f"#{{{v}}}" for v in missing_vars)
            )

        if st.button("📤 테스트 발송", type="primary", key="btn_test_send",
                     disabled=bool(missing_vars)):
            effective_dry = dry_run_on or not solapi_ready
            if not test_phone.strip():
                st.error("발송 번호를 입력해주세요.")
            elif kakao_ready and not tcode.strip():
                st.error("템플릿 ID를 입력해주세요.")
            else:
                with st.spinner("실행 중..."):
                    result = send_kakao_alerttalk(
                        test_phone.strip(), tcode.strip(), vars_, dry_run=effective_dry
                    )
                status = result.get("status")
                if status == "dry_run":
                    st.success("✅ Dry-run 완료 — 실제 발송 안 됨")
                    _pt = result.get("preview_text", "")
                    if _pt and _pt != tcode.strip():
                        st.markdown("**치환된 메시지:**")
                        st.code(_pt, language=None)
                    st.caption(
                        f"수신번호: `{result.get('phone', '')}`  |  "
                        f"변수 {len(result.get('vars', {}))}개 적용"
                    )
                elif status == "success":
                    st.success("✅ 발송 성공")
                    st.json(result)
                elif status == "skipped":
                    st.warning(f"발송 건너뜀: {result.get('error', '')}")
                    st.json(result)
                else:
                    st.error(f"발송 실패: {result.get('error', '')}")
                    st.json(result)

    st.divider()

    # ── 전체 알림 체크 ────────────────────────────────────────────────────────
    st.markdown("#### 전체 알림 체크 실행")
    dry2 = st.checkbox("Dry-run", value=True, key="full_dry")
    if st.button("전체 알림 체크 실행", key="btn_full_check"):
        with st.spinner("실행 중..."):
            results = run_check(dry_run=dry2)
        if not results:
            st.info("처리된 광고주가 없습니다. (API 키 미설정 또는 알림 비활성)")
        for r in results:
            cid  = r["customer_id"]
            bal  = r.get("balance")
            name = next(
                (s["advertiser_name"] for s in settings if s["customer_id"] == cid),
                cid,
            )
            st.markdown(
                f"**{name}** — 잔액: {f'{bal:,}원' if bal is not None else '조회 실패'}"
            )
            for a in r.get("actions", []):
                if a.get("type") == "balance_check":
                    continue
                icon = (
                    "✅" if a.get("status") in ("success", "dry_run")
                    else "⏭️" if a.get("status") == "skipped"
                    else "❌"
                )
                st.caption(f"  {icon} [{a.get('type')}] {a.get('detail', '')}")
        _reload()
