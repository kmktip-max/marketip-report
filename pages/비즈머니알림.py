"""
비즈머니 잔액 감시 & 알림톡 관리 페이지 (관리자 전용)
"""

import os
import sys
from datetime import timezone, timedelta

import streamlit as st
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bizmoney_alert import (
    load_settings, save_settings, load_history,
    get_bizmoney_balance,
    send_kakao_alerttalk, default_setting,
    TEMPLATE_CODE_FIRST, TEMPLATE_CODE_DEPLETED,
    TEMPLATE_FIRST, TEMPLATE_DEPLETED,
)

KST = timezone(timedelta(hours=9))

# ── 관리자 전용 ────────────────────────────────────────────────────────────────
if st.session_state.get("auth_type") != "admin":
    st.error("🔒 관리자만 접근 가능합니다.")
    st.stop()

st.title("비즈머니 잔액 알림 관리")

# ── 탭 구성 ────────────────────────────────────────────────────────────────────
t_status, t_settings, t_history, t_test = st.tabs([
    "📊 잔액 현황",
    "⚙️ 광고주 설정",
    "📋 발송 이력",
    "🧪 테스트 발송",
])


# ─── 잔액 현황 탭 ──────────────────────────────────────────────────────────────
with t_status:
    settings = load_settings()

    if not settings:
        st.info("설정된 광고주가 없습니다. '광고주 설정' 탭에서 추가해주세요.")
    else:
        # 즉시 잔액 조회 버튼
        if st.button("🔄 전체 잔액 즉시 조회", type="primary"):
            with st.spinner("잔액 조회 중..."):
                updated = []
                for s in settings:
                    if not s.get("api_access_license") or not s.get("secret_key"):
                        updated.append(s)
                        continue
                    res = get_bizmoney_balance(
                        s["customer_id"],
                        s["api_access_license"],
                        s["secret_key"],
                    )
                    if res["status"] == "success":
                        s["last_bizmoney_balance"] = res["balance"]
                        s["last_checked_at"]       = res["checked_at"]
                    updated.append(s)
                save_settings(updated)
                settings = updated
            st.success("조회 완료")
            st.rerun()

        # 현황 테이블
        rows = []
        for s in settings:
            bal = s.get("last_bizmoney_balance")
            first_amt  = int(s.get("first_alert_amount",  50000))
            second_amt = int(s.get("second_alert_amount", 0))

            if bal is None:
                status_icon = "⬜"
            elif bal <= second_amt:
                status_icon = "🔴"
            elif bal <= first_amt:
                status_icon = "🟠"
            else:
                status_icon = "🟢"

            checked = s.get("last_checked_at", "-")
            if checked and checked != "-":
                try:
                    checked = checked[:16].replace("T", " ")
                except Exception:
                    pass

            rows.append({
                "상태":       status_icon,
                "광고주명":   s.get("advertiser_name", ""),
                "Customer ID": s.get("customer_id", ""),
                "현재 잔액":  f"{bal:,}원" if bal is not None else "미조회",
                "1차 기준":   f"{first_amt:,}원",
                "알림 활성":  "✅" if s.get("alert_enabled") else "❌",
                "1차 발송":   "✅" if s.get("first_alert_sent")  else "—",
                "2차 발송":   "✅" if s.get("second_alert_sent") else "—",
                "최종 조회":  checked,
            })

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # 요약 메트릭
        total  = len(settings)
        normal = sum(1 for s in settings
                     if (s.get("last_bizmoney_balance") or 0) > int(s.get("first_alert_amount", 50000)))
        warn   = sum(1 for s in settings
                     if 0 < (s.get("last_bizmoney_balance") or -1) <= int(s.get("first_alert_amount", 50000)))
        empty  = sum(1 for s in settings
                     if (s.get("last_bizmoney_balance") is not None)
                     and (s.get("last_bizmoney_balance") or 0) <= int(s.get("second_alert_amount", 0)))

        st.divider()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("전체",     f"{total}개")
        m2.metric("🟢 정상",  f"{normal}개")
        m3.metric("🟠 경고",  f"{warn}개")
        m4.metric("🔴 소진",  f"{empty}개")

        # 개별 즉시 조회
        st.divider()
        st.markdown("**개별 즉시 조회**")
        names = [s["advertiser_name"] for s in settings if s.get("api_access_license")]
        if names:
            sel_name = st.selectbox("광고주 선택", names, key="indiv_check")
            if st.button("조회", key="btn_indiv"):
                s = next(x for x in settings if x["advertiser_name"] == sel_name)
                with st.spinner(f"{sel_name} 잔액 조회 중..."):
                    res = get_bizmoney_balance(
                        s["customer_id"], s["api_access_license"], s["secret_key"]
                    )
                if res["status"] == "success":
                    st.success(f"비즈머니 잔액: **{res['balance']:,}원**")
                    s["last_bizmoney_balance"] = res["balance"]
                    s["last_checked_at"]       = res["checked_at"]
                    save_settings(settings)
                else:
                    st.error(f"조회 실패: {res.get('error', '')}")


# ─── 광고주 설정 탭 ─────────────────────────────────────────────────────────────
with t_settings:
    settings = load_settings()

    col_add, col_del = st.columns([3, 1])
    with col_add:
        if st.button("➕ 광고주 추가", type="primary"):
            settings.append(default_setting())
            save_settings(settings)
            st.rerun()

    st.divider()

    for idx, s in enumerate(settings):
        lbl = s.get("advertiser_name") or f"(미입력) #{idx+1}"
        with st.expander(f"**{lbl}**  |  CID: {s.get('customer_id', '—')}", expanded=False):
            c1, c2 = st.columns(2)

            with c1:
                s["advertiser_name"] = st.text_input(
                    "광고주명", s.get("advertiser_name", ""), key=f"bm_nm_{idx}")
                s["customer_id"] = st.text_input(
                    "Customer ID", s.get("customer_id", ""), key=f"bm_cid_{idx}")
                s["api_access_license"] = st.text_input(
                    "API Access License", s.get("api_access_license", ""),
                    type="password", key=f"bm_api_{idx}")
                s["secret_key"] = st.text_input(
                    "Secret Key", s.get("secret_key", ""),
                    type="password", key=f"bm_sk_{idx}")
                s["memo"] = st.text_input(
                    "메모", s.get("memo", ""), key=f"bm_memo_{idx}")

            with c2:
                s["manager_name"] = st.text_input(
                    "담당자명", s.get("manager_name", ""), key=f"bm_mnm_{idx}")
                s["manager_phone"] = st.text_input(
                    "담당자 연락처", s.get("manager_phone", ""),
                    placeholder="010-0000-0000", key=f"bm_mph_{idx}")
                s["advertiser_phone"] = st.text_input(
                    "광고주 연락처", s.get("advertiser_phone", ""),
                    placeholder="010-0000-0000", key=f"bm_aph_{idx}")
                s["first_alert_amount"] = st.number_input(
                    "1차 알림 기준금액(원)", min_value=0, step=10000,
                    value=int(s.get("first_alert_amount", 50000)), key=f"bm_fa_{idx}")
                s["second_alert_amount"] = st.number_input(
                    "2차 알림 기준금액(원)", min_value=0, step=1000,
                    value=int(s.get("second_alert_amount", 0)), key=f"bm_sa_{idx}")
                s["alert_enabled"] = st.checkbox(
                    "알림 활성", s.get("alert_enabled", True), key=f"bm_en_{idx}")

            # 알림 플래그 수동 리셋
            if st.checkbox("알림 발송 플래그 보기/리셋", key=f"bm_fl_{idx}"):
                fa = s.get("first_alert_sent", False)
                sa = s.get("second_alert_sent", False)
                st.caption(f"1차 발송: {'✅ 발송됨' if fa else '미발송'}  |  "
                           f"2차 발송: {'✅ 발송됨' if sa else '미발송'}")
                if st.button("🔄 플래그 초기화 (재발송 허용)", key=f"bm_rst_{idx}"):
                    s["first_alert_sent"]  = False
                    s["second_alert_sent"] = False
                    save_settings(settings)
                    st.success("초기화 완료")
                    st.rerun()

            bc1, bc2 = st.columns(2)
            with bc1:
                if st.button("💾 저장", key=f"bm_sv_{idx}", type="primary"):
                    save_settings(settings)
                    st.success(f"✅ {s.get('advertiser_name', '')} 저장 완료")
                    st.rerun()
            with bc2:
                if st.button("🗑️ 삭제", key=f"bm_rm_{idx}"):
                    settings.pop(idx)
                    save_settings(settings)
                    st.rerun()

    if settings:
        st.divider()
        if st.button("💾 전체 저장", use_container_width=True):
            save_settings(settings)
            st.success("전체 저장 완료")


# ─── 발송 이력 탭 ───────────────────────────────────────────────────────────────
with t_history:
    history = load_history()

    if not history:
        st.info("발송 이력이 없습니다.")
    else:
        # 최신 순 정렬
        history_sorted = list(reversed(history))

        rows = []
        for h in history_sorted[:200]:
            rows.append({
                "발송 시각":   h.get("sent_at", "")[:16].replace("T", " "),
                "광고주":      h.get("advertiser_name", ""),
                "알림 단계":   "1차 경고" if h.get("alert_type") == "first" else "소진",
                "잔액(원)":    f"{h.get('balance', 0):,}",
                "기준금액(원)": f"{h.get('threshold_amount', 0):,}",
                "연락처":      h.get("phone", ""),
                "상태":        h.get("status", ""),
                "오류":        h.get("error_message", ""),
            })

        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption(f"최근 {len(rows)}건 표시 (전체 {len(history)}건)")

        if st.button("🗑️ 이력 전체 삭제", type="secondary"):
            from bizmoney_alert import save_history
            save_history([])
            st.success("이력 삭제 완료")
            st.rerun()


# ─── 테스트 발송 탭 ─────────────────────────────────────────────────────────────
with t_test:
    st.markdown("### 테스트 알림톡 발송")
    st.caption("실제 발송 전 dry-run으로 내용을 확인하거나, 지정 번호로 테스트 발송합니다.")

    settings = load_settings()
    names    = [s["advertiser_name"] for s in settings if s.get("advertiser_name")]

    if not names:
        st.info("광고주 설정을 먼저 등록해주세요.")
    else:
        test_name = st.selectbox("광고주 선택", names, key="test_adv")
        s = next((x for x in settings if x["advertiser_name"] == test_name), {})

        test_phone = st.text_input(
            "테스트 발송 번호",
            value=s.get("manager_phone", ""),
            placeholder="010-0000-0000",
            key="test_phone",
        )
        alert_type = st.radio(
            "알림 단계", ["1차 경고", "2차 소진"], horizontal=True, key="test_type"
        )
        test_balance  = st.number_input("테스트 잔액(원)", value=30000, step=1000, key="test_bal")
        dry_run_check = st.checkbox("Dry-run (실제 발송 안 함)", value=True, key="test_dry")

        # 템플릿 미리보기
        from bizmoney_alert import _build_vars
        is_first = alert_type == "1차 경고"
        threshold = int(s.get("first_alert_amount", 50000) if is_first
                        else s.get("second_alert_amount", 0))
        s_preview = dict(s)
        vars_ = _build_vars(s_preview, test_balance, threshold)
        tmpl  = TEMPLATE_FIRST if is_first else TEMPLATE_DEPLETED
        preview_text = tmpl
        for k, v in vars_.items():
            preview_text = preview_text.replace(f"#{{{k}}}", str(v))

        st.markdown("**메시지 미리보기**")
        st.code(preview_text, language=None)

        if st.button("📤 테스트 발송", type="primary", key="btn_test_send"):
            if not test_phone.strip():
                st.error("발송 번호를 입력해주세요.")
            else:
                tcode = TEMPLATE_CODE_FIRST if is_first else TEMPLATE_CODE_DEPLETED
                with st.spinner("발송 중..." if not dry_run_check else "Dry-run 실행 중..."):
                    result = send_kakao_alerttalk(
                        test_phone.strip(), tcode, vars_, dry_run=dry_run_check
                    )
                if result.get("status") in ("success", "dry_run"):
                    st.success(
                        "✅ Dry-run 완료 (실제 발송 안 됨)" if dry_run_check
                        else "✅ 알림톡 발송 성공"
                    )
                elif result.get("status") == "skipped":
                    st.warning(f"발송 건너뜀: {result.get('error', '')}")
                else:
                    st.error(f"발송 실패: {result.get('error', '')}")

                st.json(result)

        # 잔액 조회 테스트
        st.divider()
        st.markdown("**잔액 조회 테스트**")
        if st.button("잔액 조회 테스트", key="btn_bal_test"):
            if not s.get("api_access_license") or not s.get("secret_key"):
                st.error("API 키가 설정되어 있지 않습니다.")
            else:
                with st.spinner("조회 중..."):
                    res = get_bizmoney_balance(
                        s["customer_id"],
                        s["api_access_license"],
                        s["secret_key"],
                    )
                if res["status"] == "success":
                    st.success(f"잔액: **{res['balance']:,}원**")
                else:
                    st.error(f"실패: {res.get('error', '')}")
                st.json({k: v for k, v in res.items() if k not in ("balance",)})

        # 전체 알림 체크 (dry-run)
        st.divider()
        st.markdown("**전체 알림 체크 실행**")
        dry2 = st.checkbox("Dry-run", value=True, key="full_dry")
        if st.button("전체 알림 체크 실행", key="btn_full_check"):
            from bizmoney_alert import run_check
            with st.spinner("실행 중..."):
                results = run_check(dry_run=dry2)
            for r in results:
                cid = r["customer_id"]
                bal = r.get("balance")
                st.markdown(f"**{cid}** — 잔액: {f'{bal:,}원' if bal is not None else '조회 실패'}")
                for a in r.get("actions", []):
                    icon = "✅" if a.get("status") in ("success", "dry_run") else (
                           "⏭️" if a.get("status") == "skipped" else "❌")
                    st.caption(f"  {icon} [{a.get('type')}] {a.get('detail', '')}")
