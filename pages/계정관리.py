"""계정 관리 — 광고주 계정 승인·권한·수정·삭제 (관리자 전용)"""
import streamlit as st
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from auth import (
    load_accounts, create_account, update_account, delete_account,
    approve_account, reject_account, normalize_permissions,
    enabled_perm_keys, PERM_CATALOG,
)

if st.session_state.get("auth_type") != "admin":
    st.error("🔒 관리자만 접근 가능합니다.")
    st.stop()

# 권한 목록 (정렬 고정)
PERM_LIST = list(PERM_CATALOG.items())  # [(key, (path, label, icon)), ...]

def _perm_label_str(perms_dict):
    labels = [f"{icon} {label}" for k, (_, label, icon) in PERM_LIST
              if perms_dict.get(k, False)]
    return " · ".join(labels) if labels else "권한 없음"

# ══════════════════════════════════════════════════════════════════════════════
st.title("👤 계정 관리")

tab_pending, tab_accounts, tab_create = st.tabs([
    "🔔 승인 요청",
    "📋 계정 목록",
    "➕ 계정 생성",
])

accounts = load_accounts()
pending  = [a for a in accounts if not a.get("approved", True)]
approved = [a for a in accounts if a.get("approved", True)]

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — 승인 요청
# ══════════════════════════════════════════════════════════════════════════════
with tab_pending:
    if not pending:
        st.info("현재 승인 대기 중인 가입 요청이 없습니다.")
    else:
        st.caption(f"총 {len(pending)}건의 승인 요청이 있습니다.")
        for acc in pending:
            uid  = acc.get("username", "")
            biz  = acc.get("business_name", "")
            name = acc.get("contact_name", "")
            phone = acc.get("phone", "—")
            date_ = acc.get("created_at", "—")

            with st.expander(
                f"🏢  {biz}  ·  {uid}  ·  신청일: {date_}",
                expanded=True,
            ):
                ic1, ic2 = st.columns([3, 2])
                with ic1:
                    st.markdown(
                        f"**업체명:** {biz}  \n"
                        f"**담당자:** {name}  \n"
                        f"**이메일:** {phone}  \n"
                        f"**아이디:** {uid}  \n"
                        f"**신청일:** {date_}",
                    )
                with ic2:
                    st.markdown("**부여할 권한 선택**")
                    new_perms = {}
                    for perm_key, (_, label, icon) in PERM_LIST:
                        new_perms[perm_key] = st.checkbox(
                            f"{icon} {label}",
                            key=f"pend_perm_{uid}_{perm_key}",
                        )

                bc1, bc2 = st.columns(2)
                with bc1:
                    if st.button("✅ 승인", type="primary",
                                 use_container_width=True, key=f"approve_{uid}"):
                        approve_account(uid, new_perms)
                        st.success(f"{biz} 승인 완료")
                        st.rerun()
                with bc2:
                    if st.button("❌ 거절 (계정 삭제)", use_container_width=True,
                                 key=f"reject_{uid}"):
                        reject_account(uid)
                        st.warning(f"{uid} 거절 및 삭제")
                        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — 계정 목록
# ══════════════════════════════════════════════════════════════════════════════
with tab_accounts:
    if not approved:
        st.info("승인된 광고주 계정이 없습니다.")
    else:
        active_n   = sum(1 for a in approved if a.get("is_active", True))
        inactive_n = len(approved) - active_n
        kc1, kc2, kc3 = st.columns(3)
        kc1.metric("전체 계정",  f"{len(approved)}개")
        kc2.metric("활성",       f"{active_n}개")
        kc3.metric("비활성",     f"{inactive_n}개")
        st.markdown("<div style='margin-top:12px;'></div>", unsafe_allow_html=True)

        for acc in approved:
            uid       = acc.get("username", "")
            biz       = acc.get("business_name", "")
            is_active = acc.get("is_active", True)
            perms_dict = normalize_permissions(acc.get("permissions", {}))
            dot = "🟢" if is_active else "🔴"

            with st.expander(
                f"{dot}  {biz}  ·  {uid}  ·  "
                f"{_perm_label_str(perms_dict)}",
                expanded=False,
            ):
                st.caption(
                    f"client_id: {acc.get('client_id','')}  |  "
                    f"생성일: {acc.get('created_at','')}  |  "
                    f"상태: {'활성' if is_active else '비활성'}"
                )

                with st.form(f"edit_{uid}"):
                    ec1, ec2 = st.columns([3, 2])
                    with ec1:
                        e_biz    = st.text_input("업체명", value=biz, key=f"eb_{uid}")
                        e_pw     = st.text_input(
                            "새 비밀번호 (변경 시만 입력)",
                            type="password", key=f"epw_{uid}",
                            placeholder="변경하지 않으면 비워두세요",
                        )
                        e_active = st.checkbox("계정 활성화", value=is_active, key=f"ea_{uid}")

                    with ec2:
                        st.markdown("**접근 권한**")
                        e_perms = {}
                        for perm_key, (_, label, icon) in PERM_LIST:
                            e_perms[perm_key] = st.checkbox(
                                f"{icon} {label}",
                                value=perms_dict.get(perm_key, False),
                                key=f"ep_{uid}_{perm_key}",
                            )

                    btn1, btn2 = st.columns(2)
                    with btn1:
                        do_save = st.form_submit_button("💾 저장", type="primary")
                    with btn2:
                        do_del  = st.form_submit_button("🗑️ 삭제")

                    if do_save:
                        update_account(
                            uid,
                            business_name=e_biz.strip() or None,
                            password=e_pw or None,
                            permissions=e_perms,
                            is_active=e_active,
                        )
                        st.success("저장 완료")
                        st.rerun()

                    if do_del:
                        delete_account(uid)
                        st.success(f"{uid} 계정 삭제 완료")
                        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — 계정 직접 생성 (관리자 발급)
# ══════════════════════════════════════════════════════════════════════════════
with tab_create:
    st.caption("관리자가 직접 광고주 계정을 발급합니다. 가입 신청 없이 즉시 활성화됩니다.")
    with st.form("create_account", clear_on_submit=True):
        cc1, cc2 = st.columns([3, 2])
        with cc1:
            n_biz  = st.text_input("업체명 *",     placeholder="예: 마케팁")
            n_user = st.text_input("아이디 *",     placeholder="영문+숫자 조합 권장")
            n_pw1  = st.text_input("비밀번호 *",   type="password")
            n_pw2  = st.text_input("비밀번호 확인 *", type="password")
        with cc2:
            st.markdown("**접근 권한**")
            n_perms = {}
            for perm_key, (_, label, icon) in PERM_LIST:
                n_perms[perm_key] = st.checkbox(
                    f"{icon} {label}", key=f"nperm_{perm_key}"
                )
            st.caption("선택된 메뉴만 광고주에게 노출됩니다.")

        if st.form_submit_button("✅ 계정 생성", type="primary"):
            if not n_biz.strip():
                st.error("업체명을 입력해주세요.")
            elif not n_user.strip():
                st.error("아이디를 입력해주세요.")
            elif not n_pw1:
                st.error("비밀번호를 입력해주세요.")
            elif n_pw1 != n_pw2:
                st.error("비밀번호가 일치하지 않습니다.")
            else:
                ok, msg = create_account(n_biz.strip(), n_user.strip(), n_pw1, n_perms)
                if ok:
                    st.success(f"✅ {n_biz.strip()} 계정 생성 완료 (ID: {n_user.strip()})")
                    st.rerun()
                else:
                    st.error(msg)
