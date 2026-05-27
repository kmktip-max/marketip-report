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
    get_merged_settings, save_from_merged, save_one_alert,
    load_history, save_history,
    get_bizmoney_balance,
    send_kakao_alerttalk,
    TEMPLATE_CODE_FIRST, TEMPLATE_CODE_DEPLETED,
    TEMPLATE_FIRST, TEMPLATE_DEPLETED,
    _build_vars, run_check,
)

KST = timezone(timedelta(hours=9))

# ── 관리자 전용 ────────────────────────────────────────────────────────────────
if st.session_state.get("auth_type") != "admin":
    st.error("🔒 관리자만 접근 가능합니다.")
    st.stop()

st.title("비즈머니 잔액 알림 관리")
st.caption("광고주 정보(API 키·Customer ID)는 월간보고서 광고주 등록 데이터를 사용합니다.")

# ── 광고주 목록 로드 ───────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def _load_merged():
    return get_merged_settings()


def _reload():
    _load_merged.clear()
    st.rerun()


settings = _load_merged()

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
    "🧪 테스트 발송",
])


# ─── [탭1] 잔액 현황 ─────────────────────────────────────────────────────────
with t_status:
    col_btn, col_info = st.columns([2, 5])
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
    total  = len(settings)
    has_bal = [s for s in settings if s.get("last_bizmoney_balance") is not None]
    normal = sum(1 for s in has_bal
                 if s["last_bizmoney_balance"] > int(s.get("first_alert_amount", 50000)))
    warn   = sum(1 for s in has_bal
                 if 0 < s["last_bizmoney_balance"] <= int(s.get("first_alert_amount", 50000)))
    empty  = sum(1 for s in has_bal
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
    api_ok = [s for s in settings if s.get("api_access_license") and s.get("secret_key")]
    if api_ok:
        sel = st.selectbox(
            "광고주 선택",
            [s["advertiser_name"] for s in api_ok],
            key="indiv_sel",
        )
        if st.button("조회", key="btn_indiv"):
            s = next(x for x in api_ok if x["advertiser_name"] == sel)
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
                st.error(f"조회 실패: {res.get('error', '')}")
    else:
        st.info("API 키가 설정된 광고주가 없습니다. 월간보고서에서 광고주를 등록해주세요.")


# ─── [탭2] 알림 설정 ─────────────────────────────────────────────────────────
with t_alert_cfg:
    st.caption(
        "광고주명·Customer ID·API 키는 월간보고서 광고주 등록 정보를 사용합니다.  \n"
        "이 화면에서는 **알림 기준금액·연락처·활성 여부**만 설정합니다."
    )

    # 설정이 반영될 mutable 복사본
    editable = [dict(s) for s in settings]

    for idx, s in enumerate(editable):
        name = s.get("advertiser_name") or f"(광고주 #{idx+1})"
        cid  = s.get("customer_id", "—")
        has_api = bool(s.get("api_access_license") and s.get("secret_key"))
        api_icon = "🔑" if has_api else "⚠️"

        with st.expander(
            f"{api_icon} **{name}**  |  CID: {cid}",
            expanded=False,
        ):
            # 읽기 전용: 광고주 정보
            st.markdown(
                f"**광고주명:** {name}  \n"
                f"**Customer ID:** `{cid}`  \n"
                f"**API 키 상태:** {'설정됨 ✅' if has_api else '미설정 ⚠️ (월간보고서에서 등록 필요)'}"
            )
            st.divider()

            # 편집 가능: 알림 설정
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

            # 발송 플래그 리셋
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


# ─── [탭4] 테스트 발송 ────────────────────────────────────────────────────────
with t_test:
    st.markdown("### 테스트 알림톡 발송")
    st.caption("Dry-run으로 내용을 확인하거나, 지정 번호로 실제 테스트 발송합니다.")

    api_ok = [s for s in settings if s.get("api_access_license") and s.get("secret_key")]
    all_names = [s["advertiser_name"] for s in settings]

    if not all_names:
        st.info("월간보고서에서 광고주를 먼저 등록해주세요.")
    else:
        # ── 잔액 조회 테스트 ─────────────────────────────────────────────────
        st.markdown("**잔액 조회 테스트**")
        if api_ok:
            sel_bal = st.selectbox(
                "광고주 선택",
                [s["advertiser_name"] for s in api_ok],
                key="test_bal_sel",
            )
            if st.button("잔액 조회", key="btn_bal_test"):
                s = next(x for x in api_ok if x["advertiser_name"] == sel_bal)
                with st.spinner("조회 중..."):
                    res = get_bizmoney_balance(
                        s["customer_id"], s["api_access_license"], s["secret_key"]
                    )
                if res["status"] == "success":
                    st.success(f"비즈머니 잔액: **{res['balance']:,}원**")
                else:
                    st.error(f"실패: {res.get('error', '')}")
        else:
            st.info("API 키가 설정된 광고주가 없습니다.")

        st.divider()

        # ── 알림톡 테스트 발송 ────────────────────────────────────────────────
        st.markdown("**알림톡 테스트 발송**")
        sel_name    = st.selectbox("광고주 선택", all_names, key="test_adv")
        s_test      = next((x for x in settings if x["advertiser_name"] == sel_name), {})
        test_phone  = st.text_input(
            "테스트 발송 번호",
            value=s_test.get("manager_phone", ""),
            placeholder="010-0000-0000",
            key="test_phone",
        )
        alert_type  = st.radio(
            "알림 단계", ["1차 경고", "2차 소진"], horizontal=True, key="test_type"
        )
        test_bal    = st.number_input(
            "테스트 잔액(원)", value=30000, step=1000, key="test_bal_val"
        )
        dry_run_on  = st.checkbox("Dry-run (실제 발송 안 함)", value=True, key="test_dry")

        is_first  = alert_type == "1차 경고"
        threshold = int(s_test.get("first_alert_amount", 50000) if is_first
                        else s_test.get("second_alert_amount", 0))
        vars_     = _build_vars(s_test, test_bal, threshold)
        tmpl      = TEMPLATE_FIRST if is_first else TEMPLATE_DEPLETED
        preview   = tmpl
        for k, v in vars_.items():
            preview = preview.replace(f"#{{{k}}}", str(v))

        st.markdown("**메시지 미리보기**")
        st.code(preview, language=None)

        if st.button("📤 테스트 발송", type="primary", key="btn_test_send"):
            if not test_phone.strip():
                st.error("발송 번호를 입력해주세요.")
            else:
                tcode = TEMPLATE_CODE_FIRST if is_first else TEMPLATE_CODE_DEPLETED
                with st.spinner("실행 중..."):
                    result = send_kakao_alerttalk(
                        test_phone.strip(), tcode, vars_, dry_run=dry_run_on
                    )
                status = result.get("status")
                if status in ("success", "dry_run"):
                    st.success(
                        "✅ Dry-run 완료 (실제 발송 안 됨)" if dry_run_on
                        else "✅ 알림톡 발송 성공"
                    )
                elif status == "skipped":
                    st.warning(f"발송 건너뜀: {result.get('error', '')}")
                else:
                    st.error(f"발송 실패: {result.get('error', '')}")
                st.json(result)

        st.divider()

        # ── 전체 알림 체크 ────────────────────────────────────────────────────
        st.markdown("**전체 알림 체크 실행**")
        dry2 = st.checkbox("Dry-run", value=True, key="full_dry")
        if st.button("전체 알림 체크 실행", key="btn_full_check"):
            with st.spinner("실행 중..."):
                results = run_check(dry_run=dry2)
            if not results:
                st.info("처리된 광고주가 없습니다. (API 키 미설정 또는 알림 비활성)")
            for r in results:
                cid = r["customer_id"]
                bal = r.get("balance")
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
