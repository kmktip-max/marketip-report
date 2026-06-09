"""마케팁 OS — 메인 앱"""  # v2
import streamlit as st
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass

from components.style import SIDEBAR_CSS
from auth import (
    verify_admin, verify_client, create_session, verify_session, delete_session,
    register_pending, normalize_permissions, enabled_perm_keys, PERM_CATALOG,
)

try:
    from PIL import Image
except ImportError:
    Image = None

LOGO_PATH = next(
    (os.path.join(ROOT, f) for f in ["logo2.png", "logo.png", "logo.jpg", "logo.jpeg", "logo.webp"]
     if os.path.exists(os.path.join(ROOT, f))),
    None,
)

def _load_favicon():
    if LOGO_PATH and Image:
        try:
            return Image.open(LOGO_PATH)
        except Exception:
            pass
    return "📊"

st.set_page_config(
    page_title="마케팁",
    page_icon=_load_favicon(),
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════════════════════════════════
# 로그인 / 회원가입 화면
# ══════════════════════════════════════════════════════════════════════════════
def _login_page():
    st.markdown("""
<style>
section[data-testid="stSidebar"] { display: none !important; }
[data-testid="stSidebarNav"]      { display: none !important; }
.main .block-container {
    max-width: 960px !important;
    padding-top: 1.5rem !important;
    padding-bottom: 1rem !important;
    margin: 0 auto;
}
</style>
""", unsafe_allow_html=True)

    # ── 로고 base64 인코딩 (우측 폼에서 재사용) ──────────────────────────
    logo_html = ""
    if LOGO_PATH:
        try:
            import base64 as _b64
            ext = LOGO_PATH.rsplit(".", 1)[-1].lower().replace("jpg", "jpeg")
            with open(LOGO_PATH, "rb") as _f:
                logo_b64 = _b64.b64encode(_f.read()).decode()
            logo_html = (
                f'<img src="data:image/{ext};base64,{logo_b64}" '
                f'style="width:88px;height:auto;display:block;margin:0 auto 10px;" />'
            )
        except Exception:
            pass

    left_col, right_col = st.columns([1, 1], gap="medium")

    # ── 좌측: 서비스 카테고리 미리보기 ───────────────────────────────────
    with left_col:
        st.markdown("""
<div style="padding:20px 4px 16px 4px;">
  <div style="font-size:11px;font-weight:700;color:#9CA3AF;letter-spacing:.1em;
              text-transform:uppercase;margin-bottom:12px;">마케팁 서비스</div>

  <!-- 광고구조 컨설팅 -->
  <div style="margin-bottom:12px;">
    <div style="font-size:12px;font-weight:700;color:#6B7280;margin-bottom:5px;">광고구조 컨설팅</div>
    <div style="display:flex;flex-direction:column;gap:5px;">
      <div style="display:flex;align-items:center;gap:10px;padding:8px 12px;
                  background:#EEF2FF;border:1px solid #C7D2FE;border-radius:8px;">
        <span style="font-size:18px;line-height:1;">📈</span>
        <div style="flex:1;">
          <div style="font-size:14px;font-weight:700;color:#1E293B;">광고분석 컨설팅</div>
          <div style="font-size:12px;color:#64748B;">광고 구조 진단 및 개선 방향 제안</div>
        </div>
        <span style="font-size:11px;">🔒</span>
      </div>
      <div style="display:flex;align-items:center;gap:10px;padding:8px 12px;
                  background:#EEF2FF;border:1px solid #C7D2FE;border-radius:8px;">
        <span style="font-size:18px;line-height:1;">📩</span>
        <div style="flex:1;">
          <div style="font-size:14px;font-weight:700;color:#1E293B;">월간보고서</div>
          <div style="font-size:12px;color:#64748B;">월간 광고 성과 보고서 자동 생성 · 이메일 발송</div>
        </div>
        <span style="font-size:11px;">🔒</span>
      </div>
      <div style="display:flex;align-items:center;gap:10px;padding:8px 12px;
                  background:#EEF2FF;border:1px solid #C7D2FE;border-radius:8px;">
        <span style="font-size:18px;line-height:1;">💰</span>
        <div style="flex:1;">
          <div style="font-size:14px;font-weight:700;color:#1E293B;">비즈머니 알림</div>
          <div style="font-size:12px;color:#64748B;">광고 잔액 부족 시 카카오톡 · 문자 자동 알림</div>
        </div>
        <span style="font-size:11px;">🔒</span>
      </div>
    </div>
  </div>

  <!-- 수수료 환급 -->
  <div style="margin-bottom:12px;">
    <div style="font-size:12px;font-weight:700;color:#6B7280;margin-bottom:5px;">수수료 환급</div>
    <div style="display:flex;align-items:center;gap:10px;padding:8px 12px;
                background:#F0FDF4;border:1px solid #BBF7D0;border-radius:8px;">
      <span style="font-size:18px;line-height:1;">💸</span>
      <div style="flex:1;">
        <div style="font-size:14px;font-weight:700;color:#1E293B;">광고비 페이백 신청</div>
        <div style="font-size:12px;color:#64748B;">네이버 · 카카오 · 당근 페이백 계정 연동</div>
      </div>
      <span style="font-size:11px;">🔒</span>
    </div>
  </div>

  <!-- 광고 운영 -->
  <div style="margin-bottom:12px;">
    <div style="font-size:12px;font-weight:700;color:#6B7280;margin-bottom:5px;">광고 운영</div>
    <div style="display:flex;flex-direction:column;gap:5px;">
      <div style="display:flex;align-items:center;gap:10px;padding:8px 12px;
                  background:#FFF7ED;border:1px solid #FED7AA;border-radius:8px;">
        <span style="font-size:18px;line-height:1;">📊</span>
        <div style="flex:1;">
          <div style="font-size:14px;font-weight:700;color:#1E293B;">자동입찰 관리</div>
          <div style="font-size:12px;color:#64748B;">키워드별 목표 순위 자동 입찰 관리</div>
        </div>
        <span style="font-size:11px;">🔒</span>
      </div>
      <div style="display:flex;align-items:center;gap:10px;padding:8px 12px;
                  background:#FFF7ED;border:1px solid #FED7AA;border-radius:8px;">
        <span style="font-size:18px;line-height:1;">🛡️</span>
        <div style="flex:1;">
          <div style="font-size:14px;font-weight:700;color:#1E293B;">부정클릭 관리</div>
          <div style="font-size:12px;color:#64748B;">의심 클릭 탐지 및 IP 차단 요청 관리</div>
        </div>
        <span style="font-size:11px;">🔒</span>
      </div>
      <div style="display:flex;align-items:center;gap:10px;padding:8px 12px;
                  background:#FFF7ED;border:1px solid #FED7AA;border-radius:8px;">
        <span style="font-size:18px;line-height:1;">🔍</span>
        <div style="flex:1;">
          <div style="font-size:14px;font-weight:700;color:#1E293B;">키워드 추출</div>
          <div style="font-size:12px;color:#64748B;">경쟁사 기반 고효율 키워드 자동 발굴</div>
        </div>
        <span style="font-size:11px;">🔒</span>
      </div>
      <div style="display:flex;align-items:center;gap:10px;padding:8px 12px;
                  background:#FFF7ED;border:1px solid #FED7AA;border-radius:8px;">
        <span style="font-size:18px;line-height:1;">✍️</span>
        <div style="flex:1;">
          <div style="font-size:14px;font-weight:700;color:#1E293B;">광고소재 추출</div>
          <div style="font-size:12px;color:#64748B;">AI 기반 광고 제목 · 설명 자동 생성</div>
        </div>
        <span style="font-size:11px;">🔒</span>
      </div>
      <div style="display:flex;align-items:center;gap:10px;padding:8px 12px;
                  background:#FFF7ED;border:1px solid #FED7AA;border-radius:8px;">
        <span style="font-size:18px;line-height:1;">📐</span>
        <div style="flex:1;">
          <div style="font-size:14px;font-weight:700;color:#1E293B;">랜딩페이지 기획/분석</div>
          <div style="font-size:12px;color:#64748B;">랜딩페이지 진단 및 개선안 제안</div>
        </div>
        <span style="font-size:11px;">🔒</span>
      </div>
    </div>
  </div>

  <div style="padding:10px 12px;background:#F8FAFC;border-radius:6px;
              border-left:3px solid #6366F1;">
    <div style="font-size:11px;color:#475569;line-height:1.5;">
      🔒 모든 서비스는 <b>로그인 후</b> 이용 가능합니다.
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

    # ── 우측: 로그인 폼 ────────────────────────────────────────────────────
    with right_col:
        st.markdown(
            f'<div style="text-align:center;margin-bottom:18px;margin-top:4px;">'
            f'{logo_html}'
            f'<div style="font-size:18px;font-weight:900;color:#111;letter-spacing:-.5px;">마케팁 전용</div>'
            f'<div style="font-size:11px;color:#9CA3AF;margin-top:3px;">광고 운영 관리 시스템</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        tab_admin, tab_client, tab_join = st.tabs([
            "🔑  관리자 로그인",
            "🏢  광고주 로그인",
            "📝  광고주 가입 신청",
        ])

        with tab_admin:
            a_id = st.text_input("아이디", key="la_id", placeholder="관리자 아이디")
            a_pw = st.text_input("비밀번호", type="password", key="la_pw",
                                 placeholder="관리자 비밀번호")
            if st.button("로그인", type="primary", use_container_width=True, key="la_btn"):
                if verify_admin(a_id.strip(), a_pw):
                    token = create_session(a_id.strip(), "admin", ["all"])
                    st.session_state.update({
                        "authenticated":    True,
                        "auth_type":        "admin",
                        "auth_username":    a_id.strip(),
                        "auth_permissions": ["all"],
                        "settlement_auth":  True,
                        "_session_token":   token,
                        "user_id":          "admin",
                    })
                    st.query_params["token"] = token
                    st.rerun()
                else:
                    st.error("아이디 또는 비밀번호를 확인해주세요.")

        with tab_client:
            c_id = st.text_input("아이디", key="lc_id", placeholder="발급받은 아이디")
            c_pw = st.text_input("비밀번호", type="password", key="lc_pw",
                                 placeholder="발급받은 비밀번호")
            if st.button("로그인", type="primary", use_container_width=True, key="lc_btn"):
                client = verify_client(c_id.strip(), c_pw)
                if client:
                    perms_dict  = normalize_permissions(client.get("permissions", {}))
                    perm_keys   = enabled_perm_keys(perms_dict)
                    token = create_session(c_id.strip(), "client", perm_keys, client)
                    st.session_state.update({
                        "authenticated":    True,
                        "auth_type":        "client",
                        "auth_username":    c_id.strip(),
                        "auth_client":      client,
                        "auth_permissions": perm_keys,
                        "_session_token":   token,
                        "user_id":          c_id.strip(),
                    })
                    st.query_params["token"] = token
                    st.rerun()
                else:
                    acc_list = __import__("auth", fromlist=["load_accounts"]).load_accounts()
                    pending  = next((a for a in acc_list if a.get("username") == c_id.strip()
                                     and not a.get("approved", True)), None)
                    if pending:
                        st.warning("가입 승인 대기 중입니다. 관리자 승인 후 로그인 가능합니다.")
                    else:
                        st.error("아이디 또는 비밀번호를 확인해주세요.")

        with tab_join:
            st.caption("가입 신청 후 관리자 승인을 받으면 서비스를 이용할 수 있습니다.")
            with st.form("join_form", clear_on_submit=True):
                j_contact = st.text_input("성함 *",     placeholder="예: 홍길동")
                j_id      = st.text_input("아이디 *",   placeholder="영문+숫자 조합")
                j_pw1     = st.text_input("비밀번호 *", type="password")
                j_phone   = st.text_input("이메일 *",   placeholder="example@email.com")

                if st.form_submit_button("가입 신청", type="primary",
                                         use_container_width=True):
                    if not j_contact.strip():
                        st.error("성함을 입력해주세요.")
                    elif not j_id.strip():
                        st.error("아이디를 입력해주세요.")
                    elif not j_pw1:
                        st.error("비밀번호를 입력해주세요.")
                    elif not j_phone.strip():
                        st.error("이메일을 입력해주세요.")
                    else:
                        ok, msg = register_pending(
                            j_contact, j_id, j_pw1, j_contact, j_phone
                        )
                        if ok:
                            st.success(
                                "✅ 가입 신청이 완료됐습니다.\n\n"
                                "관리자 승인 후 로그인 탭에서 접속하세요."
                            )
                        else:
                            st.error(msg)

# ══════════════════════════════════════════════════════════════════════════════
# 세션 복원
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state.get("authenticated"):
    token = st.query_params.get("token", "")
    if token:
        sess = verify_session(token)
        if sess:
            is_adm = sess["user_type"] == "admin"
            st.session_state.update({
                "authenticated":    True,
                "auth_type":        sess["user_type"],
                "auth_username":    sess["username"],
                "auth_permissions": sess["permissions"],
                "auth_client":      sess.get("client_data", {}),
                "settlement_auth":  is_adm,
                "_session_token":   token,
                "user_id":          "admin" if is_adm else sess["username"],
            })

if not st.session_state.get("authenticated"):
    _login_page()
    st.stop()

# URL 에 토큰 항상 유지 (페이지 이동 후 F5 대비)
_active_token = st.session_state.get("_session_token", "")
if _active_token and st.query_params.get("token", "") != _active_token:
    st.query_params["token"] = _active_token

auth_type  = st.session_state.get("auth_type", "")
auth_perms = st.session_state.get("auth_permissions", [])

# ══════════════════════════════════════════════════════════════════════════════
# 네비게이션 구성
# ══════════════════════════════════════════════════════════════════════════════
if auth_type == "admin":
    pg = st.navigation([
        st.Page("pages/광고분석컨설팅.py", title="광고구조 컨설팅"),
        st.Page("pages/월간보고서.py",    title="월간보고서"),
        st.Page("pages/페이백신청.py",    title="광고비 페이백신청"),
        st.Page("pages/자동입찰.py",      title="자동입찰 관리"),
        st.Page("pages/키워드도구.py",    title="키워드 추출"),
        st.Page("pages/광고소재.py",      title="광고소재 추출"),
        st.Page("pages/상세페이지.py",    title="랜딩페이지 기획/분석"),
        st.Page("pages/정산관리.py",      title="정산관리"),
        st.Page("pages/비즈머니알림.py",  title="비즈머니 알림"),
        st.Page("pages/계정관리.py",      title="계정관리"),
        st.Page("pages/부정클릭관리.py",  title="부정클릭 관리"),
    ])
else:
    # 권한 있는 페이지만 navigation에 추가 (비즈머니 알림은 모든 계정 기본 제공)
    client_pages = []
    for perm_key, (path, title, _icon) in PERM_CATALOG.items():
        if perm_key == "bizmoney_alert" or perm_key in auth_perms:
            client_pages.append(st.Page(path, title=title))

    if not client_pages:
        st.warning("접근 가능한 메뉴가 없습니다. 관리자에게 문의하세요.")
        if st.button("🚪  로그아웃"):
            st.query_params.clear()
            st.session_state.clear()
            st.rerun()
        st.stop()
    pg = st.navigation(client_pages)

# ══════════════════════════════════════════════════════════════════════════════
# CSS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown(SIDEBAR_CSS, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 사이드바
# ══════════════════════════════════════════════════════════════════════════════
def _logout():
    delete_session(st.session_state.get("_session_token"))
    st.query_params.clear()
    st.session_state.clear()
    st.rerun()

with st.sidebar:
    st.markdown('<div class="sb-logo-wrap">', unsafe_allow_html=True)
    if LOGO_PATH:
        try:
            import base64 as _b64
            _ext = LOGO_PATH.rsplit(".", 1)[-1].lower().replace("jpg", "jpeg")
            with open(LOGO_PATH, "rb") as _lf:
                _lb64 = _b64.b64encode(_lf.read()).decode()
            st.markdown(
                f'<img src="data:image/{_ext};base64,{_lb64}" '
                f'style="width:136px;height:auto;display:block;'
                f'pointer-events:none;cursor:default;user-select:none;" />',
                unsafe_allow_html=True,
            )
        except Exception:
            st.markdown('<div style="font-size:20px;font-weight:900;color:#111827;">마케팁</div>',
                        unsafe_allow_html=True)
    else:
        st.markdown('<div style="font-size:20px;font-weight:900;color:#111827;">마케팁</div>',
                    unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    if auth_type == "admin":
        st.markdown('<span class="sb-label">광고구조 컨설팅</span>', unsafe_allow_html=True)
        st.page_link("pages/광고분석컨설팅.py", label="📈  광고분석컨설팅", use_container_width=True)
        st.page_link("pages/월간보고서.py",     label="📩  월간보고서",     use_container_width=True)
        st.page_link("pages/비즈머니알림.py",   label="💰  비즈머니 알림",  use_container_width=True)

        st.markdown('<span class="sb-label">수수료 환급</span>', unsafe_allow_html=True)
        st.page_link("pages/페이백신청.py", label="💸  광고비 페이백신청", use_container_width=True)
        st.markdown("""
<style>
div[data-testid="stSidebarContent"] [data-testid="stPageLink"]:has(a[href*="%ED%8E%98%EC%9D%B4%EB%B0%B1"]) a,
div[data-testid="stSidebarContent"] [data-testid="stPageLink"]:has(a[href*="%ED%8E%98%EC%9D%B4%EB%B0%B1%EC%8B%A0%EC%B2%AD"]) a {
    color: #1565C0 !important;
    font-weight: 700 !important;
}
</style>""", unsafe_allow_html=True)

        st.markdown('<span class="sb-label">광고 운영</span>', unsafe_allow_html=True)
        st.page_link("pages/자동입찰.py",      label="📊  자동입찰 관리",    use_container_width=True)
        st.page_link("pages/부정클릭관리.py",  label="🛡️  부정클릭 관리",      use_container_width=True)
        st.page_link("pages/키워드도구.py",    label="🔍  키워드 추출",         use_container_width=True)
        st.page_link("pages/광고소재.py",      label="✍️  광고소재 추출",       use_container_width=True)
        st.page_link("pages/상세페이지.py",    label="📐  랜딩페이지 기획/분석", use_container_width=True)

        st.markdown("""
<div style="padding:12px 20px 8px;margin-top:8px;">
  <hr style="border:none;border-top:1px solid #E5E8ED;margin:0 0 10px;">
</div>""", unsafe_allow_html=True)
        st.page_link("pages/정산관리.py",     label="⚙️  정산관리", use_container_width=True)
        st.page_link("pages/계정관리.py",     label="👤  계정관리", use_container_width=True)

    elif auth_type == "client":
        client_info = st.session_state.get("auth_client", {})
        biz = client_info.get("business_name", "")
        if biz:
            st.markdown(
                f'<div style="padding:10px 16px 6px;font-size:14px;'
                f'font-weight:700;color:#111;">{biz}</div>',
                unsafe_allow_html=True,
            )
        st.markdown('<span class="sb-label">내 메뉴</span>', unsafe_allow_html=True)
        st.page_link("pages/비즈머니알림.py", label="💰  비즈머니 알림", use_container_width=True)
        for perm_key, (path, title, icon) in PERM_CATALOG.items():
            if perm_key != "bizmoney_alert" and perm_key in auth_perms:
                st.page_link(path, label=f"{icon}  {title}", use_container_width=True)

    st.markdown('<div class="sb-bottom">', unsafe_allow_html=True)
    uname = "관리자" if auth_type == "admin" else st.session_state.get("auth_username", "")
    st.markdown(f'<div class="sb-user-info">접속: <b>{uname}</b></div>',
                unsafe_allow_html=True)
    if st.button("🚪  로그아웃", use_container_width=True, key="sb_logout"):
        _logout()
    st.markdown('</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 카카오 문의 플로팅 버튼 (모든 페이지 공통)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
.kakao-float {
    position: fixed;
    bottom: 28px;
    right: 28px;
    z-index: 99999;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0;
    text-decoration: none;
    cursor: pointer;
    filter: drop-shadow(0 4px 12px rgba(0,0,0,0.22));
    transition: transform 0.15s ease;
}
.kakao-float:hover { transform: scale(1.08); }
.kakao-float-circle {
    width: 56px;
    height: 56px;
    background: #FEE500;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
}
.kakao-float-circle svg {
    width: 30px;
    height: 30px;
}
.kakao-float-label {
    background: #3C1E1E;
    color: #FEE500;
    font-size: 11px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 0 0 6px 6px;
    letter-spacing: 0.5px;
    margin-top: -2px;
}
</style>
<a class="kakao-float" href="https://pf.kakao.com/_wMLIn" target="_blank" title="카카오 문의">
  <div class="kakao-float-circle">
    <!-- 카카오톡 말풍선 아이콘 -->
    <svg viewBox="0 0 24 24" fill="#3C1E1E" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 3C6.477 3 2 6.582 2 11c0 2.709 1.534 5.105 3.898 6.618L4.5 21l4.197-2.173A11.76 11.76 0 0 0 12 19c5.523 0 10-3.582 10-8s-4.477-8-10-8z"/>
    </svg>
  </div>
  <span class="kakao-float-label">문의</span>
</a>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 페이지 실행
# ══════════════════════════════════════════════════════════════════════════════
pg.run()
