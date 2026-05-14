import streamlit as st
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from components.style import SIDEBAR_CSS

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

# ── 라우팅 등록 (page_link 호출 전에 먼저) ────────────────────────────────────
pg = st.navigation([
    st.Page("pages/광고분석컨설팅.py", title="광고분석컨설팅"),
    st.Page("pages/월간보고서.py",    title="월간보고서"),
    st.Page("pages/페이백신청.py",    title="광고비 페이백신청"),
    st.Page("pages/정산관리.py",      title="정산관리"),       # 사이드바 미노출
])

# ── CSS 주입 ──────────────────────────────────────────────────────────────────
st.markdown(SIDEBAR_CSS, unsafe_allow_html=True)

# ── 사이드바 ──────────────────────────────────────────────────────────────────
with st.sidebar:

    # ── 로고 ──────────────────────────────────────────────────────────────
    st.markdown('<div class="sb-logo-wrap">', unsafe_allow_html=True)
    if LOGO_PATH:
        st.image(LOGO_PATH, width=136)
    else:
        st.markdown('<div style="font-size:20px;font-weight:900;color:#006633;">마케팁</div>',
                    unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # ── 상단 메뉴 ──────────────────────────────────────────────────────────
    st.markdown('<span class="sb-label">광고 관리</span>', unsafe_allow_html=True)
    st.page_link("pages/광고분석컨설팅.py", label="📈  광고분석컨설팅", use_container_width=True)
    st.page_link("pages/월간보고서.py",     label="📩  월간보고서",      use_container_width=True)

    st.markdown('<span class="sb-label" id="section-payback">정산 관리</span>',
                unsafe_allow_html=True)
    st.page_link("pages/페이백신청.py", label="💸  광고비 페이백신청", use_container_width=True)

    # ── 하단 영역 (로그인된 경우) ──────────────────────────────────────────
    if st.session_state.get("authenticated"):
        st.markdown('<div class="sb-bottom">', unsafe_allow_html=True)

        # 회원 관리 (관리자만)
        if st.session_state.get("is_admin"):
            st.markdown('<span class="sb-label" style="padding:0 0 6px;">회원 관리</span>',
                        unsafe_allow_html=True)
            if st.button("👥  전체 회원 보기", use_container_width=True,
                         key="sb_member_list"):
                st.session_state["show_member_list"] = True

        # 광고주 정보
        advertiser = st.session_state.get("advertiser_name", "")
        if advertiser:
            st.markdown(
                f'<div class="sb-user-info">광고주: <b>{advertiser}</b></div>',
                unsafe_allow_html=True,
            )

        # 로그아웃
        if st.button("🚪  로그아웃", use_container_width=True, key="sb_logout"):
            for k in ["authenticated", "advertiser_name", "user_id", "is_admin",
                      "last_ai", "confirmed_df", "adf", "raw_df", "last_df_hash",
                      "chat_messages", "chat_api"]:
                st.session_state.pop(k, None)
            st.query_params.clear()
            st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)

    # ── 관리자 전용 메뉴 (사이드바 맨 하단, 작게) ──────────────────────────
    st.markdown("""
<div style="padding:12px 20px 8px; margin-top:8px;">
  <hr style="border:none;border-top:1px solid #E5E8ED;margin:0 0 10px;">
</div>
""", unsafe_allow_html=True)
    st.page_link("pages/정산관리.py", label="⚙️  정산관리", use_container_width=True)

# ── 페이지 실행 ───────────────────────────────────────────────────────────────
pg.run()
