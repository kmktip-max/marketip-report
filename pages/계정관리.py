"""계정 관리 — 광고주 계정 생성/수정/삭제 (관리자 전용)"""
import streamlit as st
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from auth import load_accounts, create_account, update_account, delete_account

# ── 관리자 전용 ───────────────────────────────────────────────────────────
if st.session_state.get("auth_type") != "admin":
    st.error("🔒 관리자만 접근 가능합니다.")
    st.stop()

# ── 상수 ─────────────────────────────────────────────────────────────────
ALL_PERMS = [
    ("structure_consulting", "📈 광고구조 컨설팅"),
    ("report_view",          "📩 월간보고서"),
    ("payback",              "💸 광고비 페이백신청"),
]

def _perm_labels(perms):
    return [label for key, label in ALL_PERMS if key in perms] or ["없음"]

# ── 페이지 ────────────────────────────────────────────────────────────────
st.title("👤 계정 관리")
st.caption("광고주 계정을 생성하고 접근 권한을 설정합니다. 회원가입 없이 관리자가 직접 발급합니다.")

# ══════════════════════════════════════════════════════════════════════════════
# 계정 생성
# ══════════════════════════════════════════════════════════════════════════════
with st.expander("➕ 새 광고주 계정 생성", expanded=False):
    with st.form("create_account", clear_on_submit=True):
        cc1, cc2 = st.columns([3, 2])
        with cc1:
            n_biz  = st.text_input("업체명 *", placeholder="예: 법무법인 재현")
            n_user = st.text_input("아이디 *", placeholder="영문+숫자 조합 권장")
            n_pw1  = st.text_input("비밀번호 *", type="password")
            n_pw2  = st.text_input("비밀번호 확인 *", type="password")
        with cc2:
            st.markdown("**접근 권한**")
            n_perms = []
            for perm_key, perm_label in ALL_PERMS:
                if st.checkbox(perm_label, key=f"nperm_{perm_key}"):
                    n_perms.append(perm_key)
            st.markdown("---")
            st.caption("선택한 권한에 해당하는\n메뉴만 광고주에게 노출됩니다.")

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
                    st.success(f"✅ {n_biz.strip()} 계정 생성 완료 (ID: {n_user.strip()}, client_id: {msg})")
                    st.rerun()
                else:
                    st.error(msg)

# ══════════════════════════════════════════════════════════════════════════════
# 계정 목록
# ══════════════════════════════════════════════════════════════════════════════
accounts = load_accounts()

if not accounts:
    st.info("등록된 광고주 계정이 없습니다. 위에서 계정을 생성해주세요.")
else:
    active_n   = sum(1 for a in accounts if a.get("is_active", True))
    inactive_n = len(accounts) - active_n

    kc1, kc2, kc3 = st.columns(3)
    kc1.metric("전체 계정", f"{len(accounts)}개")
    kc2.metric("활성",      f"{active_n}개")
    kc3.metric("비활성",    f"{inactive_n}개")

    st.markdown("<div style='margin-top:12px;'></div>", unsafe_allow_html=True)

    for acc in accounts:
        is_active  = acc.get("is_active", True)
        status_dot = "🟢" if is_active else "🔴"
        cur_perms  = acc.get("permissions", [])

        with st.expander(
            f"{status_dot}  {acc.get('business_name','')}  ·  ID: {acc.get('username','')}  ·  "
            f"권한: {', '.join(_perm_labels(cur_perms))}",
            expanded=False,
        ):
            st.caption(
                f"client_id: {acc.get('client_id','')}  |  "
                f"생성일: {acc.get('created_at','')}  |  "
                f"상태: {'활성' if is_active else '비활성'}"
            )

            uid = acc.get("username", "")
            with st.form(f"edit_{uid}"):
                ec1, ec2 = st.columns([3, 2])
                with ec1:
                    e_biz    = st.text_input("업체명", value=acc.get("business_name",""), key=f"eb_{uid}")
                    e_pw     = st.text_input("새 비밀번호 (변경 시만 입력)",
                                             type="password", key=f"epw_{uid}",
                                             placeholder="변경하지 않으면 비워두세요")
                    e_active = st.checkbox("계정 활성화", value=is_active, key=f"ea_{uid}")
                with ec2:
                    st.markdown("**접근 권한**")
                    e_perms = []
                    for perm_key, perm_label in ALL_PERMS:
                        if st.checkbox(perm_label, value=perm_key in cur_perms,
                                       key=f"ep_{uid}_{perm_key}"):
                            e_perms.append(perm_key)

                btn1, btn2 = st.columns(2)
                with btn1:
                    do_save = st.form_submit_button("💾 저장", type="primary")
                with btn2:
                    do_del  = st.form_submit_button("🗑️ 삭제")

                if do_save:
                    ok = update_account(
                        uid,
                        business_name=e_biz.strip() or None,
                        password=e_pw or None,
                        permissions=e_perms,
                        is_active=e_active,
                    )
                    if ok:
                        st.success("저장 완료")
                        st.rerun()

                if do_del:
                    ok = delete_account(uid)
                    if ok:
                        st.success(f"{uid} 계정 삭제 완료")
                        st.rerun()
