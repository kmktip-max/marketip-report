"""마케팁 OS — 메인 앱"""
import streamlit as st
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

# .env 로드 (로컬 개발용; Streamlit Cloud는 secrets 사용)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass

from components.style import SIDEBAR_CSS
from auth import verify_admin, verify_client

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
# 로그인 화면
# ══════════════════════════════════════════════════════════════════════════════
def _login_page():
    st.markdown("""
<style>
section[data-testid="stSidebar"] { display: none !important; }
[data-testid="stSidebarNav"]      { display: none !important; }
</style>
""", unsafe_allow_html=True)

    _, cc, _ = st.columns([1, 1.1, 1])
    with cc:
        st.markdown("<div style='height:60px;'></div>", unsafe_allow_html=True)

        # 로고
        if LOGO_PATH and Image:
            try:
                st.image(LOGO_PATH, width=110)
            except Exception:
                pass

        st.markdown("""
<div style="text-align:center;margin:16px 0 32px;">
  <div style="font-size:28px;font-weight:900;color:#111;letter-spacing:-.5px;">마케팁 전용</div>
  <div style="font-size:13px;color:#6B7280;margin-top:6px;">광고 운영 관리 시스템</div>
</div>""", unsafe_allow_html=True)

        tab_admin, tab_client = st.tabs(["🔑  관리자 로그인", "🏢  광고주 로그인"])

        with tab_admin:
            a_id = st.text_input("아이디", key="la_id", placeholder="관리자 아이디")
            a_pw = st.text_input("비밀번호", type="password", key="la_pw",
                                 placeholder="관리자 비밀번호")
            if st.button("로그인", type="primary", use_container_width=True, key="la_btn"):
                if verify_admin(a_id.strip(), a_pw):
                    st.session_state.update({
                        "authenticated":    True,
                        "auth_type":        "admin",
                        "auth_username":    a_id.strip(),
                        "auth_permissions": ["all"],
                        "settlement_auth":  True,   # 기존 정산관리 인증 자동 통과
                    })
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
                    st.session_state.update({
                        "authenticated":    True,
                        "auth_type":        "client",
                        "auth_username":    c_id.strip(),
                        "auth_client":      client,
                        "auth_permissions": client.get("permissions", []),
                    })
                    st.rerun()
                else:
                    st.error("아이디 또는 비밀번호를 확인해주세요.")

# ══════════════════════════════════════════════════════════════════════════════
# 인증 확인
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state.get("authenticated"):
    _login_page()
    st.stop()

auth_type  = st.session_state.get("auth_type", "")
auth_perms = st.session_state.get("auth_permissions", [])

# ══════════════════════════════════════════════════════════════════════════════
# 네비게이션 구성
# ══════════════════════════════════════════════════════════════════════════════
_PERM_PAGES = [
    ("structure_consulting", "pages/광고분석컨설팅.py", "광고구조 컨설팅"),
    ("report_view",          "pages/월간보고서.py",     "월간보고서"),
    ("payback",              "pages/페이백신청.py",     "광고비 페이백신청"),
]

if auth_type == "admin":
    pg = st.navigation([
        st.Page("pages/광고분석컨설팅.py", title="광고구조 컨설팅"),
        st.Page("pages/월간보고서.py",    title="월간보고서"),
        st.Page("pages/광고주관리.py",    title="광고주관리"),
        st.Page("pages/페이백신청.py",    title="광고비 페이백신청"),
        st.Page("pages/키워드도구.py",    title="키워드도구"),
        st.Page("pages/정산관리.py",      title="정산관리"),
        st.Page("pages/계정관리.py",      title="계정관리"),
    ])
else:
    client_pages = [
        st.Page(path, title=title)
        for perm, path, title in _PERM_PAGES
        if perm in auth_perms
    ]
    if not client_pages:
        st.warning("접근 가능한 메뉴가 없습니다. 관리자에게 문의하세요.")
        if st.button("🚪  로그아웃"):
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
    st.session_state.clear()
    st.rerun()

with st.sidebar:
    # ── 로고 ──────────────────────────────────────────────────────────────
    st.markdown('<div class="sb-logo-wrap">', unsafe_allow_html=True)
    if LOGO_PATH:
        st.image(LOGO_PATH, width=136)
    else:
        st.markdown('<div style="font-size:20px;font-weight:900;color:#006633;">마케팁</div>',
                    unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # ── 관리자 메뉴 ───────────────────────────────────────────────────────
    if auth_type == "admin":
        st.markdown('<span class="sb-label">광고구조 컨설팅</span>', unsafe_allow_html=True)
        st.page_link("pages/광고분석컨설팅.py", label="📈  광고분석컨설팅", use_container_width=True)
        st.page_link("pages/월간보고서.py",     label="📩  월간보고서",      use_container_width=True)

        st.markdown('<span class="sb-label">광고주 관리</span>', unsafe_allow_html=True)
        st.page_link("pages/광고주관리.py", label="🏢  광고주 목록",       use_container_width=True)
        st.page_link("pages/페이백신청.py", label="💸  광고비 페이백신청", use_container_width=True)

        st.markdown('<span class="sb-label">광고 운영</span>', unsafe_allow_html=True)
        st.page_link("pages/키워드도구.py", label="🔍  키워드 도구", use_container_width=True)

        st.markdown("""
<div style="padding:12px 20px 8px;margin-top:8px;">
  <hr style="border:none;border-top:1px solid #E5E8ED;margin:0 0 10px;">
</div>""", unsafe_allow_html=True)
        st.page_link("pages/정산관리.py", label="⚙️  정산관리", use_container_width=True)
        st.page_link("pages/계정관리.py", label="👤  계정관리", use_container_width=True)

    # ── 광고주 메뉴 ───────────────────────────────────────────────────────
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
        for perm, path, title in _PERM_PAGES:
            if perm in auth_perms:
                icons = {"structure_consulting":"📈","report_view":"📩","payback":"💸"}
                st.page_link(path, label=f"{icons.get(perm,'')}  {title}",
                             use_container_width=True)

    # ── 로그아웃 (공통) ───────────────────────────────────────────────────
    st.markdown('<div class="sb-bottom">', unsafe_allow_html=True)
    uname = "관리자" if auth_type == "admin" else st.session_state.get("auth_username", "")
    st.markdown(f'<div class="sb-user-info">접속: <b>{uname}</b></div>',
                unsafe_allow_html=True)
    if st.button("🚪  로그아웃", use_container_width=True, key="sb_logout"):
        _logout()
    st.markdown('</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 페이지 실행
# ══════════════════════════════════════════════════════════════════════════════
pg.run()
